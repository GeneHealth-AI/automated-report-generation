#!/bin/bash
# Script to build and push the Parabricks Genomics Docker image to AWS ECR

# AWS Configuration (Update these or set as env vars)
AWS_REGION=${AWS_REGION:-"us-east-1"}
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REPO_NAME=${REPO_NAME:-"parabricks-genomics-pipeline"}
IMAGE_TAG=${IMAGE_TAG:-"latest"}

# Full ECR Repository URI
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPO_NAME}"

echo "Building Docker image: ${REPO_NAME}:${IMAGE_TAG}..."
docker build -t "${REPO_NAME}:${IMAGE_TAG}" -f Dockerfile.parabricks .

echo "Logging in to Amazon ECR..."
aws ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# Create repository if it doesn't exist
aws ecr describe-repositories --repository-names "${REPO_NAME}" --region "${AWS_REGION}" || \
aws ecr create-repository --repository-name "${REPO_NAME}" --region "${AWS_REGION}"

echo "Tagging and Pushing image to ${ECR_URI}..."
docker tag "${REPO_NAME}:${IMAGE_TAG}" "${ECR_URI}:${IMAGE_TAG}"
docker push "${ECR_URI}:${IMAGE_TAG}"

echo "Success! Image pushed to ${ECR_URI}:${IMAGE_TAG}"
