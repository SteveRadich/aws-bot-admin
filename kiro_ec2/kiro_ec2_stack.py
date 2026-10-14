"""Stack that provisions an SSM-managed EC2 host running Kiro CLI.

The stack:
  1. Looks up the Control Tower Account Factory VPC (by its Name tag).
  2. Selects a public subnet from that VPC.
  3. Creates an IAM role for EC2 that grants SSM Session Manager access.
  4. Launches an EC2 instance in the public subnet with user data that
     installs the Kiro CLI.

Access is exclusively through SSM Session Manager. No SSH, no key pair, and
no inbound security-group rules are created.

Context parameters (pass with -c key=value):
  vpc_name        Name tag of the VPC to look up. Default: aws-controltower-VPC
  instance_type   EC2 instance type. Default: t4g.small (Graviton/ARM64)
  admin_access    When truthy (true/1/yes/on), create a second IAM role with a
                  similar name suffixed "Admin" carrying AdministratorAccess
                  and attach it to the instance instead of the SSM-only role.
                  Default: unset (SSM-only role is used).

The AMI CPU architecture (ARM64 vs x86_64) is derived automatically from the
chosen instance type, so overriding instance_type with either an ARM
(e.g. t4g.*, m7g.*) or x86 (e.g. t3.*, m7i.*) family just works.
"""
from aws_cdk import (
    CfnOutput,
    Stack,
    Tags,
    aws_ec2 as ec2,
    aws_iam as iam,
)
from constructs import Construct


class KiroEc2Stack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc_name = self.node.try_get_context("vpc_name") or "aws-controltower-VPC"
        instance_type_str = self.node.try_get_context("instance_type") or "t4g.small"
        admin_access = _as_bool(self.node.try_get_context("admin_access"))
        instance_type = ec2.InstanceType(instance_type_str)
        # Derive the AMI architecture from the instance type so the parameter
        # works for both Graviton (ARM64) and Intel/AMD (x86_64) families.
        cpu_type = (
            ec2.AmazonLinuxCpuType.ARM_64
            if instance_type.architecture == ec2.InstanceArchitecture.ARM_64
            else ec2.AmazonLinuxCpuType.X86_64
        )

        # ------------------------------------------------------------------
        # 1. Find the Control Tower Account Factory VPC by its Name tag.
        #    from_lookup resolves subnets at synth time and classifies them
        #    as PUBLIC/PRIVATE based on their route tables (a route to an
        #    internet gateway => public), which matches the Control Tower
        #    PublicSubnet* / PrivateSubnet* layout.
        # ------------------------------------------------------------------
        vpc = ec2.Vpc.from_lookup(self, "ControlTowerVpc", vpc_name=vpc_name)

        # ------------------------------------------------------------------
        # 2. Select the public subnets.
        # ------------------------------------------------------------------
        public_subnets = ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC)

        # ------------------------------------------------------------------
        # 3. IAM role for EC2 with SSM Session Manager access.
        #
        #    When admin_access is set, a second role with a similar name
        #    suffixed "Admin" is created carrying AdministratorAccess, and it
        #    is attached to the instance in place of the SSM-only role. The
        #    admin role still includes SSM core so Session Manager keeps
        #    working. The role/attachment is only created when the option is
        #    enabled.
        # ------------------------------------------------------------------
        role = iam.Role(
            self,
            "KiroEc2SsmRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            description="Role for the Kiro EC2 host, enabling SSM Session Manager.",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                ),
            ],
        )

        if admin_access:
            admin_role = iam.Role(
                self,
                "KiroEc2SsmRoleAdmin",
                assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
                description="Admin role for the Kiro EC2 host (AdministratorAccess + SSM Session Manager).",
                managed_policies=[
                    iam.ManagedPolicy.from_aws_managed_policy_name(
                        "AmazonSSMManagedInstanceCore"
                    ),
                    iam.ManagedPolicy.from_aws_managed_policy_name(
                        "AdministratorAccess"
                    ),
                ],
            )
            instance_role = admin_role
        else:
            instance_role = role

        # ------------------------------------------------------------------
        # 4. Security group. Access is SSM-only: SSM needs only outbound
        #    (443) access, provided by the default egress-all rule. No
        #    inbound rules are added, so there is no SSH or other ingress.
        # ------------------------------------------------------------------
        security_group = ec2.SecurityGroup(
            self,
            "KiroEc2Sg",
            vpc=vpc,
            description="Kiro EC2 host - egress all, no inbound (SSM Session Manager only).",
            allow_all_outbound=True,
        )

        # ------------------------------------------------------------------
        # 5. User data: install the Kiro CLI (and dependencies).
        # ------------------------------------------------------------------
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(*_kiro_user_data_lines())

        # Amazon Linux 2023 ships the SSM agent pre-installed and enabled.
        # CPU architecture is derived from the instance type above.
        machine_image = ec2.MachineImage.latest_amazon_linux2023(
            cpu_type=cpu_type,
        )

        instance = ec2.Instance(
            self,
            "KiroEc2Instance",
            instance_type=instance_type,
            machine_image=machine_image,
            vpc=vpc,
            vpc_subnets=public_subnets,
            role=instance_role,
            security_group=security_group,
            user_data=user_data,
            associate_public_ip_address=True,
            # No key_name: access is exclusively via SSM Session Manager.
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        volume_size=30,
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                        encrypted=True,
                        delete_on_termination=True,
                    ),
                )
            ],
        )
        Tags.of(instance).add("Name", "kiro-cli-host")

        # ------------------------------------------------------------------
        # Outputs.
        # ------------------------------------------------------------------
        CfnOutput(self, "InstanceId", value=instance.instance_id)
        CfnOutput(self, "PublicIp", value=instance.instance_public_ip)
        CfnOutput(self, "PublicDnsName", value=instance.instance_public_dns_name)
        CfnOutput(self, "VpcId", value=vpc.vpc_id)
        CfnOutput(
            self,
            "SsmStartSessionCommand",
            value=f"aws ssm start-session --target {instance.instance_id}",
        )
        CfnOutput(self, "InstanceRoleArn", value=instance_role.role_arn)
        CfnOutput(self, "AdminAccessEnabled", value=str(admin_access).lower())


