"""Unit tests for the ProcessOrder Lambda function."""

import json
import os
from unittest.mock import patch, MagicMock

import pytest
from botocore.exceptions import ClientError


# Set environment variables before importing the handler
os.environ["TABLE_NAME"] = "test-orders-table"
os.environ["TOPIC_ARN"] = "arn:aws:sns:us-east-1:123456789012:test-topic"

# Import handler after setting environment variables
from lambdas.process_order import handler


@pytest.fixture
def mock_dynamodb_table():
    """Create a mock DynamoDB table."""
    with patch("lambdas.process_order._get_table") as mock_get_table:
        mock_table = MagicMock()
        mock_get_table.return_value = mock_table
        yield mock_table


@pytest.fixture
def mock_sns_client():
    """Create a mock SNS client."""
    with patch("lambdas.process_order._get_sns_client") as mock_get_sns:
        mock_sns = MagicMock()
        mock_get_sns.return_value = mock_sns
        yield mock_sns


def create_stream_event(order_id, status, event_name="INSERT"):
    """Helper to create a DynamoDB Stream event."""
    return {
        "Records": [
            {
                "eventID": "1",
                "eventName": event_name,
                "eventVersion": "1.1",
                "eventSource": "aws:dynamodb",
                "dynamodb": {
                    "SequenceNumber": "111",
                    "Keys": {"orderId": {"S": order_id}},
                    "NewImage": {
                        "orderId": {"S": order_id},
                        "status": {"S": status},
                        "snackType": {"S": "crisps"},
                        "createdAt": {"S": "2025-10-18T10:00:00Z"},
                    },
                    "StreamViewType": "NEW_AND_OLD_IMAGES",
                },
            }
        ]
    }


def test_process_order_success(mock_dynamodb_table, mock_sns_client):
    """Test successful processing of a NEW order."""
    # Arrange
    event = create_stream_event("order-123", "NEW")
    mock_dynamodb_table.update_item.return_value = {}
    mock_sns_client.publish.return_value = {"MessageId": "msg-123"}

    # Act
    response = handler(event, None)

    # Assert
    assert response == {"batchItemFailures": []}

    # Verify update_item was called correctly
    mock_dynamodb_table.update_item.assert_called_once()
    call_args = mock_dynamodb_table.update_item.call_args
    assert call_args.kwargs["Key"] == {"orderId": "order-123"}
    assert (
        call_args.kwargs["UpdateExpression"]
        == "SET #status = :processed, processedAt = :timestamp"
    )
    assert call_args.kwargs["ConditionExpression"] == "#status = :new"
    assert call_args.kwargs["ExpressionAttributeValues"][":new"] == "NEW"
    assert call_args.kwargs["ExpressionAttributeValues"][":processed"] == "PROCESSED"

    # Verify SNS publish was called
    mock_sns_client.publish.assert_called_once()
    publish_args = mock_sns_client.publish.call_args
    assert (
        publish_args.kwargs["TopicArn"]
        == "arn:aws:sns:us-east-1:123456789012:test-topic"
    )
    assert publish_args.kwargs["Subject"] == "Order Processed"

    message = json.loads(publish_args.kwargs["Message"])
    assert message["orderId"] == "order-123"
    assert message["status"] == "PROCESSED"


def test_process_order_modify_event(mock_dynamodb_table, mock_sns_client):
    """Test processing of a MODIFY event with NEW status."""
    # Arrange
    event = create_stream_event("order-456", "NEW", event_name="MODIFY")
    mock_dynamodb_table.update_item.return_value = {}
    mock_sns_client.publish.return_value = {"MessageId": "msg-456"}

    # Act
    response = handler(event, None)

    # Assert
    assert response == {"batchItemFailures": []}
    mock_dynamodb_table.update_item.assert_called_once()
    mock_sns_client.publish.assert_called_once()


def test_process_order_non_new_status_ignored(mock_dynamodb_table, mock_sns_client):
    """Test that orders with non-NEW status are ignored."""
    # Arrange
    event = create_stream_event("order-789", "PROCESSED")

    # Act
    response = handler(event, None)

    # Assert
    assert response == {"batchItemFailures": []}

    # Verify no update or publish occurred
    mock_dynamodb_table.update_item.assert_not_called()
    mock_sns_client.publish.assert_not_called()


