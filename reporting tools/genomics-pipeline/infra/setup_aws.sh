#!/bin/bash
set -euo pipefail

# Set up AWS infrastructure for the genomics pipeline:
# - SQS queue
# - Lambda function (SQS consumer -> EC2 launcher)
# - IAM roles
# - Security group

AWS_REGION="${AWS_REGION:-us-east-2}"
STACK_NAME="genomics-pipeline"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "=== Setting up AWS infrastructure for Genomics Pipeline ==="
echo "Region:  $AWS_REGION"
echo "Account: $AWS_ACCOUNT_ID"

# ---- 1. SQS Queue ----
echo "Creating SQS queue..."
QUEUE_URL=$(aws sqs create-queue \
    --queue-name "${STACK_NAME}-jobs" \
    --attributes '{
        "VisibilityTimeout": "900",
        "MessageRetentionPeriod": "86400",
        "ReceiveMessageWaitTimeSeconds": "20"
    }' \
    --region "$AWS_REGION" \
    --query 'QueueUrl' --output text)

QUEUE_ARN=$(aws sqs get-queue-attributes \
    --queue-url "$QUEUE_URL" \
    --attribute-names QueueArn \
    --query 'Attributes.QueueArn' --output text)

echo "  Queue URL: $QUEUE_URL"
echo "  Queue ARN: $QUEUE_ARN"

# ---- 2. IAM Role for EC2 Pipeline Instances ----
echo "Creating EC2 instance role..."
INSTANCE_ROLE_NAME="${STACK_NAME}-ec2-role"

aws iam create-role \
    --role-name "$INSTANCE_ROLE_NAME" \
    --assume-role-policy-document '{
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "ec2.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    }' 2>/dev/null || echo "  Role already exists"

# Attach policies: S3 access, ECR pull, CloudWatch logs
aws iam attach-role-policy --role-name "$INSTANCE_ROLE_NAME" \
    --policy-arn "arn:aws:iam::aws:policy/AmazonS3FullAccess" 2>/dev/null || true
aws iam attach-role-policy --role-name "$INSTANCE_ROLE_NAME" \
    --policy-arn "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly" 2>/dev/null || true
aws iam attach-role-policy --role-name "$INSTANCE_ROLE_NAME" \
    --policy-arn "arn:aws:iam::aws:policy/CloudWatchLogsFullAccess" 2>/dev/null || true

# Create instance profile
INSTANCE_PROFILE_NAME="${STACK_NAME}-ec2-profile"
aws iam create-instance-profile \
    --instance-profile-name "$INSTANCE_PROFILE_NAME" 2>/dev/null || true
aws iam add-role-to-instance-profile \
    --instance-profile-name "$INSTANCE_PROFILE_NAME" \
    --role-name "$INSTANCE_ROLE_NAME" 2>/dev/null || true

INSTANCE_PROFILE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:instance-profile/${INSTANCE_PROFILE_NAME}"
echo "  Instance Profile: $INSTANCE_PROFILE_ARN"

# ---- 3. IAM Role for Lambda ----
echo "Creating Lambda execution role..."
LAMBDA_ROLE_NAME="${STACK_NAME}-lambda-role"

aws iam create-role \
    --role-name "$LAMBDA_ROLE_NAME" \
    --assume-role-policy-document '{
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    }' 2>/dev/null || echo "  Role already exists"

# Lambda needs: EC2 launch, SQS read, IAM PassRole, CloudWatch
aws iam attach-role-policy --role-name "$LAMBDA_ROLE_NAME" \
    --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole" 2>/dev/null || true
aws iam attach-role-policy --role-name "$LAMBDA_ROLE_NAME" \
    --policy-arn "arn:aws:iam::aws:policy/AmazonEC2FullAccess" 2>/dev/null || true
aws iam attach-role-policy --role-name "$LAMBDA_ROLE_NAME" \
    --policy-arn "arn:aws:iam::aws:policy/AmazonSQSFullAccess" 2>/dev/null || true

# Allow Lambda to pass the EC2 role
aws iam put-role-policy \
    --role-name "$LAMBDA_ROLE_NAME" \
    --policy-name "PassEC2Role" \
    --policy-document "{
        \"Version\": \"2012-10-17\",
        \"Statement\": [{
            \"Effect\": \"Allow\",
            \"Action\": \"iam:PassRole\",
            \"Resource\": \"arn:aws:iam::${AWS_ACCOUNT_ID}:role/${INSTANCE_ROLE_NAME}\"
        }]
    }" 2>/dev/null || true

LAMBDA_ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/${LAMBDA_ROLE_NAME}"
echo "  Lambda Role: $LAMBDA_ROLE_ARN"

# ---- 4. Security Group ----
echo "Creating security group..."
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" \
    --query 'Vpcs[0].VpcId' --output text --region "$AWS_REGION")

