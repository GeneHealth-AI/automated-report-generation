#!/bin/bash
# Commands for building and pushing ECR containers with relative paths

# Set your AWS region and account ID
AWS_REGION="us-east-2"  # Change to your preferred region
AWS_ACCOUNT_ID="339712911975"  # Your specific ECR account number

# Repository names
ECR_REPO_JSON="report-generator-json"
ECR_REPO_PDF="report-generator-pdf"

# Login to ECR
echo "=== Login to ECR ==="
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# Create repositories if they don't exist
echo "=== Creating ECR repositories if needed ==="
aws ecr describe-repositories --repository-names $ECR_REPO_JSON --region $AWS_REGION || \
    aws ecr create-repository --repository-name $ECR_REPO_JSON --region $AWS_REGION

aws ecr describe-repositories --repository-names $ECR_REPO_PDF --region $AWS_REGION || \
    aws ecr create-repository --repository-name $ECR_REPO_PDF --region $AWS_REGION

# Build and push JSON container
echo "=== Building JSON container ==="
docker build -t $ECR_REPO_JSON:latest -f Dockerfile.json .
docker tag $ECR_REPO_JSON:latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_JSON:latest
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_JSON:latest

# Build and push PDF container
echo "=== Building PDF container ==="
docker build -t $ECR_REPO_PDF:latest -f Dockerfile.pdf .
docker tag $ECR_REPO_PDF:latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_PDF:latest
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_PDF:latest

echo "=== Containers successfully built and pushed to ECR ==="
echo "JSON container: $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_JSON:latest"
echo "PDF container: $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_PDF:latest"