def test_process_order_remove_event_ignored(mock_dynamodb_table, mock_sns_client):
    """Test that REMOVE events are ignored."""
    # Arrange
    event = create_stream_event("order-remove", "NEW", event_name="REMOVE")

    # Act
    response = handler(event, None)

    # Assert
    assert response == {"batchItemFailures": []}
    mock_dynamodb_table.update_item.assert_not_called()
    mock_sns_client.publish.assert_not_called()


def test_process_order_already_processed(mock_dynamodb_table, mock_sns_client):
    """Test handling when order is already processed (conditional check fails)."""
    # Arrange
    event = create_stream_event("order-duplicate", "NEW")

    # Simulate ConditionalCheckFailedException
    error_response = {"Error": {"Code": "ConditionalCheckFailedException"}}
    mock_dynamodb_table.update_item.side_effect = ClientError(
        error_response, "UpdateItem"
    )

    # Act
    response = handler(event, None)

    # Assert
    assert response == {"batchItemFailures": []}

    # Verify update was attempted but SNS was not called (due to condition failure)
    mock_dynamodb_table.update_item.assert_called_once()
    mock_sns_client.publish.assert_not_called()


def test_process_order_partial_batch_failure(mock_dynamodb_table, mock_sns_client):
    """Test partial batch failure when one record fails."""
    # Arrange
    event = {
        "Records": [
            {
                "eventID": "1",
                "eventName": "INSERT",
                "dynamodb": {
                    "SequenceNumber": "111",
                    "NewImage": {
                        "orderId": {"S": "order-success"},
                        "status": {"S": "NEW"},
                    },
                },
            },
            {
                "eventID": "2",
                "eventName": "INSERT",
                "dynamodb": {
                    "SequenceNumber": "222",
                    "NewImage": {
                        "orderId": {"S": "order-fail"},
                        "status": {"S": "NEW"},
                    },
                },
            },
        ]
    }

    # First call succeeds, second fails
    error_response = {"Error": {"Code": "ServiceUnavailable"}}
    mock_dynamodb_table.update_item.side_effect = [
        {},  # First order succeeds
        ClientError(error_response, "UpdateItem"),  # Second order fails
    ]
    mock_sns_client.publish.return_value = {"MessageId": "msg-123"}

    # Act
    response = handler(event, None)

    # Assert
    assert len(response["batchItemFailures"]) == 1
    assert response["batchItemFailures"][0]["itemIdentifier"] == "222"

    # Verify first order was processed successfully
    assert mock_dynamodb_table.update_item.call_count == 2
    assert mock_sns_client.publish.call_count == 1


def test_process_order_missing_new_image(mock_dynamodb_table, mock_sns_client):
    """Test handling of record without NewImage."""
    # Arrange
    event = {
        "Records": [
            {
                "eventID": "1",
                "eventName": "REMOVE",
                "dynamodb": {
                    "SequenceNumber": "333",
                    "Keys": {"orderId": {"S": "order-deleted"}},
                    # No NewImage for REMOVE events
                },
            }
        ]
    }

    # Act
    response = handler(event, None)

    # Assert
    assert response == {"batchItemFailures": []}
    mock_dynamodb_table.update_item.assert_not_called()
    mock_sns_client.publish.assert_not_called()


def test_process_order_missing_order_id(mock_dynamodb_table, mock_sns_client):
    """Test handling of record missing orderId."""
    # Arrange
    event = {
        "Records": [
            {
                "eventID": "1",
                "eventName": "INSERT",
                "dynamodb": {
                    "SequenceNumber": "444",
                    "NewImage": {
                        "status": {"S": "NEW"},
                        # Missing orderId
                    },
                },
            }
        ]
    }

    # Act
    response = handler(event, None)

    # Assert
    assert response == {"batchItemFailures": []}
    mock_dynamodb_table.update_item.assert_not_called()
    mock_sns_client.publish.assert_not_called()


def test_process_order_poison_record_triggers_failure(
    mock_dynamodb_table, mock_sns_client
):
    """Test that a poison record (exception during processing) is reported as failure."""
    # Arrange
    event = create_stream_event("order-poison", "NEW")

    # Simulate unexpected error during update
    error_response = {"Error": {"Code": "InternalServerError"}}
    mock_dynamodb_table.update_item.side_effect = ClientError(
        error_response, "UpdateItem"
    )

    # Act
    response = handler(event, None)

    # Assert
    assert len(response["batchItemFailures"]) == 1
    assert response["batchItemFailures"][0]["itemIdentifier"] == "111"

    # Verify update was attempted but SNS was not called
    mock_dynamodb_table.update_item.assert_called_once()
    mock_sns_client.publish.assert_not_called()
