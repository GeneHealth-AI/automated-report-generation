#!/bin/bash

# Build script for Fargate report generation container

set -e

# Configuration
IMAGE_NAME="report-generator"
TAG="latest"
AWS_REGION="us-east-1"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPOSITORY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${IMAGE_NAME}"

echo "🏗️  Building Fargate Report Generation Container"
echo "================================================"
echo "Image: ${IMAGE_NAME}:${TAG}"
echo "ECR Repository: ${ECR_REPOSITORY}"
echo ""

# Build the Docker image
echo "📦 Building Docker image..."
docker build -t ${IMAGE_NAME}:${TAG} .

if [ $? -eq 0 ]; then
    echo "✅ Docker image built successfully"
else
    echo "❌ Docker build failed"
    exit 1
fi

# Tag for ECR
echo "🏷️  Tagging image for ECR..."
docker tag ${IMAGE_NAME}:${TAG} ${ECR_REPOSITORY}:${TAG}

# Login to ECR
echo "🔐 Logging into ECR..."
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_REPOSITORY}

# Create ECR repository if it doesn't exist
echo "📋 Ensuring ECR repository exists..."
aws ecr describe-repositories --repository-names ${IMAGE_NAME} --region ${AWS_REGION} 2>/dev/null || \
aws ecr create-repository --repository-name ${IMAGE_NAME} --region ${AWS_REGION}

# Push to ECR
echo "🚀 Pushing image to ECR..."
docker push ${ECR_REPOSITORY}:${TAG}

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Container successfully built and pushed to ECR!"
    echo "📍 Image URI: ${ECR_REPOSITORY}:${TAG}"
    echo ""
    echo "Next steps:"
    echo "1. Update your ECS task definition to use this image"
    echo "2. Configure your Lambda function to call the ECS task"
    echo "3. Set up appropriate IAM roles and networking"
else
    echo "❌ Failed to push to ECR"
    exit 1
fi