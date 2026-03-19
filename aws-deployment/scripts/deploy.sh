#!/bin/bash
set -e

# Genetic Report Generation System - Main Deployment Script
# This script automates the deployment of the entire system to AWS

echo "================================================"
echo "Genetic Report Generation System - Deployment"
echo "================================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TERRAFORM_DIR="$SCRIPT_DIR/../terraform"
DATABASE_DIR="$SCRIPT_DIR/../database"
LAMBDA_DIR="$SCRIPT_DIR/../lambda"
DOCKER_DIR="$PROJECT_ROOT"

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    print_info "Checking prerequisites..."

    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        print_error "AWS CLI is not installed. Please install it first."
        exit 1
    fi

    # Check Terraform
    if ! command -v terraform &> /dev/null; then
        print_error "Terraform is not installed. Please install it first."
        exit 1
    fi

    # Check Docker
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install it first."
        exit 1
    fi

    # Check Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is not installed. Please install it first."
        exit 1
    fi

    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        print_error "AWS credentials are not configured. Please run 'aws configure'."
        exit 1
    fi

    print_info "All prerequisites met!"
}

# Initialize Terraform
init_terraform() {
    print_info "Initializing Terraform..."
    cd "$TERRAFORM_DIR"

    # Check if terraform.tfvars exists
    if [ ! -f "terraform.tfvars" ]; then
        print_warning "terraform.tfvars not found. Creating from example..."
        cp terraform.tfvars.example terraform.tfvars
        print_warning "Please edit terraform.tfvars with your values before continuing."
        read -p "Press Enter when you're ready to continue..."
    fi

    terraform init
    print_info "Terraform initialized successfully!"
}

# Plan Terraform deployment
plan_terraform() {
    print_info "Planning Terraform deployment..."
    cd "$TERRAFORM_DIR"
    terraform plan -out=tfplan
    print_info "Terraform plan created. Review the plan above."
}

# Apply Terraform configuration
apply_terraform() {
    print_info "Applying Terraform configuration..."
    cd "$TERRAFORM_DIR"

    # Apply the plan
    terraform apply tfplan

    # Get outputs
    print_info "Fetching Terraform outputs..."
    ECR_REPO_URL=$(terraform output -raw ecr_repository_url)
    RDS_ENDPOINT=$(terraform output -raw rds_endpoint)
    INPUT_BUCKET=$(terraform output -raw input_bucket_name)
    OUTPUT_BUCKET=$(terraform output -raw output_bucket_name)
    GWAS_BUCKET=$(terraform output -raw gwas_data_bucket_name)
    DB_SECRET_ARN=$(terraform output -raw rds_secret_arn)

    # Export for use in other functions
    export ECR_REPO_URL INPUT_BUCKET OUTPUT_BUCKET GWAS_BUCKET DB_SECRET_ARN RDS_ENDPOINT

    print_info "Infrastructure deployed successfully!"
}

# Build and push Docker image
build_and_push_docker() {
    print_info "Building and pushing Docker image..."

    if [ -z "$ECR_REPO_URL" ]; then
        print_error "ECR_REPO_URL not set. Run Terraform apply first."
        exit 1
    fi

    # Get AWS region and account ID
    AWS_REGION=$(echo "$ECR_REPO_URL" | cut -d'.' -f4)
    AWS_ACCOUNT_ID=$(echo "$ECR_REPO_URL" | cut -d'.' -f1 | cut -d'/' -f1)

    # Login to ECR
    print_info "Logging in to ECR..."
    aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$ECR_REPO_URL"

    # Build Docker image
    print_info "Building Docker image..."
    cd "$DOCKER_DIR"
    docker build -f infra/Dockerfile -t genetic-reports:latest .

    # Tag and push
    docker tag genetic-reports:latest "$ECR_REPO_URL:latest"
    docker tag genetic-reports:latest "$ECR_REPO_URL:$(date +%Y%m%d-%H%M%S)"

    print_info "Pushing Docker image to ECR..."
    docker push "$ECR_REPO_URL:latest"
    docker push "$ECR_REPO_URL:$(date +%Y%m%d-%H%M%S)"

    print_info "Docker image pushed successfully!"
}

# Upload GWAS data to S3
upload_gwas_data() {
    print_info "Uploading GWAS data to S3..."

    if [ -z "$GWAS_BUCKET" ]; then
        print_error "GWAS_BUCKET not set. Run Terraform apply first."
        exit 1
    fi

    GWAS_FILE="$PROJECT_ROOT/gwas_catalog_v1.0.2-associations_e114_r2025-07-10.tsv"

    if [ ! -f "$GWAS_FILE" ]; then
        print_warning "GWAS catalog file not found at $GWAS_FILE"
        print_warning "Skipping GWAS data upload. Please upload manually later."
        return
    fi

    aws s3 cp "$GWAS_FILE" "s3://$GWAS_BUCKET/gwas_catalog.tsv"
    print_info "GWAS data uploaded successfully!"
}

