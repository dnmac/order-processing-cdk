# Order Processing System

Event-driven order processing using AWS CDK with DynamoDB Streams, Lambda, and SNS.

## Quick Start

### Complete Setup (One Command)

```bash
make setup
```

This single command will:
- Create Python virtual environment
- Install all dependencies
- Configure AWS credentials (interactive)
- Bootstrap CDK in your AWS account

After setup, try these:

**Local Testing (No AWS Required)**
```bash
make sandbox-start       # Start LocalStack
make sandbox-create-order
make sandbox-view-orders
```

**AWS Deployment**
```bash
make deploy              # Deploy to AWS
```

## Architecture

```
CreateOrder Lambda
     |
     v
DynamoDB Table (with Streams)
     |
     v
ProcessOrder Lambda
     |
     +--> SNS Topic (success)
     +--> SQS DLQ (failures)
```

**Flow:**
1. CreateOrder Lambda writes order to DynamoDB (status: NEW)
2. DynamoDB Stream triggers ProcessOrder Lambda
3. ProcessOrder updates status to PROCESSED
4. SNS notification published

## LocalStack Sandbox

Run the complete system locally with zero AWS costs.

```bash
# Start LocalStack (creates all resources automatically)
make sandbox-start

# Create orders
make sandbox-create-order

# View orders
make sandbox-view-orders
make sandbox-watch-orders      # Live updates

# Monitor SNS
make sandbox-watch-sns

# Check DLQ
make sandbox-dlq

# Stop
make sandbox-stop
make sandbox-clean             # Remove everything
```

## Testing

Three-layer testing pyramid (25 total tests):

**1. Lambda Unit Tests** (14 tests, fast, no AWS)
```bash
make test-unit
make test-coverage
```
Validates Lambda function logic, error handling, and edge cases.

**2. CDK Infrastructure Tests** (8 tests, fast, no AWS)
```bash
make test-cdk
```
Validates CloudFormation template has all required resources and correct configuration.

**3. Integration Tests** (3 tests, slow, deploys to AWS)
```bash
make test-integration
```
Deploys ephemeral stack, validates end-to-end order processing flow, auto-cleans up.

## Deploy to AWS

### Deploy and Test

```bash
make deploy                # Deploy infrastructure
make invoke-create         # Test CreateOrder Lambda
make logs-process          # View ProcessOrder logs
```

### Cleanup

```bash
make destroy               # Remove all AWS resources
```

## Common Commands

```bash
# Sandbox
make sandbox-start
make sandbox-create-order
make sandbox-view-orders

# Testing
make test-unit
make test-cdk
make test-integration

# AWS Deployment
make deploy
make destroy

# AWS Debugging
make invoke-create
make logs-create
make logs-process
make check-dlq

# Cleanup
make clean
```

## Project Structure

```
cdk_app/
├── Makefile                  # All commands
├── docker-compose.yml        # LocalStack
├── app.py                    # CDK entry point
├── stacks/
│   └── order_stack.py        # Infrastructure
├── lambdas/
│   ├── create_order.py       # Create orders
│   └── process_order.py      # Process orders
├── tests/
│   ├── test_*.py             # Unit tests
│   └── integration/          # Integration tests
└── sandbox/
    ├── create_order.py       # Interactive order creation
    ├── view_orders.py        # View orders
    └── watch_sns.py          # Monitor notifications
```

## CI/CD

GitHub Actions workflows:
- **PR Validation**: Runs unit tests, CDK tests, and synthesis on every PR (fast, no AWS costs)
- **Main Deploy**: Runs integration tests and deploys to dev after merge to main
- **Production Deploy**: Manual deployment to production via workflow dispatch

See `.github/workflows/` for details.

## Requirements

- **Python 3.12+**
- **Docker** (for LocalStack)
- **Node.js** (for AWS CDK): `npm install -g aws-cdk`
- **AWS CLI v2** (for AWS deployment): https://aws.amazon.com/cli/
- **AWS credentials** (for AWS deployment - configured via `aws configure`)

## Resources Created

| Resource | Name | Purpose |
|----------|------|---------|
| KMS Key | alias/techtest-orders | Encryption |
| DynamoDB | techtest-orders | Order storage + Streams |
| SNS Topic | techtest-order-notifications | Notifications |
| SQS Queue | techtest-orders-dlq | Failed events |
| Lambda | techtest-create-order | Create orders |
| Lambda | techtest-process-order | Process orders |

## Configuration

**Lambda A (CreateOrder):**
- Runtime: Python 3.12 (ARM64)
- Memory: 256 MB
- Timeout: 30s
- Env: TABLE_NAME, TTL_DAYS

**Lambda B (ProcessOrder):**
- Runtime: Python 3.12 (ARM64)
- Memory: 256 MB
- Timeout: 60s
- Env: TABLE_NAME, TOPIC_ARN
- Trigger: DynamoDB Stream (batch 10, max retries 3)

## Troubleshooting

**LocalStack won't start:**
```bash
docker ps
docker compose logs localstack
```

**Orders not processing:**
```bash
make sandbox-logs
```

**AWS deployment fails:**
```bash
# Check credentials
aws sts get-caller-identity

# Check CDK
cdk doctor
```

**Tests fail:**
```bash
# Run with verbose
make test-verbose
```

## Security Features

- Customer-managed KMS encryption (DynamoDB, SNS)
- Least-privilege IAM roles
- Point-in-Time Recovery enabled
- TTL for automatic data expiration (7 days)
- No PII in SNS notifications
- Idempotent operations (prevent duplicates)

## License

All rights reserved.
