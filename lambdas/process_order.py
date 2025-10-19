"""Lambda handler for processing orders from DynamoDB Streams."""

import json
import os
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Dict, List

import boto3
from botocore.exceptions import ClientError


# Environment configuration
table_name = os.environ["TABLE_NAME"]
topic_arn = os.environ["TOPIC_ARN"]


@lru_cache(maxsize=1)
def _get_table():
    """Get or initialise the DynamoDB table (cached)."""
    dynamodb = boto3.resource("dynamodb")
    return dynamodb.Table(table_name)


@lru_cache(maxsize=1)
def _get_sns_client():
    """Get or initialise the SNS client (cached)."""
    return boto3.client("sns")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, List[Dict[str, str]]]:
    """Process orders from DynamoDB Stream and publish notifications.

    Only processes records where the new status is "NEW". Updates the order
    status to "PROCESSED" and publishes a notification to SNS.

    Implements partial batch failure reporting for resilience.

    Args:
        event: DynamoDB Stream event containing order records.
        context: Lambda context object.

    Returns:
        Dict with batchItemFailures list for partial failure handling.
    """
    batch_item_failures = []

    for record in event.get("Records", []):
        sequence_number = record.get("dynamodb", {}).get("SequenceNumber")

        try:
            # Only process INSERT and MODIFY events
            event_name = record.get("eventName")
            if event_name not in ["INSERT", "MODIFY"]:
                print(f"Skipping event type: {event_name}")
                continue

            # Extract new image
            new_image = record.get("dynamodb", {}).get("NewImage")
            if not new_image:
                print(f"No NewImage found in record: {sequence_number}")
                continue

            # Deserialise DynamoDB JSON format
            order_id = new_image.get("orderId", {}).get("S")
            status = new_image.get("status", {}).get("S")

            if not order_id:
                print(f"Missing orderId in record: {sequence_number}")
                continue

            # Only process orders with status "NEW"
            if status != "NEW":
                print(f"Skipping order {order_id} with status: {status}")
                continue

            # Update order status to PROCESSED with conditional check
            processed_at = datetime.now(timezone.utc).isoformat()

            try:
                _get_table().update_item(
                    Key={"orderId": order_id},
                    UpdateExpression="SET #status = :processed, processedAt = :timestamp",
                    ConditionExpression="#status = :new",
                    ExpressionAttributeNames={
                        "#status": "status",
                    },
                    ExpressionAttributeValues={
                        ":new": "NEW",
                        ":processed": "PROCESSED",
                        ":timestamp": processed_at,
                    },
                )
                print(f"Updated order {order_id} to PROCESSED")

                # Publish notification to SNS (no PII, just orderId and status)
                message = {
                    "orderId": order_id,
                    "status": "PROCESSED",
                }

                _get_sns_client().publish(
                    TopicArn=topic_arn,
                    Message=json.dumps(message),
                    Subject="Order Processed",
                )
                print(f"Published notification for order {order_id}")

            except ClientError as e:
                if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                    # Order already processed by another invocation - safe to ignore
                    print(f"Order {order_id} already processed, skipping")
                else:
                    # Other DynamoDB errors should trigger retry
                    raise

        except Exception as e:
            # Log error and add to batch failures for retry
            print(f"Error processing record {sequence_number}: {str(e)}")
            if sequence_number:
                batch_item_failures.append({"itemIdentifier": sequence_number})

    # Return partial batch failure response
    return {"batchItemFailures": batch_item_failures}
