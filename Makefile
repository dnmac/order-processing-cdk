.PHONY: help install test test-unit test-cdk test-integration test-all lint clean synth deploy destroy logs-create logs-process invoke-create check-order sandbox-start sandbox-stop sandbox-create-order sandbox-view-orders sandbox-watch-sns sandbox-dlq sandbox-clean

# Default target
help:
	@echo "Available targets:"
	@echo ""
	@echo "Setup:"
	@echo "  make setup                  - Complete setup (venv + dependencies + AWS + CDK bootstrap)"
	@echo "  make install                - Create venv and install dependencies only"
	@echo "  make setup-aws              - AWS setup only (credentials + CDK bootstrap)"
	@echo ""
	@echo "Testing:"
	@echo "  make test                   - Run unit tests only (default)"
	@echo "  make test-unit              - Run Lambda unit tests"
	@echo "  make test-cdk               - Run CDK infrastructure tests (no deployment)"
	@echo "  make test-integration       - Run integration tests (deploys to AWS)"
	@echo "  make test-all               - Run all tests (unit + CDK + integration)"
	@echo "  make test-verbose           - Run tests with verbose output"
	@echo "  make test-coverage          - Run tests with coverage report"
	@echo ""
	@echo "LocalStack Sandbox (Docker):"
	@echo "  make sandbox-start          - Start LocalStack and initialize resources"
	@echo "  make sandbox-stop           - Stop LocalStack"
	@echo "  make sandbox-create-order   - Create a test order interactively"
	@echo "  make sandbox-view-orders    - View all orders in DynamoDB"
	@echo "  make sandbox-watch-orders   - Watch orders in real-time (auto-refresh)"
	@echo "  make sandbox-watch-sns      - Monitor SNS notifications"
	@echo "  make sandbox-dlq            - Check Dead Letter Queue"
	@echo "  make sandbox-logs           - View LocalStack logs"
	@echo "  make sandbox-clean          - Stop and remove all sandbox resources"
	@echo ""
	@echo "CDK Operations:"
	@echo "  make synth                  - Synthesize CloudFormation template"
	@echo "  make deploy                 - Deploy the CDK stack to AWS"
	@echo "  make destroy                - Destroy the CDK stack from AWS"
	@echo ""
	@echo "AWS Debugging:"
	@echo "  make logs-create            - Tail CreateOrder Lambda logs"
	@echo "  make logs-process           - Tail ProcessOrder Lambda logs"
	@echo "  make invoke-create          - Invoke CreateOrder with test payload"
	@echo "  make check-order ORDER_ID=<id> - Check order status in DynamoDB"
	@echo "  make check-dlq              - Check DLQ message count"
	@echo ""
	@echo "Maintenance:"
	@echo "  make lint                   - Run code quality checks (ruff/black)"
	@echo "  make clean                  - Remove generated files and venv"

# Complete setup - everything in one command
setup:
	@echo "================================================================================"
	@echo "COMPLETE SETUP"
	@echo "================================================================================"
	@echo ""
	@echo "This will set up everything you need to get started:"
	@echo "  1. Python virtual environment"
	@echo "  2. Install dependencies"
	@echo "  3. Configure AWS credentials"
	@echo "  4. Bootstrap CDK"
	@echo ""
	@$(MAKE) install
	@echo ""
	@$(MAKE) setup-aws
	@echo ""
	@echo "================================================================================"
	@echo "SETUP COMPLETE - READY TO USE"
	@echo "================================================================================"
	@echo ""
	@echo "Try these commands:"
	@echo "  make sandbox-start       # Run locally with LocalStack (no AWS)"
	@echo "  make test-unit           # Run unit tests"
	@echo "  make deploy              # Deploy to AWS"
	@echo ""

# Virtual environment setup
.venv:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip

# Install dependencies
install: .venv
	.venv/bin/pip install -r requirements.txt
	@echo "[OK] Installation complete. Activate with: source .venv/bin/activate"

# Run tests
test: test-unit
	@echo "[OK] Unit tests complete. Run 'make test-cdk' or 'make test-integration' for infrastructure tests."

test-unit:
	@echo "Running Lambda unit tests..."
	.venv/bin/pytest -q tests/test_create_order.py tests/test_process_order.py

test-cdk:
	@echo "Running CDK infrastructure tests (no deployment)..."
	.venv/bin/pytest -q tests/test_cdk_stack.py

test-integration:
	@echo "[WARN]  WARNING: This will deploy a temporary stack to AWS and incur costs."
	@echo "Running integration tests (deploys to AWS)..."
	.venv/bin/pytest -v tests/integration/ -s

test-all:
	@echo "Running all tests (unit + CDK + integration)..."
	.venv/bin/pytest -v tests/