# Run database migrations
run_database_migrations() {
    print_info "Running database migrations..."

    if [ -z "$DB_SECRET_ARN" ] || [ -z "$RDS_ENDPOINT" ]; then
        print_error "Database credentials not available. Run Terraform apply first."
        exit 1
    fi

    # Get DB credentials from Secrets Manager
    print_info "Fetching database credentials..."
    DB_CREDS=$(aws secretsmanager get-secret-value --secret-id "$DB_SECRET_ARN" --query SecretString --output text)
    DB_HOST=$(echo "$DB_CREDS" | python3 -c "import sys, json; print(json.load(sys.stdin)['host'])")
    DB_NAME=$(echo "$DB_CREDS" | python3 -c "import sys, json; print(json.load(sys.stdin)['dbname'])")
    DB_USER=$(echo "$DB_CREDS" | python3 -c "import sys, json; print(json.load(sys.stdin)['username'])")
    DB_PASS=$(echo "$DB_CREDS" | python3 -c "import sys, json; print(json.load(sys.stdin)['password'])")

    # Check if psql is available
    if ! command -v psql &> /dev/null; then
        print_warning "psql is not installed. Skipping database migrations."
        print_warning "Please run migrations manually using the scripts in $DATABASE_DIR/migrations/"
        return
    fi

    # Run migrations
    export PGPASSWORD="$DB_PASS"

    print_info "Running migration: schema.sql"
    psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -f "$DATABASE_DIR/schema.sql"

    print_info "Database migrations completed successfully!"
}

# Package Lambda function
package_lambda() {
    print_info "Packaging Lambda function..."

    mkdir -p "$LAMBDA_DIR"
    cd "$LAMBDA_DIR"

    # Copy Lambda function
    cp "$PROJECT_ROOT/infra/lambda_fargate_caller.py" .

    # Create deployment package
    if [ -f lambda_package.zip ]; then
        rm lambda_package.zip
    fi

    zip -r lambda_package.zip lambda_fargate_caller.py

    print_info "Lambda function packaged successfully!"
}

# Update API keys in Secrets Manager
update_api_keys() {
    print_info "Updating API keys in Secrets Manager..."

    # Get secret ARNs from Terraform
    cd "$TERRAFORM_DIR"
    ANTHROPIC_SECRET_ARN=$(terraform output -raw anthropic_secret_arn)
    GEMINI_SECRET_ARN=$(terraform output -raw gemini_secret_arn)

    print_warning "Please update the API keys in AWS Secrets Manager:"
    echo ""
    echo "  Anthropic API Key:"
    echo "    aws secretsmanager put-secret-value --secret-id $ANTHROPIC_SECRET_ARN --secret-string \"YOUR_KEY\""
    echo ""
    echo "  Gemini API Key:"
    echo "    aws secretsmanager put-secret-value --secret-id $GEMINI_SECRET_ARN --secret-string \"YOUR_KEY\""
    echo ""
}

# Main deployment flow
main() {
    print_info "Starting deployment process..."
    echo ""

    # Check prerequisites
    check_prerequisites
    echo ""

    # Ask for confirmation
    read -p "Do you want to proceed with the deployment? (yes/no): " -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]es$ ]]; then
        print_warning "Deployment cancelled."
        exit 0
    fi

    # Initialize Terraform
    init_terraform
    echo ""

    # Plan Terraform
    plan_terraform
    echo ""

    # Confirm apply
    read -p "Do you want to apply this Terraform plan? (yes/no): " -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]es$ ]]; then
        print_warning "Deployment cancelled."
        exit 0
    fi

    # Apply Terraform
    apply_terraform
    echo ""

    # Package Lambda
    package_lambda
    echo ""

    # Build and push Docker image
    build_and_push_docker
    echo ""

    # Upload GWAS data
    upload_gwas_data
    echo ""

    # Run database migrations
    run_database_migrations
    echo ""

    # Print API key update instructions
    update_api_keys
    echo ""

    # Print deployment summary
    print_info "================================================"
    print_info "Deployment completed successfully!"
    print_info "================================================"
    echo ""
    print_info "Next steps:"
    echo "  1. Update API keys in AWS Secrets Manager (see commands above)"
    echo "  2. Test the API endpoint"
    echo "  3. Monitor CloudWatch logs for any issues"
    echo ""
    print_info "Deployment outputs have been saved in Terraform outputs."
    echo ""
}

# Run main function
main "$@"