def _as_bool(value) -> bool:
    """Interpret a CDK context value as a boolean.

    Context values arrive as strings (e.g. -c admin_access=true) or, when set
    in cdk.json, as native JSON booleans. Treat the common truthy spellings as
    True and everything else (including None) as False.
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _kiro_user_data_lines():
    """Return the shell lines that install Kiro CLI on first boot.

    Everything is logged to /var/log/kiro-bootstrap.log. The Kiro CLI binary
    is interactive and requires a login to use its agents, so this only puts
    the binary in place and makes it available on the PATH for all users.
    """
    # Note: CDK's UserData.for_linux() already prepends "#!/bin/bash", so we
    # do not add another shebang here.
    return [
        "set -uxo pipefail",
        "exec > >(tee -a /var/log/kiro-bootstrap.log) 2>&1",
        'echo "=== kiro-cli bootstrap started: $(date -u) ==="',
        # Base tooling.
        "dnf -y update || true",
        "dnf -y install tar gzip zstd findutils shadow-utils glibc git which || true",
        # Install Kiro CLI as a dedicated non-root user so the interactive
        # binary has a real HOME. Default install dir is ~/.local/bin.
        "id kiro >/dev/null 2>&1 || useradd -m -s /bin/bash kiro",
        "export HOME=/home/kiro",
        # Run the official installer non-interactively as the kiro user.
        # --no-confirm avoids any interactive prompts in the installer.
        "sudo -u kiro HOME=/home/kiro bash -c 'curl -fsSL https://cli.kiro.dev/install | bash -s -- --no-confirm' || "
        "sudo -u kiro HOME=/home/kiro bash -c 'curl -fsSL https://cli.kiro.dev/install | bash' || true",
        # Make kiro-cli available system-wide on the PATH.
        "if [ -x /home/kiro/.local/bin/kiro-cli ]; then ln -sf /home/kiro/.local/bin/kiro-cli /usr/local/bin/kiro-cli; fi",
        'echo "export PATH=\\"/home/kiro/.local/bin:$PATH\\"" > /etc/profile.d/kiro-cli.sh',
        # Record the result for easy verification over SSM.
        "( /usr/local/bin/kiro-cli --version || /home/kiro/.local/bin/kiro-cli --version ) "
        "> /var/log/kiro-version.txt 2>&1 || echo 'kiro-cli not on PATH yet' > /var/log/kiro-version.txt",
        'echo "=== kiro-cli bootstrap finished: $(date -u) ==="',
    ]
