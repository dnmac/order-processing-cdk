#!/bin/bash

# LocalStack initialization script
# This runs automatically when LocalStack starts

set -e

echo " Initializing LocalStack resources..."

# Set AWS endpoint and region
export AWS_ENDPOINT_URL=http://localhost:4566
export AWS_DEFAULT_REGION=us-east-1
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test

# Wait for LocalStack to be ready
echo " Waiting for LocalStack to be ready..."
awslocal dynamodb list-tables || sleep 2

# Create DynamoDB table
echo " Creating DynamoDB table..."
awslocal dynamodb create-table \
    --table-name techtest-orders \
    --attribute-definitions \
        AttributeName=orderId,AttributeType=S \
    --key-schema \
        AttributeName=orderId,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --stream-specification \
        StreamEnabled=true,StreamViewType=NEW_AND_OLD_IMAGES \
    --region us-east-1 || echo "Table might already exist"

# Enable TTL on the table
echo " Enabling TTL..."
awslocal dynamodb update-time-to-live \
    --table-name techtest-orders \
    --time-to-live-specification \
        Enabled=true,AttributeName=expiresAt \
    --region us-east-1 || true

# Create SNS topic
echo " Creating SNS topic..."
TOPIC_ARN=$(awslocal sns create-topic \
    --name techtest-order-notifications \
    --region us-east-1 \
    --query 'TopicArn' \
    --output text)
echo "Topic ARN: $TOPIC_ARN"

# Create SQS queue for DLQ
echo " Creating DLQ..."
DLQ_URL=$(awslocal sqs create-queue \
    --queue-name techtest-orders-dlq \
    --region us-east-1 \
    --query 'QueueUrl' \
    --output text)
echo "DLQ URL: $DLQ_URL"

# Get DLQ ARN
DLQ_ARN=$(awslocal sqs get-queue-attributes \
    --queue-url "$DLQ_URL" \
    --attribute-names QueueArn \
    --region us-east-1 \
    --query 'Attributes.QueueArn' \
    --output text)
echo "DLQ ARN: $DLQ_ARN"

# Get DynamoDB Stream ARN
STREAM_ARN=$(awslocal dynamodb describe-table \
    --table-name techtest-orders \
    --region us-east-1 \
    --query 'Table.LatestStreamArn' \
    --output text)
echo "Stream ARN: $STREAM_ARN"

# Package Lambda functions
echo " Packaging Lambda functions..."
cd /tmp/lambdas || exit 1

# Create CreateOrder Lambda
echo "Creating CreateOrder Lambda..."
zip -q /tmp/create_order.zip create_order.py __init__.py || true

# Create ProcessOrder Lambda
echo "Creating ProcessOrder Lambda..."
zip -q /tmp/process_order.zip process_order.py __init__.py || true

# Create IAM role for Lambda (LocalStack doesn't enforce IAM)
echo " Creating IAM role..."
ROLE_ARN=$(awslocal iam create-role \
    --role-name lambda-execution-role \
    --assume-role-policy-document '{
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Principal": {
            "Service": "lambda.amazonaws.com"
          },
          "Action": "sts:AssumeRole"
        }
      ]
    }' \
    --query 'Role.Arn' \
    --output text 2>/dev/null || echo "arn:aws:iam::000000000000:role/lambda-execution-role")
echo "Role ARN: $ROLE_ARN"

# Create CreateOrder Lambda function
echo " Creating CreateOrder Lambda function..."
awslocal lambda create-function \
    --function-name techtest-create-order \
    --runtime python3.12 \
    --role "$ROLE_ARN" \
    --handler create_order.handler \
    --zip-file fileb:///tmp/create_order.zip \
    --environment "Variables={TABLE_NAME=techtest-orders,TTL_DAYS=7}" \
    --region us-east-1 || echo "CreateOrder Lambda might already exist"

# Create ProcessOrder Lambda function
echo " Creating ProcessOrder Lambda function..."
awslocal lambda create-function \
    --function-name techtest-process-order \
    --runtime python3.12 \
    --role "$ROLE_ARN" \
    --handler process_order.handler \
    --zip-file fileb:///tmp/process_order.zip \
    --environment "Variables={TABLE_NAME=techtest-orders,TOPIC_ARN=$TOPIC_ARN}" \
    --region us-east-1 || echo "ProcessOrder Lambda might already exist"

# Create event source mapping for DynamoDB Streams
echo " Creating DynamoDB Stream event source mapping..."
awslocal lambda create-event-source-mapping \
    --function-name techtest-process-order \
    --event-source-arn "$STREAM_ARN" \
    --starting-position TRIM_HORIZON \
    --batch-size 10 \
    --maximum-retry-attempts 3 \
    --maximum-record-age-in-seconds 3600 \
    --bisect-batch-on-function-error \
    --destination-config "OnFailure={Destination=$DLQ_ARN}" \
    --region us-east-1 2>/dev/null || echo "Event source mapping might already exist"

echo ""
echo "[OK] LocalStack initialization complete!"
echo ""
echo " Resources created:"
echo "  - DynamoDB Table: techtest-orders"
echo "  - SNS Topic: $TOPIC_ARN"
echo "  - SQS DLQ: $DLQ_URL"
echo "  - Lambda: techtest-create-order"
echo "  - Lambda: techtest-process-order"
echo "  - Stream Mapping: $STREAM_ARN -> techtest-process-order"
echo ""
echo " Ready to create orders!"
