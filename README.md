# Kiro CLI EC2 host (AWS CDK, Python)

THIS IS NOT FOR VIBE CODERS, this is for senior engineers who understand
infrastructure and want to experiment at machine speed.

An AWS CDK (Python) app that provisions a single EC2 instance for running the
[Kiro CLI](https://kiro.dev/cli/). The instance lands in a **public subnet of a
Control Tower Account Factory VPC**, is reachable **only through AWS Systems
Manager (SSM) Session Manager** — no SSH, no key pair, no inbound ports — and
installs the Kiro CLI automatically on first boot via user data.

> ## ⚠️ READ THIS FIRST: [`WARNING.md`](./WARNING.md)
>
> This stack can place an **autonomous LLM agent on an EC2 host with
> `AdministratorAccess` over your entire AWS account** (the `admin_access=true`
> configuration). That is a language model with a shell and an unrestricted AWS
> credential, running unattended.
>
> - **The financial risk is UNLIMITED.** An admin-capable agent can launch
>   compute and call paid APIs at machine speed, run up an unbounded bill, and
>   even delete the budget alarms meant to warn you. **Watch cost continuously
>   during every run.**
> - **The real-world blast radius is unlimited.** It can create/modify/**delete
>   any resource**, mint new credentials to persist its own access, and cause
>   irreversible harm.
>
> **MITIGATIONS (mandatory):** run only in a **cost-controlled account**; run
> with **FULL account isolation** — the account must contain *nothing* except
> what the bot creates; **USE ONLY FOR EXPERIMENTS** and keep the useful output
> in **git**, never the account itself long-term; spin up a disposable account
> with **Control Tower Account Factory**, push results to git, then **delete the
> account** (or clear it with [`aws-nuke`](https://github.com/ekristen/aws-nuke)).
>
> **You assume all risk. The authors are not responsible for your AWS bill or
> for any other consequence of running this.** See [`WARNING.md`](./WARNING.md)
> for the full statement.

## What it creates

| Resource | Purpose |
| --- | --- |
| `AWS::IAM::Role` + instance profile | EC2 role with the AWS managed policy `AmazonSSMManagedInstanceCore`, enabling SSM Session Manager. |
| `AWS::IAM::Role` (admin, optional) | A second role suffixed `Admin` with `AdministratorAccess` (plus SSM core). Created and attached **only** when `-c admin_access=true` is set. |
| `AWS::EC2::SecurityGroup` | Egress-all, **zero inbound rules**. SSM only needs outbound 443, so no ports are exposed. |
| `AWS::EC2::Instance` | Amazon Linux 2023 host in a public subnet, 30 GiB encrypted gp3 root volume, user data that installs the Kiro CLI. |

The instance is tagged `Name=kiro-cli-host`.

## How it works

1. **VPC discovery** — `ec2.Vpc.from_lookup` finds the Control Tower VPC by its
   `Name` tag (default `aws-controltower-VPC`). The lookup resolves the VPC's
   subnets at synth time and classifies them as public or private from their
   route tables (a route to an internet gateway ⇒ public), which matches the
   Account Factory `PublicSubnet*` / `PrivateSubnet*` layout. Because this is a
   context lookup, the resolved values are cached in `cdk.context.json`.

2. **Public subnet placement** — the instance is placed with
   `SubnetSelection(subnet_type=SubnetType.PUBLIC)` and a public IP is
   associated.

3. **SSM access** — the instance role carries `AmazonSSMManagedInstanceCore`.
   Amazon Linux 2023 ships the SSM agent pre-installed and enabled, so the host
   registers with Systems Manager a minute or two after boot. All operator
   access is via Session Manager; there is no SSH path.

4. **Kiro CLI install (user data)** — on first boot the instance:
   - updates packages and installs base tooling (`git`, `tar`, `zstd`, …),
   - creates a dedicated `kiro` user with a real home directory,
   - runs the official installer `curl -fsSL https://cli.kiro.dev/install | bash`,
   - symlinks the binary to `/usr/local/bin/kiro-cli` and adds it to the login
     `PATH` via `/etc/profile.d/kiro-cli.sh`.

   The whole run is logged to `/var/log/kiro-bootstrap.log`, and the resolved
   version is written to `/var/log/kiro-version.txt` for quick verification.

   > Note: the Kiro CLI is interactive and requires a login (social/AWS Builder
   > ID) before its agents can be used. The user data only puts the binary in
   > place; you complete authentication yourself inside a Session Manager shell
   > by running `kiro-cli`.

## Configuration

Pass CDK context values with `-c key=value`:

| Context key | Default | Description |
| --- | --- | --- |
| `vpc_name` | `aws-controltower-VPC` | `Name` tag of the VPC to deploy into. |
| `instance_type` | `t4g.small` | EC2 instance type. The AMI architecture (ARM64 vs x86_64) is derived automatically, so both Graviton (`t4g.*`, `m7g.*`) and Intel/AMD (`t3.*`, `m7i.*`) families work. |
| `admin_access` | _(unset)_ | When truthy (`true`/`1`/`yes`/`on`), create a second IAM role with a similar name suffixed `Admin` carrying `AdministratorAccess` and attach it to the instance instead of the SSM-only role. The role is **only created when this option is set**. |

Example:

```bash
cdk deploy -c instance_type=t3.small -c vpc_name=aws-controltower-VPC
```

Example granting the instance administrator access:

```bash
cdk deploy -c admin_access=true
```

## Prerequisites

- An AWS account/region with the Control Tower Account Factory VPC present.
- Credentials for that account (e.g. `aws sts get-caller-identity` works).
- Node.js + the AWS CDK CLI (`cdk --version`).
- Python 3.9+.
- The environment must be CDK-bootstrapped once:
  ```bash
  cdk bootstrap aws://<ACCOUNT_ID>/<REGION>
  ```

## Deploy

```bash
# 1. Create/activate a virtualenv and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. (first time only) bootstrap the environment
cdk bootstrap

# 3. Review the synthesized template
cdk synth

# 4. Deploy
cdk deploy
```

On success CDK prints outputs including `InstanceId` and a ready-to-use
`SsmStartSessionCommand`.

## Connect and verify

The host is reachable only through SSM Session Manager.

Check that SSM sees the instance (wait ~1–2 minutes after deploy):

```bash
aws ssm describe-instance-information \
  --filters "Key=InstanceIds,Values=<INSTANCE_ID>" \
  --query 'InstanceInformationList[0].{Id:InstanceId,Ping:PingStatus,Platform:PlatformName}'
```

`PingStatus` should be `Online`.

Open an interactive shell (requires the
[Session Manager plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html)
for the AWS CLI):

```bash
aws ssm start-session --target <INSTANCE_ID>
```

Inside the session, confirm the CLI is installed, then log in:

```bash
kiro-cli --version
kiro-cli            # starts the interactive login + agent experience
```

You can also confirm the bootstrap non-interactively:

```bash
aws ssm send-command \
  --instance-ids <INSTANCE_ID> \
  --document-name AWS-RunShellScript \
  --parameters 'commands=["kiro-cli --version","cat /var/log/kiro-version.txt"]'
```

## Clean up

```bash
cdk destroy
```

This terminates the instance and removes the role and security group. (The
one-time CDK bootstrap stack, `CDKToolkit`, is left in place.)

## Project layout

```
.
├── app.py                      # CDK app entry point
├── cdk.json                    # CDK config (app command, feature flags)
├── requirements.txt            # Python dependencies (aws-cdk-lib, constructs)
├── kiro_ec2/
│   ├── __init__.py
│   └── kiro_ec2_stack.py       # the stack: VPC lookup, IAM role, SG, instance, user data
└── README.md
```

## Security notes

- **No inbound access.** The security group has no ingress rules; the instance
  is operated entirely through SSM Session Manager.
- **Encrypted storage.** The root EBS volume is gp3 and encrypted.
- **Least-privilege-ish access.** The instance role grants only
  `AmazonSSMManagedInstanceCore`. Add further policies only as your workloads
  require them.
- **Admin access is opt-in.** The `admin_access` option attaches
  `AdministratorAccess` to the instance via a separate `*Admin` role. This
  grants the host full control of the account — enable it only when you
  understand and accept that blast radius.

## ⚠️ Risks of giving an LLM unlimited "YOLO" access

See [`WARNING.md`](./WARNING.md) for the complete, explicit statement. The short
version:

- **You are handing an autonomous LLM an AWS credential.** With
  `admin_access=true`, the Kiro CLI agent on this host can act as account
  administrator on its own, with no human in the loop. LLMs hallucinate, loop,
  misread instructions, and can be steered by adversarial content they read off
  the internet — and then execute that mistake against your account at API
  speed.
- **Unlimited financial exposure.** The agent can launch arbitrary compute and
  call paid APIs faster than you will notice. There is no spend cap. AWS Budgets
  only *notify* (with lag) and can themselves be deleted by an admin-capable
  agent, so **you must watch cost continuously during any run** — keep Cost
  Explorer / the Billing console open and be ready to kill the instance and
  revoke credentials.
- **Unlimited real-world exposure.** It can create, modify, and **delete any
  resource**, create new IAM principals to persist its own access, disable
  guardrails (CloudTrail, Config, budgets), and cause irreversible damage.

**MITIGATIONS — do all of them, every time:**

1. **Run only in a cost-controlled account** with strict budgets/alerts and,
   ideally, an org-level spend ceiling the agent cannot remove.
2. **Run with FULL account isolation.** The account must contain **nothing**
   other than what the bot creates — no production workloads, shared data,
   long-lived secrets, or cross-account trust.
3. **USE ONLY FOR EXPERIMENTS.** The *output* (CDK, Terraform, management
   scripts, artifacts) belongs in **git**; the AWS account is never a long-term
   home for anything.
4. **Use a disposable account.** Spin one up with **Control Tower Account
   Factory**, run the experiment, push the useful output to git, then
   **close/delete the account** — or clear it with
   [`aws-nuke`](https://github.com/ekristen/aws-nuke) once results are
   committed. Never reuse the experiment account for anything that matters.
5. **Prefer the SSM-only (non-admin) role** whenever the experiment allows it.

**By deploying — especially with `-c admin_access=true` — you assume all risk.**
The financial exposure is unlimited and entirely yours. The authors and
contributors are **not responsible for your AWS bill**, for data loss, for any
security incident, or for any other consequence of running this. If you are not
willing to own every one of those outcomes, do not deploy it.
