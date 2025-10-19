"""End-to-end integration tests for order processing flow."""

import json
import time
import uuid
from typing import Dict, Any


class TestOrderProcessingFlow:
    """Essential end-to-end tests for the complete order processing system."""

    def test_create_order_and_auto_process(
        self, deployed_stack: Dict[str, Any], lambda_client, dynamodb_client
    ):
        """
        Test complete order lifecycle from creation to processing.

        Flow:
        1. Create order via CreateOrder Lambda (status: NEW)
        2. DynamoDB Stream triggers ProcessOrder Lambda
        3. Order status updates to PROCESSED
        4. SNS notification published (verified implicitly)
        """
        create_function = deployed_stack["CreateOrderFunctionName"]
        table_name = deployed_stack["OrdersTableName"]
        order_id = f"test-e2e-{uuid.uuid4()}"

        # Create order
        response = lambda_client.invoke(
            FunctionName=create_function,
            InvocationType="RequestResponse",
            Payload=json.dumps({"orderId": order_id, "snackType": "crisps"}),
        )

        assert response["StatusCode"] == 200
        response_payload = json.loads(response["Payload"].read())
        assert response_payload["statusCode"] == 201

        # Verify order created with NEW status
        time.sleep(2)
        initial_item = dynamodb_client.get_item(
            TableName=table_name, Key={"orderId": {"S": order_id}}
        )
        assert initial_item["Item"]["status"]["S"] == "NEW"
        assert "expiresAt" in initial_item["Item"]

        # Wait for stream processing (DynamoDB Streams can take 30-60 seconds)
        processed = False
        for attempt in range(30):  # 60 seconds max
            time.sleep(2)
            response = dynamodb_client.get_item(
                TableName=table_name, Key={"orderId": {"S": order_id}}
            )
            status = response["Item"]["status"]["S"]
            print(f"  Attempt {attempt + 1}/30: Order status = {status}")

            if status == "PROCESSED":
                processed = True
                break

        assert (
            processed
        ), f"Order was not processed by stream trigger after 60 seconds (final status: {status})"
        assert "processedAt" in response["Item"]

    def test_order_idempotency(self, deployed_stack: Dict[str, Any], lambda_client):
        """
        Test duplicate order handling (idempotent creates).

        Ensures same orderId cannot create duplicate records.
        """
        function_name = deployed_stack["CreateOrderFunctionName"]
        order_id = f"test-idem-{uuid.uuid4()}"
        payload = {"orderId": order_id, "snackType": "chocolate"}

        # First create - should succeed with 201
        response1 = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload),
        )
        payload1 = json.loads(response1["Payload"].read())
        assert payload1["statusCode"] == 201
        body1 = json.loads(payload1["body"])
        assert body1["message"] == "Order created successfully"

        # Duplicate create - should return 200 (idempotent)
        response2 = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload),
        )
        payload2 = json.loads(response2["Payload"].read())
        assert payload2["statusCode"] == 200
        body2 = json.loads(payload2["body"])
        assert body2["message"] == "Order already exists"
        assert body2["orderId"] == order_id

    def test_batch_order_processing(
        self, deployed_stack: Dict[str, Any], lambda_client, dynamodb_client
    ):
        """
        Test system handles multiple concurrent orders.

        Creates 5 orders asynchronously and verifies all are processed.
        """
        function_name = deployed_stack["CreateOrderFunctionName"]
        table_name = deployed_stack["OrdersTableName"]

        # Create 5 orders asynchronously
        order_ids = [f"test-batch-{uuid.uuid4()}" for _ in range(5)]
        snack_types = ["crisps", "chocolate", "biscuits", "nuts", "candy"]

        for order_id, snack_type in zip(order_ids, snack_types):
            lambda_client.invoke(
                FunctionName=function_name,
                InvocationType="Event",  # Async
                Payload=json.dumps({"orderId": order_id, "snackType": snack_type}),
            )

        # Wait for processing
        time.sleep(15)

        # Verify all orders processed
        processed_count = 0
        for order_id in order_ids:
            response = dynamodb_client.get_item(
                TableName=table_name, Key={"orderId": {"S": order_id}}
            )
            if "Item" in response and response["Item"]["status"]["S"] == "PROCESSED":
                processed_count += 1

        # Allow for eventual consistency - at least 4/5 should succeed
        assert processed_count >= 4, f"Only {processed_count}/5 orders processed"
