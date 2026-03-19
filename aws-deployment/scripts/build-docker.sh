#!/bin/bash
set -e

# Build and push Docker image to ECR

echo "Building and pushing Docker image to ECR..."

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TERRAFORM_DIR="$SCRIPT_DIR/../terraform"

# Get ECR repository URL from Terraform
cd "$TERRAFORM_DIR"
ECR_REPO_URL=$(terraform output -raw ecr_repository_url 2>/dev/null)

if [ -z "$ECR_REPO_URL" ]; then
    echo "Error: Could not get ECR repository URL from Terraform."
    echo "Please run 'terraform apply' first."
    exit 1
fi

# Extract AWS region from ECR URL
AWS_REGION=$(echo "$ECR_REPO_URL" | cut -d'.' -f4)

echo "ECR Repository: $ECR_REPO_URL"
echo "AWS Region: $AWS_REGION"

# Login to ECR
echo "Logging in to ECR..."
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$ECR_REPO_URL"

# Build Docker image
echo "Building Docker image..."
cd "$PROJECT_ROOT"
docker build -f infra/Dockerfile -t genetic-reports:latest .

# Tag image
echo "Tagging image..."
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
docker tag genetic-reports:latest "$ECR_REPO_URL:latest"
docker tag genetic-reports:latest "$ECR_REPO_URL:$TIMESTAMP"

# Push image
echo "Pushing image to ECR..."
docker push "$ECR_REPO_URL:latest"
docker push "$ECR_REPO_URL:$TIMESTAMP"

echo "Docker image pushed successfully!"
echo "  Latest: $ECR_REPO_URL:latest"
echo "  Tagged: $ECR_REPO_URL:$TIMESTAMP"
