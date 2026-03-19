#!/bin/bash
set -e

# Default Variables
REGION="us-east-1"
REPO_NAME="parabricks-pipeline"
TAG="latest"

echo "=== AWS ECR Build & Push Script ==="
echo "Dependencies: docker, aws-cli"

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "Error: aws cli not found."
    exit 1
fi

# Get Account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
if [ -z "$ACCOUNT_ID" ]; then
    echo "Error: Could not get AWS Account ID. Check your credentials."
    exit 1
fi

ECR_URL="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
FULL_IMAGE_NAME="${ECR_URL}/${REPO_NAME}:${TAG}"

echo "Region: $REGION"
echo "Account: $ACCOUNT_ID"
echo "Image: $FULL_IMAGE_NAME"

# Login to ECR
echo "Logging in to ECR..."
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ECR_URL"

# Create Repo if not exists (Optional)
echo "Ensuring repository exists..."
aws ecr describe-repositories --repository-names "$REPO_NAME" --region "$REGION" > /dev/null 2>&1 || \
    aws ecr create-repository --repository-name "$REPO_NAME" --region "$REGION"

# Build Image
echo "Building Docker Image..."
# We use -f Dockerfile.parabricks
docker build -t "$REPO_NAME" -f Dockerfile.parabricks .

# Tag Image
echo "Tagging Image..."
docker tag "$REPO_NAME:latest" "$FULL_IMAGE_NAME"

# Push Image
echo "Pushing Image to ECR (This may take a while)..."
docker push "$FULL_IMAGE_NAME"

echo "Success! Image available at: $FULL_IMAGE_NAME"
