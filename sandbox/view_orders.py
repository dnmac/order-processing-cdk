#!/usr/bin/env python3
"""View orders in LocalStack DynamoDB table."""

import sys
import boto3
from typing import List, Dict, Any

# Colors for terminal output
GREEN = "\033[0;32m"
BLUE = "\033[0;34m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
RED = "\033[0;31m"
BOLD = "\033[1m"
NC = "\033[0m"  # No Color


def get_dynamodb_client():
    """Create DynamoDB client pointing to LocalStack."""
    return boto3.client(
        "dynamodb",
        endpoint_url="http://localhost:4566",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )


def scan_orders() -> List[Dict[str, Any]]:
    """Scan all orders from DynamoDB table."""
    client = get_dynamodb_client()

    try:
        response = client.scan(TableName="techtest-orders")
        return response.get("Items", [])
    except Exception as e:
        print(f"{RED}[ERROR] Error scanning DynamoDB: {str(e)}{NC}")
        print(f"{YELLOW}Is LocalStack running? Start with: make sandbox-start{NC}")
        sys.exit(1)


def format_dynamodb_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Convert DynamoDB item format to plain Python dict."""
    result = {}
    for key, value in item.items():
        if "S" in value:
            result[key] = value["S"]
        elif "N" in value:
            result[key] = (
                int(value["N"]) if "." not in value["N"] else float(value["N"])
            )
        else:
            result[key] = str(value)
    return result


def print_order_table(orders: List[Dict[str, Any]]):
    """Print orders in a nice table format."""
    if not orders:
        print(f"{YELLOW} No orders found{NC}")
        print(f"\nCreate an order with: {GREEN}make sandbox-create-order{NC}")
        return

    print(f"\n{BOLD}{BLUE} Orders in DynamoDB{NC}\n")
    print(f"{CYAN}{'─' * 120}{NC}")
    print(
        f"{BOLD}{'Order ID':<30} {'Snack Type':<15} {'Status':<12} {'Created At':<25} {'Processed At':<25}{NC}"
    )
    print(f"{CYAN}{'─' * 120}{NC}")

    # Sort by createdAt (newest first)
    # Handle DynamoDB format where createdAt is {'S': 'timestamp'}
    def get_created_at(order):
        created = order.get("createdAt", {})
        if isinstance(created, dict):
            return created.get("S", "")
        return created

    sorted_orders = sorted(orders, key=get_created_at, reverse=True)

    for item in sorted_orders:
        order = format_dynamodb_item(item)
        order_id = order.get("orderId", "N/A")
        snack_type = order.get("snackType", "N/A")
        status = order.get("status", "N/A")
        created_at = (
            order.get("createdAt", "N/A")[:19] if "createdAt" in order else "N/A"
        )
        processed_at = (
            order.get("processedAt", "-")[:19] if "processedAt" in order else "-"
        )

        # Color code by status
        if status == "PROCESSED":
            status_colored = f"{GREEN}{status}{NC}"
        elif status == "NEW":
            status_colored = f"{YELLOW}{status}{NC}"
        else:
            status_colored = status

        print(
            f"{order_id:<30} {snack_type:<15} {status_colored:<21} {created_at:<25} {processed_at:<25}"
        )

    print(f"{CYAN}{'─' * 120}{NC}\n")

    # Summary statistics
    total = len(sorted_orders)
    new_count = sum(
        1 for o in sorted_orders if format_dynamodb_item(o).get("status") == "NEW"
    )
    processed_count = sum(
        1 for o in sorted_orders if format_dynamodb_item(o).get("status") == "PROCESSED"
    )

    print(f"{BOLD} Summary:{NC}")
    print(f"  Total orders: {total}")
    print(f"  {YELLOW}NEW:{NC} {new_count}")
    print(f"  {GREEN}PROCESSED:{NC} {processed_count}")

    if new_count > 0:
        print(
            f"\n{BLUE}[INFO]  Orders with NEW status will be processed by the DynamoDB Stream trigger.{NC}"
        )
        print(
            "   Wait a few seconds and run this script again to see them as PROCESSED."
        )


def get_order_by_id(order_id: str) -> Dict[str, Any]:
    """Get a specific order by ID."""
    client = get_dynamodb_client()

    try:
        response = client.get_item(
            TableName="techtest-orders", Key={"orderId": {"S": order_id}}
        )

        if "Item" not in response:
            print(f"{RED}[ERROR] Order not found: {order_id}{NC}")
            return None

        return format_dynamodb_item(response["Item"])
    except Exception as e:
        print(f"{RED}[ERROR] Error getting order: {str(e)}{NC}")
        return None


def print_order_details(order: Dict[str, Any]):
    """Print detailed information about a single order."""
    print(f"\n{BOLD}{BLUE} Order Details{NC}\n")
    print(f"{CYAN}{'─' * 60}{NC}")

    for key, value in order.items():
        if key == "status":
            if value == "PROCESSED":
                value = f"{GREEN}{value}{NC}"
            elif value == "NEW":
                value = f"{YELLOW}{value}{NC}"
        print(f"{BOLD}{key:20s}{NC}: {value}")

    print(f"{CYAN}{'─' * 60}{NC}\n")


def watch_mode():
    """Continuously watch for order updates."""
    import time

    print(f"{BLUE} Watch mode - Press Ctrl+C to exit{NC}\n")

    try:
        while True:
            # Clear screen
            print("\033[H\033[J", end="")

            orders = scan_orders()
            print_order_table(orders)

            print(f"\n{CYAN}Refreshing in 3 seconds...{NC}")
            time.sleep(3)
    except KeyboardInterrupt:
        print(f"\n{GREEN}[OK] Watch mode stopped{NC}")


def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        if sys.argv[1] == "--watch" or sys.argv[1] == "-w":
            watch_mode()
        elif sys.argv[1] == "--help" or sys.argv[1] == "-h":
            print(f"{BLUE}Usage:{NC}")
            print(f"  {sys.argv[0]}              - View all orders")
            print(f"  {sys.argv[0]} ORDER_ID     - View specific order")
            print(f"  {sys.argv[0]} --watch|-w   - Watch mode (auto-refresh)")
            print(f"  {sys.argv[0]} --help|-h    - Show this help")
        else:
            # Get specific order
            order = get_order_by_id(sys.argv[1])
            if order:
                print_order_details(order)
    else:
        # List all orders
        orders = scan_orders()
        print_order_table(orders)


if __name__ == "__main__":
    main()
