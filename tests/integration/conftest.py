"""Pytest configuration and fixtures for integration tests."""

import os
import time
import uuid
import boto3
import pytest
import sys
from typing import Generator, Dict, Any


def check_aws_credentials():
    """Check if AWS credentials are configured and provide guidance if not."""
    try:
        sts = boto3.client("sts")
        identity = sts.get_caller_identity()
        return True, identity
    except Exception:
        print("\n" + "=" * 80)
        print("AWS CREDENTIALS NOT CONFIGURED")
        print("=" * 80)
        print("\nIntegration tests require AWS credentials to deploy resources.")
        print("\nQuick Setup:\n")

        print("1. Get AWS access keys:")
        print("   https://console.aws.amazon.com/iam/home#/security_credentials")
        print("   Click: Create access key > Command Line Interface > Create\n")

        print("2. Run aws configure and enter your credentials:")
        print("   aws configure")
        print("   AWS Access Key ID: [paste your key]")
        print("   AWS Secret Access Key: [paste your secret]")
        print("   Default region name: us-east-1 (recommended)")
        print("   Default output format: json\n")

        print("3. Verify:")
        print("   aws sts get-caller-identity\n")

        print("4. Run tests:")
        print("   make test-integration\n")

        print("Don't have AWS CLI? https://aws.amazon.com/cli/\n")

        print("SKIP INTEGRATION TESTS:")
        print("  make test-unit    # Lambda tests only (no AWS)")
        print("  make test-cdk     # Infrastructure tests only (no AWS)\n")
        print("=" * 80)
        return False, None


@pytest.fixture(scope="session")
def aws_region() -> str:
    """Get AWS region from environment or AWS config."""
    import subprocess

    # Try environment variable first
    region = os.environ.get("AWS_REGION")
    if region:
        return region

    # Try AWS CLI config
    try:
        result = subprocess.run(
            ["aws", "configure", "get", "region"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass

    # Default fallback
    return "us-east-1"


@pytest.fixture(scope="session")
def aws_account_id(aws_region: str) -> str:
    """Get AWS account ID."""
    sts = boto3.client("sts", region_name=aws_region)
    return sts.get_caller_identity()["Account"]


@pytest.fixture(scope="session")
def test_stack_name() -> str:
    """Generate unique test stack name to avoid conflicts."""
    timestamp = int(time.time())
    unique_id = str(uuid.uuid4())[:8]
    return f"IntegrationTest-OrderStack-{timestamp}-{unique_id}"


@pytest.fixture(scope="session", autouse=True)
def verify_aws_credentials():
    """Verify AWS credentials before running any integration tests."""
    has_creds, identity = check_aws_credentials()
    if not has_creds:
        pytest.exit("AWS credentials not configured. See guidance above.", returncode=2)
    print(f"\nAWS Account: {identity['Account']}")
    print(f"AWS User/Role: {identity['Arn']}\n")


@pytest.fixture(scope="session")
def deployed_stack(
    test_stack_name: str, aws_region: str
) -> Generator[Dict[str, Any], None, None]:
    """
    Deploy the CDK stack for integration testing and clean up after.

    This fixture:
    1. Deploys the stack using CDK
    2. Retrieves stack outputs
    3. Yields outputs to tests
    4. Destroys the stack after all tests complete

    Yields:
        Dictionary containing CloudFormation stack outputs
    """
    import subprocess
    import json

    # Determine CDK command (prefer installed cdk, fallback to npx)
    import shutil

    cdk_cmd = "cdk" if shutil.which("cdk") else "npx"
    cdk_args = ["cdk"] if cdk_cmd == "npx" else []

    # Get virtualenv Python path
    venv_python = sys.executable

    # Deploy the stack with unique resource names
    unique_suffix = test_stack_name.split("-")[-1]  # Get unique ID from stack name
    print(f"\nDeploying integration test stack: {test_stack_name}")
    deploy_result = subprocess.run(
        [
            cdk_cmd,
            *cdk_args,
            "deploy",
            "--require-approval",
            "never",
            "--outputs-file",
            f"/tmp/{test_stack_name}-outputs.json",
            "--context",
            f"stack_name={test_stack_name}",
            "--context",
            f"resource_suffix={unique_suffix}",
        ],
        cwd="/home/dan/git/saber/cdk_app",
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "CDK_DEFAULT_REGION": aws_region,
            "PATH": f"{os.path.dirname(venv_python)}:{os.environ.get('PATH', '')}",
        },
    )

    if deploy_result.returncode != 0:
        pytest.fail(
            f"CDK deployment failed:\nSTDOUT: {deploy_result.stdout}\nSTDERR: {deploy_result.stderr}"
        )

    # Read outputs
    with open(f"/tmp/{test_stack_name}-outputs.json", "r") as f:
        outputs_data = json.load(f)

    # Extract outputs (CDK wraps them in stack name)
    stack_outputs = list(outputs_data.values())[0] if outputs_data else {}

    print(f"Stack deployed successfully. Outputs: {stack_outputs}")

    # Wait for event source mapping to become active
    print("Waiting for event source mapping to be enabled...")
    lambda_client = boto3.client("lambda", region_name=aws_region)
    function_name = stack_outputs.get("ProcessOrderFunctionName")

    if function_name:
        for _ in range(30):  # Wait up to 60 seconds
            time.sleep(2)
            try:
                mappings = lambda_client.list_event_source_mappings(
                    FunctionName=function_name
                )
                if mappings["EventSourceMappings"]:
                    state = mappings["EventSourceMappings"][0]["State"]
                    print(f"Event source mapping state: {state}")
                    if state == "Enabled":
                        print("Event source mapping is active!")
                        break
            except Exception as e:
                print(f"Checking event source mapping: {e}")

    # Additional wait for resources to stabilize
    time.sleep(10)

    yield stack_outputs

    # Teardown: Destroy the stack
    print(f"\nDestroying integration test stack: {test_stack_name}")
    destroy_result = subprocess.run(
        [
            cdk_cmd,
            *cdk_args,
            "destroy",
            "--force",
            "--context",
            f"stack_name={test_stack_name}",
        ],
        cwd="/home/dan/git/saber/cdk_app",
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "CDK_DEFAULT_REGION": aws_region,
            "PATH": f"{os.path.dirname(venv_python)}:{os.environ.get('PATH', '')}",
        },
    )

    if destroy_result.returncode != 0:
        print(
            f"WARNING: Stack destruction failed:\nSTDOUT: {destroy_result.stdout}\nSTDERR: {destroy_result.stderr}"
        )


@pytest.fixture(scope="session")
def dynamodb_client(aws_region: str):
    """Create DynamoDB client."""
    return boto3.client("dynamodb", region_name=aws_region)


@pytest.fixture(scope="session")
def lambda_client(aws_region: str):
    """Create Lambda client."""
    return boto3.client("lambda", region_name=aws_region)


@pytest.fixture(scope="session")
def sns_client(aws_region: str):
    """Create SNS client."""
    return boto3.client("sns", region_name=aws_region)


@pytest.fixture(scope="session")
def sqs_client(aws_region: str):
    """Create SQS client."""
    return boto3.client("sqs", region_name=aws_region)


@pytest.fixture(scope="session")
def cloudformation_client(aws_region: str):
    """Create CloudFormation client."""
    return boto3.client("cloudformation", region_name=aws_region)
