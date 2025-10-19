"""CDK infrastructure unit tests using fine-grained assertions."""

import aws_cdk as cdk
from aws_cdk.assertions import Template, Match
import pytest

from stacks.order_stack import OrderStack


@pytest.fixture
def template():
    """Create a test stack and return its CloudFormation template."""
    app = cdk.App()
    stack = OrderStack(app, "TestOrderStack")
    return Template.from_stack(stack)


def test_kms_key(template):
    """Verify KMS key with rotation and alias."""
    template.resource_count_is("AWS::KMS::Key", 1)
    template.has_resource_properties(
        "AWS::KMS::Key",
        {
            "Description": "CMK for encrypting Orders table and SNS topic",
            "EnableKeyRotation": True,
        },
    )
    template.has_resource_properties(
        "AWS::KMS::Alias",
        {"AliasName": "alias/techtest-orders"},
    )


def test_dynamodb_table(template):
    """Verify DynamoDB table with encryption, PITR, TTL, and Streams."""
    template.resource_count_is("AWS::DynamoDB::Table", 1)
    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "TableName": "techtest-orders",
            "BillingMode": "PAY_PER_REQUEST",
            "SSESpecification": {
                "SSEEnabled": True,
                "SSEType": "KMS",
            },
            "PointInTimeRecoverySpecification": {
                "PointInTimeRecoveryEnabled": True,
            },
            "TimeToLiveSpecification": {
                "AttributeName": "expiresAt",
                "Enabled": True,
            },
            "StreamSpecification": {
                "StreamViewType": "NEW_AND_OLD_IMAGES",
            },
        },
    )


def test_sns_topic(template):
    """Verify SNS topic with encryption."""
    template.resource_count_is("AWS::SNS::Topic", 1)
    template.has_resource_properties(
        "AWS::SNS::Topic",
        {
            "TopicName": "techtest-order-notifications",
            "DisplayName": "Order Notifications",
            "KmsMasterKeyId": Match.any_value(),
        },
    )


def test_sqs_dlq(template):
    """Verify SQS Dead Letter Queue with encryption."""
    template.resource_count_is("AWS::SQS::Queue", 1)
    template.has_resource_properties(
        "AWS::SQS::Queue",
        {
            "QueueName": "techtest-orders-dlq",
            "MessageRetentionPeriod": 1209600,
            "VisibilityTimeout": 300,
            "KmsMasterKeyId": "alias/aws/sqs",
        },
    )


def test_create_order_lambda(template):
    """Verify CreateOrder Lambda with correct config and permissions."""
    # Find the CreateOrder function
    resources = template.find_resources(
        "AWS::Lambda::Function",
        {"Properties": Match.object_like({"FunctionName": "techtest-create-order"})},
    )
    assert len(resources) == 1

    # Check configuration
    function = list(resources.values())[0]["Properties"]
    assert function["Runtime"] == "python3.12"
    assert function["Handler"] == "create_order.handler"
    assert function["MemorySize"] == 256
    assert function["Timeout"] == 30
    assert function["Architectures"] == ["arm64"]

    # Check environment variables
    env_vars = function["Environment"]["Variables"]
    assert "TABLE_NAME" in env_vars
    assert env_vars["TTL_DAYS"] == "7"

    # Check IAM permissions for DynamoDB write
    template.has_resource_properties(
        "AWS::IAM::Policy",
        Match.object_like(
            {
                "PolicyDocument": {
                    "Statement": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "Action": Match.array_with(["dynamodb:PutItem"]),
                                    "Effect": "Allow",
                                }
                            )
                        ]
                    )
                }
            }
        ),
    )


def test_process_order_lambda(template):
    """Verify ProcessOrder Lambda with correct config and permissions."""
    # Find the ProcessOrder function
    resources = template.find_resources(
        "AWS::Lambda::Function",
        {"Properties": Match.object_like({"FunctionName": "techtest-process-order"})},
    )
    assert len(resources) == 1

    # Check configuration
    function = list(resources.values())[0]["Properties"]
    assert function["Runtime"] == "python3.12"
    assert function["Handler"] == "process_order.handler"
    assert function["MemorySize"] == 256
    assert function["Timeout"] == 60
    assert function["Architectures"] == ["arm64"]

    # Check environment variables
    env_vars = function["Environment"]["Variables"]
    assert "TABLE_NAME" in env_vars
    assert "TOPIC_ARN" in env_vars

    # Check IAM permissions for DynamoDB read/write
    template.has_resource_properties(
        "AWS::IAM::Policy",
        Match.object_like(
            {
                "PolicyDocument": {
                    "Statement": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "Action": Match.array_with(["dynamodb:UpdateItem"]),
                                    "Effect": "Allow",
                                }
                            )
                        ]
                    )
                }
            }
        ),
    )

    # Check IAM permissions for SNS publish
    template.has_resource_properties(
        "AWS::IAM::Policy",
        Match.object_like(
            {
                "PolicyDocument": {
                    "Statement": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "Action": "sns:Publish",
                                    "Effect": "Allow",
                                }
                            )
                        ]
                    )
                }
            }
        ),
    )


def test_event_source_mapping(template):
    """Verify DynamoDB Stream event source mapping with resilience config."""
    template.resource_count_is("AWS::Lambda::EventSourceMapping", 1)
    template.has_resource_properties(
        "AWS::Lambda::EventSourceMapping",
        {
            "BatchSize": 10,
            "BisectBatchOnFunctionError": True,
            "FunctionResponseTypes": ["ReportBatchItemFailures"],
            "MaximumRetryAttempts": 3,
            "MaximumRecordAgeInSeconds": 3600,
            "StartingPosition": "TRIM_HORIZON",
            "DestinationConfig": {
                "OnFailure": {
                    "Destination": Match.any_value(),
                }
            },
        },
    )


def test_stack_outputs(template):
    """Verify all expected CloudFormation outputs exist."""
    expected_outputs = [
        "OrdersTableName",
        "OrdersTableArn",
        "OrderNotificationsTopicArn",
        "StreamDLQUrl",
        "StreamDLQArn",
        "CreateOrderFunctionName",
        "CreateOrderFunctionArn",
        "ProcessOrderFunctionName",
        "ProcessOrderFunctionArn",
    ]

    for output_name in expected_outputs:
        template.has_output(output_name, {})
