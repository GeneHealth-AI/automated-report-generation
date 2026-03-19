#!/bin/bash
# Simplified ECS setup script

set -e

AWS_REGION="us-east-2"

echo "=== Simplified ECS Setup ==="

# Create log groups
echo "Creating CloudWatch log groups..."
aws logs create-log-group --log-group-name /ecs/report-generator-json --region $AWS_REGION 2>/dev/null || echo "✓ JSON log group exists"
aws logs create-log-group --log-group-name /ecs/report-generator-pdf --region $AWS_REGION 2>/dev/null || echo "✓ PDF log group exists"

# Create ECS cluster
echo "Creating ECS cluster..."
aws ecs create-cluster --cluster-name report-generation-cluster --region $AWS_REGION 2>/dev/null || echo "✓ ECS cluster exists"

# Register task definitions
echo "Registering task definitions..."
if [ -f "json-task-definition.json" ]; then
    aws ecs register-task-definition --cli-input-json file://json-task-definition.json --region $AWS_REGION
    echo "✓ JSON task definition registered"
else
    echo "❌ json-task-definition.json not found"
    exit 1
fi

if [ -f "pdf-task-definition.json" ]; then
    aws ecs register-task-definition --cli-input-json file://pdf-task-definition.json --region $AWS_REGION
    echo "✓ PDF task definition registered"
else
    echo "❌ pdf-task-definition.json not found"
    exit 1
fi

echo ""
echo "=== Setup Complete! ==="
echo "✓ CloudWatch log groups created"
echo "✓ ECS cluster created"
echo "✓ Task definitions registered"
echo ""
echo "Next steps:"
echo "1. Verify your IAM roles exist:"
echo "   aws iam get-role --role-name ecsTaskExecutionRole"
echo "   aws iam get-role --role-name ecsTaskRole"
echo ""
echo "2. Get your VPC configuration:"
echo "   aws ec2 describe-subnets --query 'Subnets[?MapPublicIpOnLaunch==\`true\`].[SubnetId,AvailabilityZone]' --output table"
echo ""
echo "3. Build and push your containers:"
echo "   ./build_json_ecr.sh"