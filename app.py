#!/usr/bin/env python3
"""CDK app entry point for the DevOps Technical Test."""

import os
import aws_cdk as cdk
from stacks.order_stack import OrderStack


app = cdk.App()

# Instantiate the main stack
OrderStack(
    app,
    "TechTestOrderStack",
    env=cdk.Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"),
        region=os.getenv("CDK_DEFAULT_REGION", "us-east-1"),  # Default to us-east-1
    ),
    description="DevOps Technical Test - Event-Driven Order Processing",
)

app.synth()