SG_ID=$(aws ec2 create-security-group \
    --group-name "${STACK_NAME}-sg" \
    --description "Genomics pipeline EC2 instances" \
    --vpc-id "$VPC_ID" \
    --region "$AWS_REGION" \
    --query 'GroupId' --output text 2>/dev/null || \
    aws ec2 describe-security-groups \
        --filters "Name=group-name,Values=${STACK_NAME}-sg" \
        --query 'SecurityGroups[0].GroupId' --output text --region "$AWS_REGION")

# Allow outbound (default) - no inbound needed
echo "  Security Group: $SG_ID"

# Get a subnet
SUBNET_ID=$(aws ec2 describe-subnets \
    --filters "Name=vpc-id,Values=$VPC_ID" \
    --query 'Subnets[0].SubnetId' --output text --region "$AWS_REGION")
echo "  Subnet: $SUBNET_ID"

# ---- 5. Deploy Lambda ----
echo "Deploying Lambda function..."
LAMBDA_NAME="${STACK_NAME}-sqs-consumer"
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/genomics-pipeline:latest"

# Find GPU AMI (NVIDIA GPU-Optimized AMI or Deep Learning AMI)
AMI_ID=$(aws ec2 describe-images \
    --owners amazon \
    --filters "Name=name,Values=*Deep Learning Base GPU AMI*Amazon Linux 2*" \
              "Name=state,Values=available" \
    --query 'sort_by(Images, &CreationDate)[-1].ImageId' \
    --output text --region "$AWS_REGION" 2>/dev/null || echo "REPLACE_WITH_GPU_AMI_ID")

echo "  GPU AMI: $AMI_ID"

# Package Lambda
cd "$(dirname "$0")/../lambda"
zip -j /tmp/lambda_sqs_consumer.zip sqs_consumer.py

# Wait for role propagation
echo "  Waiting for IAM role propagation..."
sleep 10

aws lambda create-function \
    --function-name "$LAMBDA_NAME" \
    --runtime python3.12 \
    --handler sqs_consumer.lambda_handler \
    --role "$LAMBDA_ROLE_ARN" \
    --zip-file fileb:///tmp/lambda_sqs_consumer.zip \
    --timeout 60 \
    --memory-size 256 \
    --environment "Variables={
        ECR_IMAGE_URI=${ECR_URI},
        SUBNET_ID=${SUBNET_ID},
        SECURITY_GROUP_ID=${SG_ID},
        INSTANCE_PROFILE_ARN=${INSTANCE_PROFILE_ARN},
        AMI_ID=${AMI_ID},
        AWS_REGION=${AWS_REGION},
        REF_S3_URI=s3://entprises/ref/,
        STR_S3_URI=s3://exomeinputbucket/str_entprise.tar.gz,
        DEFAULT_INSTANCE_TYPE=g5.2xlarge
    }" \
    --region "$AWS_REGION" 2>/dev/null || \
aws lambda update-function-code \
    --function-name "$LAMBDA_NAME" \
    --zip-file fileb:///tmp/lambda_sqs_consumer.zip \
    --region "$AWS_REGION"

# ---- 6. Wire SQS -> Lambda ----
echo "Creating SQS -> Lambda event source mapping..."
aws lambda create-event-source-mapping \
    --function-name "$LAMBDA_NAME" \
    --event-source-arn "$QUEUE_ARN" \
    --batch-size 1 \
    --region "$AWS_REGION" 2>/dev/null || echo "  Event source mapping already exists"

echo ""
echo "=== Infrastructure Setup Complete ==="
echo ""
echo "To submit a job, send a message to SQS:"
echo ""
echo "  aws sqs send-message \\"
echo "    --queue-url $QUEUE_URL \\"
echo "    --message-body '{\"s3_input_dir\": \"s3://your-bucket/sample_001/\", \"sample_id\": \"sample_001\"}'"
echo ""
echo "To submit multiple jobs in parallel:"
echo ""
echo "  for dir in s3://bucket/sample_{001..010}/; do"
echo "    aws sqs send-message --queue-url $QUEUE_URL \\"
echo "      --message-body \"{\\\"s3_input_dir\\\": \\\"\$dir\\\", \\\"sample_id\\\": \\\"\$(basename \$dir)\\\"}\""
echo "  done"
echo ""
echo "Environment:"
echo "  SQS Queue:        $QUEUE_URL"
echo "  Lambda:           $LAMBDA_NAME"
echo "  EC2 Profile:      $INSTANCE_PROFILE_ARN"
echo "  Security Group:   $SG_ID"
echo "  Subnet:           $SUBNET_ID"
echo "  GPU AMI:          $AMI_ID"
echo "  ECR Image:        $ECR_URI"
