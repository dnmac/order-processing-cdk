#!/usr/bin/env python3
"""Interactive script to create orders in LocalStack."""

import sys
import json
import time
import random
import boto3

# Colors for output
GREEN = "\033[0;32m"
BLUE = "\033[0;34m"
YELLOW = "\033[1;33m"
NC = "\033[0m"  # No Color


def get_lambda_client():
    """Create Lambda client pointing to LocalStack."""
    return boto3.client(
        "lambda",
        endpoint_url="http://localhost:4566",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )


def check_localstack():
    """Check if LocalStack is running."""
    try:
        import requests

        response = requests.get("http://localhost:4566/_localstack/health", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def main():
    """Main entry point."""
    print(f"{BLUE} Order Creation Tool{NC}\n")

    # Check if LocalStack is running
    if not check_localstack():
        print(f"{YELLOW}[WARN]  LocalStack is not running!{NC}")
        print("Start it with: make sandbox-start")
        sys.exit(1)

    # Get order details from user
    if len(sys.argv) > 1:
        order_id = sys.argv[1]
    else:
        order_id_input = input(
            "Enter Order ID (or press Enter for auto-generated): "
        ).strip()
        if order_id_input:
            order_id = order_id_input
        else:
            timestamp = int(time.time())
            random_num = random.randint(1000, 9999)
            order_id = f"order-{timestamp}-{random_num}"
            print(f"{GREEN}Generated Order ID: {order_id}{NC}")

    if len(sys.argv) > 2:
        snack_type = sys.argv[2]
    else:
        print("\nSnack Types:")
        print("  1) crisps")
        print("  2) chocolate")
        print("  3) biscuits")
        print("  4) nuts")
        print("  5) candy")
        snack_choice = input("Choose snack type (1-5 or type custom): ").strip()

        snack_map = {
            "1": "crisps",
            "2": "chocolate",
            "3": "biscuits",
            "4": "nuts",
            "5": "candy",
        }
        snack_type = snack_map.get(snack_choice, snack_choice)

    print(f"\n{BLUE}Creating order...{NC}")
    print(f"  Order ID: {order_id}")
    print(f"  Snack Type: {snack_type}\n")

    # Create payload
    payload = {"orderId": order_id, "snackType": snack_type}

    # Invoke Lambda
    try:
        client = get_lambda_client()
        response = client.invoke(
            FunctionName="techtest-create-order",
            InvocationType="RequestResponse",
            Payload=json.dumps(payload),
        )

        # Parse response
        response_payload = json.loads(response["Payload"].read())
        status_code = response_payload.get("statusCode")
        body = json.loads(response_payload.get("body", "{}"))

        print(f"{GREEN}[OK] Lambda Response:{NC}")
        print(f"  Status Code: {status_code}")
        print(f"  Body: {json.dumps(body, indent=2)}\n")

        if status_code == 201:
            print(f"{GREEN} Order created successfully!{NC}\n")
            print(f"{BLUE}What happens next:{NC}")
            print("  1. DynamoDB Stream detects the new order")
            print("  2. ProcessOrder Lambda is triggered automatically")
            print("  3. Order status changes from NEW → PROCESSED")
            print("  4. SNS notification is published\n")
            print(f"Check order status with: {GREEN}make sandbox-view-orders{NC}")
        elif status_code == 200:
            print(f"{YELLOW}[INFO]  Order already exists (idempotency){NC}")
        else:
            print(f"{YELLOW}[WARN]  Unexpected response{NC}")

    except Exception as e:
        print(f"{YELLOW}[ERROR] Error invoking Lambda: {str(e)}{NC}")
        print(f"\n{BLUE}Troubleshooting:{NC}")
        print("  - Is LocalStack running? (make sandbox-start)")
        print("  - Check logs: make sandbox-logs")
        sys.exit(1)


if __name__ == "__main__":
    main()
