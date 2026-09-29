#!/usr/bin/env python3
"""
CDK app entrypoint. Configuration comes from infra/.env (gitignored — copy
infra/.env.example to get started) rather than interactive prompts or
CloudFormation Parameters: no NoEcho double-entry prompts, no re-typing
secrets on every deploy, and `cdk diff`/`cdk deploy` behave predictably
since the values are fixed before synth even starts. See infra/README.md.
"""

import os

import aws_cdk as cdk
from dotenv import load_dotenv

from charkha_lifestyle.charkha_stack import CharkhaStack

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

stage = os.environ.get("STAGE", "dev")

app = cdk.App()
CharkhaStack(
    app,
    f"charkha-lifestyle-{stage}",
    stage=stage,
    allowed_origin=os.environ.get("ALLOWED_ORIGIN", "http://localhost:5173"),
    google_client_id=os.environ.get("GOOGLE_CLIENT_ID", ""),
    google_client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", ""),
    razorpay_key_id=os.environ.get("RAZORPAY_KEY_ID", ""),
    razorpay_key_secret=os.environ.get("RAZORPAY_KEY_SECRET", ""),
    env=cdk.Environment(
        # CDK_DEFAULT_ACCOUNT/REGION are set automatically by the CDK CLI from
        # whatever AWS CLI credentials/profile are active — no need to hardcode
        # your account ID here. AWS_REGION overrides the region if you ever
        # need to point at somewhere other than your default profile's region.
        account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
        region=os.environ.get("AWS_REGION", os.environ.get("CDK_DEFAULT_REGION", "ap-south-1")),
    ),
    tags={"app-1": "charkha-lifestyle"},
    description="Charkha Lifestyle — backend API, database, auth, and product media (frontend is on Vercel).",
)

app.synth()