test-verbose:
	.venv/bin/pytest -v tests/

test-coverage:
	.venv/bin/pytest --cov=lambdas --cov-report=term-missing tests/test_create_order.py tests/test_process_order.py

# Code quality
lint:
	@echo "Running code quality checks..."
	.venv/bin/ruff check lambdas/ tests/ stacks/ sandbox/
	.venv/bin/black --check lambdas/ tests/ stacks/ sandbox/

# CDK commands
synth:
	@if command -v cdk >/dev/null 2>&1; then \
		. $$(pwd)/.venv/bin/activate && cdk synth; \
	elif command -v npx >/dev/null 2>&1; then \
		. $$(pwd)/.venv/bin/activate && npx cdk synth; \
	else \
		echo "[ERROR] CDK CLI not found. Install with: npm install -g aws-cdk"; \
		exit 1; \
	fi

# Complete AWS setup (credentials + bootstrap)
setup-aws:
	@echo "================================================================================"
	@echo "AWS SETUP WIZARD"
	@echo "================================================================================"
	@echo ""
	@echo "This will guide you through AWS credential setup and CDK bootstrapping."
	@echo ""
	@echo "STEP 1: AWS Credentials"
	@echo "--------------------------------------------------------------------------------"
	@if command -v aws >/dev/null 2>&1; then \
		echo "[OK] AWS CLI is installed"; \
		if aws sts get-caller-identity >/dev/null 2>&1; then \
			echo "[OK] AWS credentials already configured"; \
			aws sts get-caller-identity; \
		else \
			echo ""; \
			echo "AWS credentials not found. Let's configure them now."; \
			echo ""; \
			echo "Get your credentials from:"; \
			echo "https://console.aws.amazon.com/iam/home#/security_credentials"; \
			echo ""; \
			echo "NOTE: Use 'us-east-1' as the default region (recommended)"; \
			echo ""; \
			aws configure; \
		fi \
	else \
		echo "[ERROR] AWS CLI not installed"; \
		echo ""; \
		echo "Install from: https://aws.amazon.com/cli/"; \
		echo ""; \
		echo "Linux:"; \
		echo "  curl 'https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip' -o awscliv2.zip"; \
		echo "  unzip awscliv2.zip && sudo ./aws/install"; \
		echo ""; \
		echo "macOS:"; \
		echo "  brew install awscli"; \
		echo ""; \
		echo "Windows:"; \
		echo "  Download: https://awscli.amazonaws.com/AWSCLIV2.msi"; \
		echo ""; \
		exit 1; \
	fi
	@echo ""
	@echo "STEP 2: CDK Bootstrap"
	@echo "--------------------------------------------------------------------------------"
	@if aws sts get-caller-identity >/dev/null 2>&1; then \
		ACCOUNT=$$(aws sts get-caller-identity --query Account --output text); \
		REGION=$$(aws configure get region || echo "us-east-1"); \
		echo "Bootstrapping CDK in account $$ACCOUNT (region: $$REGION)..."; \
		echo ""; \
		echo "This is a one-time setup that creates:"; \
		echo "  - S3 bucket for CDK assets"; \
		echo "  - IAM roles for deployments"; \
		echo "  - ECR repository for Docker images"; \
		echo ""; \
		read -p "Continue? (y/N): " confirm; \
		if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
			. $$(pwd)/.venv/bin/activate && npx cdk bootstrap aws://$$ACCOUNT/$$REGION; \
			echo ""; \
			echo "[OK] CDK bootstrap complete for $$REGION"; \
		else \
			echo "Bootstrap skipped. Run 'make bootstrap' later."; \
		fi \
	else \
		echo "[ERROR] Cannot bootstrap without AWS credentials"; \
		exit 1; \
	fi
	@echo ""
	@echo "================================================================================"
	@echo "SETUP COMPLETE"
	@echo "================================================================================"
	@echo ""
	@echo "You can now run:"
	@echo "  make test-integration    # Deploy and test on AWS"
	@echo "  make deploy              # Deploy to AWS"
	@echo ""

bootstrap:
	@if command -v cdk >/dev/null 2>&1; then \
		. $$(pwd)/.venv/bin/activate && cdk bootstrap; \
	elif command -v npx >/dev/null 2>&1; then \
		. $$(pwd)/.venv/bin/activate && npx cdk bootstrap; \
	else \
		echo "[ERROR] CDK CLI not found. Install with: npm install -g aws-cdk"; \
		exit 1; \
	fi

deploy:
	@if command -v cdk >/dev/null 2>&1; then \
		. $$(pwd)/.venv/bin/activate && cdk deploy --require-approval never; \
	elif command -v npx >/dev/null 2>&1; then \
		. $$(pwd)/.venv/bin/activate && npx cdk deploy --require-approval never; \
	else \
		echo "[ERROR] CDK CLI not found. Install with: npm install -g aws-cdk"; \
		exit 1; \
	fi

