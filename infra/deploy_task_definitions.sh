#!/bin/bash
# Script to deploy ECS task definitions for report generation containers

set -e

# Configuration
AWS_REGION="us-east-1"
AWS_ACCOUNT_ID="339712911975"

echo "=== Deploying ECS Task Definitions ==="
echo "AWS Account: $AWS_ACCOUNT_ID"
echo "Region: $AWS_REGION"
echo ""

# Check if AWS CLI is configured
if ! aws sts get-caller-identity > /dev/null 2>&1; then
    echo "Error: AWS CLI not configured or no valid credentials"
    exit 1
fi

# Create CloudWatch log groups first
echo "=== Creating CloudWatch Log Groups ==="
aws logs create-log-group --log-group-name /ecs/report-generator-json --region $AWS_REGION || echo "Log group /ecs/report-generator-json already exists"
aws logs create-log-group --log-group-name /ecs/report-generator-pdf --region $AWS_REGION || echo "Log group /ecs/report-generator-pdf already exists"

# Check if IAM roles exist (optional - will warn if they don't exist)
echo "=== Checking IAM Roles ==="
if aws iam get-role --role-name ecsTaskExecutionRole > /dev/null 2>&1; then
    echo "✓ ecsTaskExecutionRole exists"
else
    echo "⚠️  Warning: ecsTaskExecutionRole does not exist. You'll need to create it."
    echo "   You can create it with: aws iam create-role --role-name ecsTaskExecutionRole --assume-role-policy-document file://ecs-task-execution-role-policy.json"
fi

if aws iam get-role --role-name ecsTaskRole > /dev/null 2>&1; then
    echo "✓ ecsTaskRole exists"
else
    echo "⚠️  Warning: ecsTaskRole does not exist. You'll need to create it."
    echo "   You can create it with: aws iam create-role --role-name ecsTaskRole --assume-role-policy-document file://ecs-task-role-policy.json"
fi

# Register JSON task definition
echo ""
echo "=== Registering JSON Task Definition ==="
if [ -f "json-task-definition.json" ]; then
    aws ecs register-task-definition --cli-input-json file://json-task-definition.json --region $AWS_REGION
    echo "✓ JSON task definition registered successfully"
else
    echo "Error: json-task-definition.json not found"
    exit 1
fi

# Register PDF task definition
echo ""
echo "=== Registering PDF Task Definition ==="
if [ -f "pdf-task-definition.json" ]; then
    aws ecs register-task-definition --cli-input-json file://pdf-task-definition.json --region $AWS_REGION
    echo "✓ PDF task definition registered successfully"
else
    echo "Error: pdf-task-definition.json not found"
    exit 1
fi

# Create ECS cluster if it doesn't exist
echo ""
echo "=== Creating ECS Cluster ==="
if aws ecs describe-clusters --clusters report-generation-cluster --region $AWS_REGION > /dev/null 2>&1; then
    echo "✓ ECS cluster 'report-generation-cluster' already exists"
else
    aws ecs create-cluster --cluster-name report-generation-cluster --region $AWS_REGION
    echo "✓ ECS cluster 'report-generation-cluster' created successfully"
fi

echo ""
echo "=== Deployment Summary ==="
echo "✓ CloudWatch log groups created"
echo "✓ Task definitions registered"
echo "✓ ECS cluster ready"
echo ""
echo "Next steps:"
echo "1. Ensure your ECR containers are built and pushed"
echo "2. Configure your Lambda function with the correct environment variables"
echo "3. Set up VPC subnets and security groups for Fargate tasks"
echo ""
echo "Task definitions created:"
echo "- report-generator-json (1024 CPU, 2048 MB memory)"
echo "- report-generator-pdf (512 CPU, 1024 MB memory)"