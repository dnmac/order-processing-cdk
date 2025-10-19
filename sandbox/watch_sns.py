#!/usr/bin/env python3
"""Monitor SNS notifications by subscribing to the topic."""

import sys
import json
import boto3
import time
from datetime import datetime

# Colors for terminal output
GREEN = "\033[0;32m"
BLUE = "\033[0;34m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
RED = "\033[0;31m"
BOLD = "\033[1m"
NC = "\033[0m"  # No Color


def get_sns_client():
    """Create SNS client pointing to LocalStack."""
    return boto3.client(
        "sns",
        endpoint_url="http://localhost:4566",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )


def get_sqs_client():
    """Create SQS client pointing to LocalStack."""
    return boto3.client(
        "sqs",
        endpoint_url="http://localhost:4566",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )


def setup_subscription():
    """
    Create a temporary SQS queue and subscribe it to the SNS topic.
    Returns (queue_url, subscription_arn).
    """
    sqs = get_sqs_client()
    sns = get_sns_client()

    # Create temporary queue for receiving notifications
    print(f"{BLUE} Creating temporary queue for SNS notifications...{NC}")
    queue_name = f"sns-monitor-{int(time.time())}"
    queue_response = sqs.create_queue(QueueName=queue_name)
    queue_url = queue_response["QueueUrl"]

    # Get queue ARN
    attrs = sqs.get_queue_attributes(QueueUrl=queue_url, AttributeNames=["QueueArn"])
    queue_arn = attrs["Attributes"]["QueueArn"]

    print(f"{GREEN}[OK] Queue created: {queue_name}{NC}")

    # Subscribe queue to SNS topic
    print(f"{BLUE} Subscribing to SNS topic...{NC}")
    topic_arn = "arn:aws:sns:us-east-1:000000000000:techtest-order-notifications"

    subscription = sns.subscribe(TopicArn=topic_arn, Protocol="sqs", Endpoint=queue_arn)
    subscription_arn = subscription["SubscriptionArn"]

    print(f"{GREEN}[OK] Subscribed to topic{NC}\n")

    return queue_url, subscription_arn, queue_name


def monitor_notifications(queue_url: str):
    """Poll SQS queue for SNS notifications."""
    sqs = get_sqs_client()

    print(f"{BOLD}{CYAN}{'=' * 80}{NC}")
    print(f"{BOLD}{BLUE} Monitoring SNS Notifications{NC}")
    print(f"{CYAN}Topic: techtest-order-notifications{NC}")
    print(f"{CYAN}Press Ctrl+C to stop{NC}")
    print(f"{BOLD}{CYAN}{'=' * 80}{NC}\n")

    message_count = 0

    try:
        while True:
            # Long poll for messages (wait up to 5 seconds)
            response = sqs.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=5,
                AttributeNames=["All"],
            )

            messages = response.get("Messages", [])

            for message in messages:
                message_count += 1

                # Parse SNS message
                body = json.loads(message["Body"])
                sns_message = json.loads(body.get("Message", "{}"))

                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                print(f"{GREEN}{'─' * 80}{NC}")
                print(f"{BOLD} Notification #{message_count} {NC}({timestamp})")
                print(f"{GREEN}{'─' * 80}{NC}")
                print(f"{BOLD}Order ID:{NC}  {sns_message.get('orderId', 'N/A')}")
                print(
                    f"{BOLD}Status:{NC}    {GREEN}{sns_message.get('status', 'N/A')}{NC}"
                )
                print(f"{GREEN}{'─' * 80}{NC}\n")

                # Delete message from queue
                sqs.delete_message(
                    QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"]
                )

            # Show alive indicator if no messages
            if not messages:
                print(
                    f"{CYAN} Waiting for notifications...{NC} (checked at {datetime.now().strftime('%H:%M:%S')})",
                    end="\r",
                )

    except KeyboardInterrupt:
        print(f"\n\n{YELLOW} Monitoring stopped{NC}")
        print(f"{CYAN}Total notifications received: {message_count}{NC}")


def cleanup(queue_url: str, subscription_arn: str, queue_name: str):
    """Clean up temporary resources."""
    sqs = get_sqs_client()
    sns = get_sns_client()

    print(f"\n{BLUE} Cleaning up...{NC}")

    try:
        # Unsubscribe from topic
        sns.unsubscribe(SubscriptionArn=subscription_arn)
        print(f"{GREEN}[OK] Unsubscribed from topic{NC}")
    except Exception as e:
        print(f"{YELLOW}[WARN]  Could not unsubscribe: {str(e)}{NC}")

    try:
        # Delete queue
        sqs.delete_queue(QueueUrl=queue_url)
        print(f"{GREEN}[OK] Deleted queue: {queue_name}{NC}")
    except Exception as e:
        print(f"{YELLOW}[WARN]  Could not delete queue: {str(e)}{NC}")


def check_dlq():
    """Check DLQ for failed messages."""
    sqs = get_sqs_client()

    try:
        # Get DLQ URL
        dlq_response = sqs.get_queue_url(QueueName="techtest-orders-dlq")
        dlq_url = dlq_response["QueueUrl"]

        # Get approximate message count
        attrs = sqs.get_queue_attributes(
            QueueUrl=dlq_url, AttributeNames=["ApproximateNumberOfMessages"]
        )

        message_count = int(attrs["Attributes"]["ApproximateNumberOfMessages"])

        if message_count > 0:
            print(
                f"{RED}[WARN]  DLQ has {message_count} messages (failures detected){NC}\n"
            )
        else:
            print(f"{GREEN}[OK] DLQ is empty (no failures){NC}\n")

    except Exception as e:
        print(f"{YELLOW}[WARN]  Could not check DLQ: {str(e)}{NC}\n")


def main():
    """Main entry point."""
    if "--help" in sys.argv or "-h" in sys.argv:
        print(f"{BLUE}SNS Notification Monitor{NC}")
        print(
            "\nThis tool monitors SNS notifications published by the ProcessOrder Lambda."
        )
        print("\nUsage:")
        print(f"  {sys.argv[0]}              - Start monitoring SNS notifications")
        print(f"  {sys.argv[0]} --dlq        - Check DLQ message count")
        print(f"  {sys.argv[0]} --help|-h    - Show this help")
        print(f"\n{CYAN}Tip: Run this in a separate terminal while creating orders{NC}")
        return

    if "--dlq" in sys.argv:
        check_dlq()
        return

    # Check if LocalStack is running
    try:
        get_sns_client().list_topics()
    except Exception:
        print(f"{RED}[ERROR] Cannot connect to LocalStack{NC}")
        print(f"{YELLOW}Is LocalStack running? Start with: make sandbox-start{NC}")
        sys.exit(1)

    # Setup subscription
    queue_url, subscription_arn, queue_name = setup_subscription()

    # Also check DLQ status
    check_dlq()

    # Monitor notifications
    try:
        monitor_notifications(queue_url)
    finally:
        cleanup(queue_url, subscription_arn, queue_name)


if __name__ == "__main__":
    main()
