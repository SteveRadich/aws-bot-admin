#!/usr/bin/env python3
"""CDK app entry point.

Deploys a single EC2 instance into the public subnet of a Control Tower
Account Factory VPC, with an SSM-enabled IAM role, and user data that
installs the Kiro CLI.
"""
import os

import aws_cdk as cdk

from kiro_ec2.kiro_ec2_stack import KiroEc2Stack

app = cdk.App()

# The VPC lookup (Vpc.from_lookup) requires a concrete account + region at
# synth time. These are taken from the ambient CLI credentials/environment.
env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION"),
)

KiroEc2Stack(
    app,
    "KiroEc2Stack",
    env=env,
    description="EC2 host in the Control Tower public subnet with SSM access and Kiro CLI installed.",
)

app.synth()
