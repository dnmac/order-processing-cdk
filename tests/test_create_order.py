"""Unit tests for the CreateOrder Lambda function."""

import json
import os
from unittest.mock import patch, MagicMock

import pytest
from botocore.exceptions import ClientError


# Set environment variables before importing the handler
os.environ["TABLE_NAME"] = "test-orders-table"
os.environ["TTL_DAYS"] = "7"

# Import handler after setting environment variables
from lambdas.create_order import handler


@pytest.fixture
def mock_dynamodb_table():
    """Create a mock DynamoDB table."""
    with patch("lambdas.create_order._get_table") as mock_get_table:
        mock_table = MagicMock()
        mock_get_table.return_value = mock_table
        yield mock_table


def test_create_order_success(mock_dynamodb_table):
    """Test successful order creation with valid payload."""
    # Arrange
    event = {
        "orderId": "order-123",
        "snackType": "crisps",
    }

    mock_dynamodb_table.put_item.return_value = {}

    # Act
    response = handler(event, None)

    # Assert
    assert response["statusCode"] == 201
    body = json.loads(response["body"])
    assert body["message"] == "Order created successfully"
    assert body["orderId"] == "order-123"
    assert body["status"] == "NEW"

    # Verify put_item was called with correct parameters
    mock_dynamodb_table.put_item.assert_called_once()
    call_args = mock_dynamodb_table.put_item.call_args
    item = call_args.kwargs["Item"]

    assert item["orderId"] == "order-123"
    assert item["snackType"] == "crisps"
    assert item["status"] == "NEW"
    assert "createdAt" in item
    assert "expiresAt" in item
    assert call_args.kwargs["ConditionExpression"] == "attribute_not_exists(orderId)"


def test_create_order_with_api_gateway_event(mock_dynamodb_table):
    """Test order creation with API Gateway event structure."""
    # Arrange
    event = {
        "body": json.dumps(
            {
                "orderId": "order-456",
                "snackType": "chocolate",
            }
        )
    }

    mock_dynamodb_table.put_item.return_value = {}

    # Act
    response = handler(event, None)

    # Assert
    assert response["statusCode"] == 201
    body = json.loads(response["body"])
    assert body["orderId"] == "order-456"


def test_create_order_duplicate_handled_gracefully(mock_dynamodb_table):
    """Test that duplicate orderId is handled gracefully with idempotency."""
    # Arrange
    event = {
        "orderId": "order-789",
        "snackType": "biscuits",
    }

    # Simulate ConditionalCheckFailedException
    error_response = {"Error": {"Code": "ConditionalCheckFailedException"}}
    mock_dynamodb_table.put_item.side_effect = ClientError(error_response, "PutItem")

    # Act
    response = handler(event, None)

    # Assert
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["message"] == "Order already exists"
    assert body["orderId"] == "order-789"


def test_create_order_missing_order_id(mock_dynamodb_table):
    """Test validation error when orderId is missing."""
    # Arrange
    event = {
        "snackType": "crisps",
    }

    # Act
    response = handler(event, None)

    # Assert
    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "error" in body
    assert "orderId" in body["error"]

    # Verify put_item was not called
    mock_dynamodb_table.put_item.assert_not_called()


def test_create_order_missing_snack_type(mock_dynamodb_table):
    """Test validation error when snackType is missing."""
    # Arrange
    event = {
        "orderId": "order-999",
    }

    # Act
    response = handler(event, None)

    # Assert
    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "error" in body
    assert "snackType" in body["error"]

    # Verify put_item was not called
    mock_dynamodb_table.put_item.assert_not_called()


def test_create_order_invalid_order_id_type(mock_dynamodb_table):
    """Test validation error when orderId is not a string."""
    # Arrange
    event = {
        "orderId": 12345,  # Should be string
        "snackType": "crisps",
    }

    # Act
    response = handler(event, None)

    # Assert
    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "error" in body
    assert "orderId" in body["error"]


def test_create_order_invalid_json(mock_dynamodb_table):
    """Test error handling for invalid JSON in request body."""
    # Arrange
    event = {
        "body": "not valid json {{{",
    }

    # Act
    response = handler(event, None)

    # Assert
    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "error" in body
    assert "JSON" in body["error"]


def test_create_order_dynamodb_error(mock_dynamodb_table):
    """Test error handling for unexpected DynamoDB errors."""
    # Arrange
    event = {
        "orderId": "order-error",
        "snackType": "crisps",
    }

    # Simulate unexpected DynamoDB error
    error_response = {"Error": {"Code": "ServiceUnavailable"}}
    mock_dynamodb_table.put_item.side_effect = ClientError(error_response, "PutItem")

    # Act
    response = handler(event, None)

    # Assert
    assert response["statusCode"] == 500
    body = json.loads(response["body"])
    assert "error" in body