destroy:
	@if command -v cdk >/dev/null 2>&1; then \
		. $$(pwd)/.venv/bin/activate && cdk destroy --force; \
	elif command -v npx >/dev/null 2>&1; then \
		. $$(pwd)/.venv/bin/activate && npx cdk destroy --force; \
	else \
		echo "[ERROR] CDK CLI not found. Install with: npm install -g aws-cdk"; \
		exit 1; \
	fi

# CloudWatch Logs
logs-create:
	aws logs tail /aws/lambda/techtest-create-order --follow

logs-process:
	aws logs tail /aws/lambda/techtest-process-order --follow

# Testing helpers
invoke-create:
	@echo "Invoking CreateOrder with test payload..."
	@aws lambda invoke \
		--function-name techtest-create-order \
		--cli-binary-format raw-in-base64-out \
		--payload '{"orderId":"test-order-$(shell date +%s)","snackType":"crisps"}' \
		/tmp/response.json > /dev/null
	@echo "Response:"
	@cat /tmp/response.json | python3 -m json.tool
	@rm /tmp/response.json

# Check order status (requires ORDER_ID environment variable)
check-order:
	@if [ -z "$(ORDER_ID)" ]; then \
		echo "[ERROR] Usage: make check-order ORDER_ID=test-order-123"; \
		exit 1; \
	fi
	@echo "Checking order: $(ORDER_ID)"
	@RESULT=$$(aws dynamodb get-item \
		--table-name techtest-orders \
		--key '{"orderId":{"S":"$(ORDER_ID)"}}' \
		--output json); \
	if [ -z "$$RESULT" ] || [ "$$RESULT" = "{}" ]; then \
		echo "[ERROR] Order not found: $(ORDER_ID)"; \
	else \
		echo "$$RESULT" | python3 -m json.tool; \
	fi

# Check DLQ message count
check-dlq:
	@aws sqs get-queue-attributes \
		--queue-url $$(aws sqs get-queue-url --queue-name techtest-orders-dlq --query 'QueueUrl' --output text) \
		--attribute-names ApproximateNumberOfMessages \
		--query 'Attributes.ApproximateNumberOfMessages' \
		--output text | xargs -I {} echo "DLQ Messages: {}"

# LocalStack Sandbox
sandbox-start:
	@echo " Starting LocalStack sandbox..."
	@command -v docker >/dev/null 2>&1 || { echo "[ERROR] Docker not found. Install Docker first."; exit 1; }
	@if command -v docker-compose >/dev/null 2>&1; then \
		docker-compose up -d; \
	else \
		docker compose up -d; \
	fi
	@echo " Waiting for LocalStack to initialize (30s)..."
	@sleep 30
	@echo "[OK] LocalStack is ready!"
	@echo ""
	@echo "Next steps:"
	@echo "  make sandbox-create-order   # Create test orders"
	@echo "  make sandbox-view-orders    # View orders in DynamoDB"
	@echo "  make sandbox-watch-sns      # Monitor SNS notifications"

sandbox-stop:
	@echo " Stopping LocalStack..."
	@if command -v docker-compose >/dev/null 2>&1; then \
		docker-compose stop; \
	else \
		docker compose stop; \
	fi

sandbox-create-order:
	@.venv/bin/python3 ./sandbox/create_order.py

sandbox-view-orders:
	@.venv/bin/python3 ./sandbox/view_orders.py

sandbox-watch-orders:
	@.venv/bin/python3 ./sandbox/view_orders.py --watch

sandbox-watch-sns:
	@.venv/bin/python3 ./sandbox/watch_sns.py

sandbox-dlq:
	@.venv/bin/python3 ./sandbox/watch_sns.py --dlq

sandbox-logs:
	@if command -v docker-compose >/dev/null 2>&1; then \
		docker-compose logs -f localstack; \
	else \
		docker compose logs -f localstack; \
	fi

sandbox-clean:
	@echo " Cleaning up LocalStack sandbox..."
	@if command -v docker-compose >/dev/null 2>&1; then \
		docker-compose down -v; \
	else \
		docker compose down -v; \
	fi
	@echo "[OK] Sandbox cleaned up"

# Clean up
clean:
	rm -rf .venv
	rm -rf cdk.out
	rm -rf .pytest_cache
	rm -rf __pycache__
	rm -rf lambdas/__pycache__
	rm -rf tests/__pycache__
	rm -rf tests/integration/__pycache__
	rm -rf stacks/__pycache__
	rm -rf .coverage
	rm -rf htmlcov
	rm -rf tests/__snapshots__
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "[OK] Cleanup complete"