"""CDK stack for order processing with DynamoDB Streams."""

import aws_cdk as cdk
from constructs import Construct
from aws_cdk import (
    aws_dynamodb as dynamodb,
    aws_kms as kms,
    aws_lambda as lambda_,
    aws_lambda_event_sources as lambda_event_sources,
    aws_logs as logs,
    aws_sns as sns,
    aws_sqs as sqs,
    Duration,
    RemovalPolicy,
    CfnOutput,
)

# Lambda configuration constants
CREATE_ORDER_TIMEOUT_SECONDS = 30
CREATE_ORDER_MEMORY_MB = 256
PROCESS_ORDER_TIMEOUT_SECONDS = 60
PROCESS_ORDER_MEMORY_MB = 256

# Stream processing configuration
STREAM_BATCH_SIZE = 10
STREAM_RETRY_ATTEMPTS = 3
STREAM_MAX_RECORD_AGE_SECONDS = 3600

# Logging configuration
LOG_RETENTION_DAYS = logs.RetentionDays.TWO_WEEKS

# DLQ configuration
DLQ_RETENTION_DAYS = 14
DLQ_VISIBILITY_TIMEOUT_SECONDS = 300


class OrderStack(cdk.Stack):
    """Stack for event-driven order processing using DynamoDB Streams."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        """Initialise the order processing stack.

        Args:
            scope: The scope in which this stack is defined.
            construct_id: The scoped construct ID.
            **kwargs: Additional stack properties.
        """
        super().__init__(scope, construct_id, **kwargs)

        # Get optional resource suffix for integration tests (makes names unique)
        resource_suffix = self.node.try_get_context("resource_suffix") or ""
        name_suffix = f"-{resource_suffix}" if resource_suffix else ""

        # KMS Customer Managed Key for encryption
        self.orders_cmk = kms.Key(
            self,
            "OrdersCMK",
            description="CMK for encrypting Orders table and SNS topic",
            alias=f"alias/techtest-orders{name_suffix}",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # DynamoDB Orders table with Streams enabled
        self.orders_table = dynamodb.Table(
            self,
            "OrdersTable",
            table_name=f"techtest-orders{name_suffix}",
            partition_key=dynamodb.Attribute(
                name="orderId",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryption_key=self.orders_cmk,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            ),
            time_to_live_attribute="expiresAt",
            stream=dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # SNS Topic for order notifications
        self.order_notifications_topic = sns.Topic(
            self,
            "OrderNotificationsTopic",
            topic_name=f"techtest-order-notifications{name_suffix}",
            display_name="Order Notifications",
            master_key=self.orders_cmk,
        )

        # SQS Dead Letter Queue for stream processing failures
        self.stream_dlq = sqs.Queue(
            self,
            "StreamProcessingDLQ",
            queue_name=f"techtest-orders-dlq{name_suffix}",
            encryption=sqs.QueueEncryption.KMS_MANAGED,
            retention_period=Duration.days(DLQ_RETENTION_DAYS),
            visibility_timeout=Duration.seconds(DLQ_VISIBILITY_TIMEOUT_SECONDS),
        )

        # Lambda A: CreateOrder function
        create_order_log_group = logs.LogGroup(
            self,
            "CreateOrderLogGroup",
            log_group_name=f"/aws/lambda/techtest-create-order{name_suffix}",
            retention=LOG_RETENTION_DAYS,
            removal_policy=RemovalPolicy.DESTROY,
        )

        self.create_order_function = lambda_.Function(
            self,
            "CreateOrderFunction",
            function_name=f"techtest-create-order{name_suffix}",
            runtime=lambda_.Runtime.PYTHON_3_12,
            architecture=lambda_.Architecture.ARM_64,
            handler="create_order.handler",
            code=lambda_.Code.from_asset("lambdas"),
            environment={
                "TABLE_NAME": self.orders_table.table_name,
                "TTL_DAYS": "7",
            },
            timeout=Duration.seconds(CREATE_ORDER_TIMEOUT_SECONDS),
            memory_size=CREATE_ORDER_MEMORY_MB,
            log_group=create_order_log_group,
        )

        # Grant CreateOrder Lambda permission to write to the Orders table
        self.orders_table.grant_write_data(self.create_order_function)

        # Grant permission to use the KMS key for encryption
        self.orders_cmk.grant_encrypt_decrypt(self.create_order_function)

        # Lambda B: ProcessOrder function (triggered by DynamoDB Stream)
        process_order_log_group = logs.LogGroup(
            self,
            "ProcessOrderLogGroup",
            log_group_name=f"/aws/lambda/techtest-process-order{name_suffix}",
            retention=LOG_RETENTION_DAYS,
            removal_policy=RemovalPolicy.DESTROY,
        )

        self.process_order_function = lambda_.Function(
            self,
            "ProcessOrderFunction",
            function_name=f"techtest-process-order{name_suffix}",
            runtime=lambda_.Runtime.PYTHON_3_12,
            architecture=lambda_.Architecture.ARM_64,
            handler="process_order.handler",
            code=lambda_.Code.from_asset("lambdas"),
            environment={
                "TABLE_NAME": self.orders_table.table_name,
                "TOPIC_ARN": self.order_notifications_topic.topic_arn,
            },
            timeout=Duration.seconds(PROCESS_ORDER_TIMEOUT_SECONDS),
            memory_size=PROCESS_ORDER_MEMORY_MB,
            log_group=process_order_log_group,
        )

        # Grant ProcessOrder Lambda permissions
        self.orders_table.grant_read_write_data(self.process_order_function)
        self.order_notifications_topic.grant_publish(self.process_order_function)
        self.orders_cmk.grant_encrypt_decrypt(self.process_order_function)

        # DynamoDB Stream event source mapping with resilience configuration
        stream_event_source = lambda_event_sources.DynamoEventSource(
            self.orders_table,
            starting_position=lambda_.StartingPosition.TRIM_HORIZON,
            batch_size=STREAM_BATCH_SIZE,
            bisect_batch_on_error=True,
            on_failure=lambda_event_sources.SqsDlq(self.stream_dlq),
            report_batch_item_failures=True,
            retry_attempts=STREAM_RETRY_ATTEMPTS,
            max_record_age=Duration.seconds(STREAM_MAX_RECORD_AGE_SECONDS),
        )

        self.process_order_function.add_event_source(stream_event_source)

        # Stack outputs
        CfnOutput(
            self,
            "OrdersTableName",
            value=self.orders_table.table_name,
            description="Name of the Orders DynamoDB table",
        )

        CfnOutput(
            self,
            "OrdersTableArn",
            value=self.orders_table.table_arn,
            description="ARN of the Orders DynamoDB table",
        )

        CfnOutput(
            self,
            "OrderNotificationsTopicArn",
            value=self.order_notifications_topic.topic_arn,
            description="ARN of the Order Notifications SNS topic",
        )

        CfnOutput(
            self,
            "StreamDLQUrl",
            value=self.stream_dlq.queue_url,
            description="URL of the Stream Processing DLQ",
        )

        CfnOutput(
            self,
            "StreamDLQArn",
            value=self.stream_dlq.queue_arn,
            description="ARN of the Stream Processing DLQ",
        )

        CfnOutput(
            self,
            "CreateOrderFunctionName",
            value=self.create_order_function.function_name,
            description="Name of the CreateOrder Lambda function",
        )

        CfnOutput(
            self,
            "CreateOrderFunctionArn",
            value=self.create_order_function.function_arn,
            description="ARN of the CreateOrder Lambda function",
        )

        CfnOutput(
            self,
            "ProcessOrderFunctionName",
            value=self.process_order_function.function_name,
            description="Name of the ProcessOrder Lambda function",
        )

        CfnOutput(
            self,
            "ProcessOrderFunctionArn",
            value=self.process_order_function.function_arn,
            description="ARN of the ProcessOrder Lambda function",
        )
