#!/bin/bash
# Complete setup script for ECS infrastructure including IAM roles and task definitions

set -e

# Configuration
AWS_REGION="us-east-1"
AWS_ACCOUNT_ID="339712911975"

echo "=== Setting up ECS Infrastructure ==="
echo "AWS Account: $AWS_ACCOUNT_ID"
echo "Region: $AWS_REGION"
echo ""

# Check if AWS CLI is configured
if ! aws sts get-caller-identity > /dev/null 2>&1; then
    echo "Error: AWS CLI not configured or no valid credentials"
    exit 1
fi

# Create ECS Task Execution Role
echo "=== Creating ECS Task Execution Role ==="
if aws iam get-role --role-name ecsTaskExecutionRole > /dev/null 2>&1; then
    echo "✓ ecsTaskExecutionRole already exists"
else
    aws iam create-role \
        --role-name ecsTaskExecutionRole \
        --assume-role-policy-document file://ecs-task-execution-role-policy.json
    
    # Attach the AWS managed policy for ECS task execution
    aws iam attach-role-policy \
        --role-name ecsTaskExecutionRole \
        --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
    
    echo "✓ ecsTaskExecutionRole created and policy attached"
fi

# Create ECS Task Role (for the containers themselves)
echo ""
echo "=== Creating ECS Task Role ==="
if aws iam get-role --role-name ecsTaskRole > /dev/null 2>&1; then
    echo "✓ ecsTaskRole already exists"
else
    aws iam create-role \
        --role-name ecsTaskRole \
        --assume-role-policy-document file://ecs-task-role-policy.json
    
    # Create and attach custom policy for S3 access and EC2 termination
    cat > ecs-task-permissions.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:PutObject",
                "s3:DeleteObject",
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::*",
                "arn:aws:s3:::*/*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "ec2:TerminateInstances",
                "ec2:DescribeInstances"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": "arn:aws:logs:*:*:*"
        }
    ]
}
EOF
    
    aws iam put-role-policy \
        --role-name ecsTaskRole \
        --policy-name ECSTaskCustomPermissions \
        --policy-document file://ecs-task-permissions.json
    
    echo "✓ ecsTaskRole created with custom permissions"
fi

# Create CloudWatch log groups
echo ""
echo "=== Creating CloudWatch Log Groups ==="
aws logs create-log-group --log-group-name /ecs/report-generator-json --region $AWS_REGION || echo "✓ Log group /ecs/report-generator-json already exists"
aws logs create-log-group --log-group-name /ecs/report-generator-pdf --region $AWS_REGION || echo "✓ Log group /ecs/report-generator-pdf already exists"

# Create ECS cluster
echo ""
echo "=== Creating ECS Cluster ==="
if aws ecs describe-clusters --clusters report-generation-cluster --region $AWS_REGION > /dev/null 2>&1; then
    echo "✓ ECS cluster 'report-generation-cluster' already exists"
else
    aws ecs create-cluster --cluster-name report-generation-cluster --region $AWS_REGION
    echo "✓ ECS cluster 'report-generation-cluster' created successfully"
fi

# Wait a moment for roles to propagate
echo ""
echo "=== Waiting for IAM roles to propagate ==="
sleep 10

# Register task definitions
echo ""
echo "=== Registering Task Definitions ==="
if [ -f "json-task-definition.json" ]; then
    aws ecs register-task-definition --cli-input-json file://json-task-definition.json --region $AWS_REGION
    echo "✓ JSON task definition registered successfully"
else
    echo "Error: json-task-definition.json not found"
    exit 1
fi

if [ -f "pdf-task-definition.json" ]; then
    aws ecs register-task-definition --cli-input-json file://pdf-task-definition.json --region $AWS_REGION
    echo "✓ PDF task definition registered successfully"
else
    echo "Error: pdf-task-definition.json not found"
    exit 1
fi

# Clean up temporary files
rm -f ecs-task-permissions.json

echo ""
echo "=== Setup Complete! ==="
echo "✓ IAM roles created (ecsTaskExecutionRole, ecsTaskRole)"
echo "✓ CloudWatch log groups created"
echo "✓ ECS cluster created"
echo "✓ Task definitions registered"
echo ""
echo "Next steps:"
echo "1. Build and push your ECR containers:"
echo "   ./build_json_ecr.sh"
echo ""
echo "2. Get your VPC subnet IDs and security group ID:"
echo "   aws ec2 describe-subnets --query 'Subnets[?MapPublicIpOnLaunch==\`true\`].[SubnetId,AvailabilityZone]' --output table"
echo "   aws ec2 describe-security-groups --query 'SecurityGroups[?GroupName==\`default\`].GroupId' --output text"
echo ""
echo "3. Deploy your Lambda function with the correct environment variables"
echo ""
echo "Your task definitions are ready to use!"