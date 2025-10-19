"""Lambda handler for creating new orders in DynamoDB."""

import json
import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError


# Environment configuration
table_name = os.environ["TABLE_NAME"]
ttl_days = int(os.environ.get("TTL_DAYS", "7"))


@lru_cache(maxsize=1)
def _get_table():
    """Get or initialise the DynamoDB table (cached)."""
    dynamodb = boto3.resource("dynamodb")
    return dynamodb.Table(table_name)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Create a new order in the Orders table with idempotency.

    Args:
        event: Lambda event containing the order payload.
        context: Lambda context object.

    Returns:
        Response dict with statusCode and body containing the result message.
    """
    try:
        # Parse the body (for both direct invocation and API Gateway)
        if isinstance(event.get("body"), str):
            body = json.loads(event["body"])
        else:
            body = event

        # Validate required fields
        order_id = body.get("orderId")
        snack_type = body.get("snackType")

        if not order_id or not isinstance(order_id, str):
            return {
                "statusCode": 400,
                "body": json.dumps(
                    {"error": "Missing or invalid orderId (must be a non-empty string)"}
                ),
            }

        if not snack_type or not isinstance(snack_type, str):
            return {
                "statusCode": 400,
                "body": json.dumps(
                    {
                        "error": "Missing or invalid snackType (must be a non-empty string)"
                    }
                ),
            }

        # Calculate timestamps
        now = datetime.now(timezone.utc)
        created_at = now.isoformat()
        expires_at = int((now + timedelta(days=ttl_days)).timestamp())

        # Prepare item
        item = {
            "orderId": order_id,
            "snackType": snack_type,
            "status": "NEW",
            "createdAt": created_at,
            "expiresAt": expires_at,
        }

        # Idempotent PutItem with condition expression
        try:
            _get_table().put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(orderId)",
            )
            return {
                "statusCode": 201,
                "body": json.dumps(
                    {
                        "message": "Order created successfully",
                        "orderId": order_id,
                        "status": "NEW",
                    }
                ),
            }
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                # Order already exists - idempotency handled
                return {
                    "statusCode": 200,
                    "body": json.dumps(
                        {
                            "message": "Order already exists",
                            "orderId": order_id,
                        }
                    ),
                }
            else:
                # Re-raise other DynamoDB errors
                raise

    except json.JSONDecodeError:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Invalid JSON in request body"}),
        }
    except Exception as e:
        print(f"Error creating order: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal server error"}),
        }
