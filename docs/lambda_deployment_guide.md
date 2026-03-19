# Lambda Function Deployment Guide for ECR Container Orchestration

This guide explains how to deploy the simplified Lambda function that orchestrates your ECR containers instead of running report generation directly in Lambda.

## Architecture Overview

```
API Gateway/S3 Event → Lambda Function → ECS/Fargate → ECR Container → S3 Output
```

## Required AWS Resources

### 1. ECS Cluster
Create an ECS cluster to run your containers:

```bash
aws ecs create-cluster --cluster-name report-generation-cluster
```

### 2. Task Definitions

Create task definitions for both containers:

#### JSON Task Definition
```json
{
  "family": "report-generator-json",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "executionRoleArn": "arn:aws:iam::339712911975:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::339712911975:role/ecsTaskRole",
  "containerDefinitions": [
    {
      "name": "report-generator-json",
      "image": "339712911975.dkr.ecr.us-east-1.amazonaws.com/report-generator-json:latest",
      "essential": true,
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/report-generator-json",
          "awslogs-region": "us-east-2",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
```

#### PDF Task Definition
```json
{
  "family": "report-generator-pdf",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "arn:aws:iam::339712911975:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::339712911975:role/ecsTaskRole",
  "containerDefinitions": [
    {
      "name": "report-generator-pdf",
      "image": "339712911975.dkr.ecr.us-east-1.amazonaws.com/report-generator-pdf:latest",
      "essential": true,
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/report-generator-pdf",
          "awslogs-region": "us-east-2",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
```

### 3. Lambda Function Environment Variables

Set these environment variables in your Lambda function:

```bash
ECS_CLUSTER=report-generation-cluster
JSON_TASK_DEFINITION=report-generator-json
PDF_TASK_DEFINITION=report-generator-pdf
SUBNET_IDS=subnet-12345,subnet-67890  # Your VPC subnet IDs
SECURITY_GROUP_IDS=sg-12345678  # Security group allowing outbound internet access
ANTHROPIC_API_KEY=your-anthropic-api-key
OUTPUT_BUCKET=ghcompletedreports
AWS_REGION=us-east-1
```

### 4. IAM Roles

#### Lambda Execution Role
The Lambda function needs permissions to:
- Run ECS tasks
- Pass roles to ECS tasks
- Access S3 buckets

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ecs:RunTask",
        "ecs:DescribeTasks",
        "ecs:StopTask"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": [
        "arn:aws:iam::339712911975:role/ecsTaskExecutionRole",
        "arn:aws:iam::339712911975:role/ecsTaskRole"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::*/*"
    }
  ]
}
```

#### ECS Task Execution Role
Standard ECS task execution role for pulling container images and logging.

#### ECS Task Role
The containers need permissions to:
- Access S3 buckets
- Terminate EC2 instances (if using EC2 launch type)

## Deployment Steps

### 1. Deploy Lambda Function

```bash
# Create deployment package
zip lambda-deployment.zip lambda_function_simplified.py

# Create or update Lambda function
aws lambda create-function \
  --function-name report-generator-orchestrator \
  --runtime python3.9 \
  --role arn:aws:iam::339712911975:role/lambda-execution-role \
  --handler lambda_function_simplified.lambda_handler \
  --zip-file fileb://lambda-deployment.zip \
  --timeout 300 \
  --memory-size 256

# Set environment variables
aws lambda update-function-configuration \
  --function-name report-generator-orchestrator \
  --environment Variables='{
    "ECS_CLUSTER":"report-generation-cluster",
    "JSON_TASK_DEFINITION":"report-generator-json",
    "PDF_TASK_DEFINITION":"report-generator-pdf",
    "SUBNET_IDS":"subnet-12345,subnet-67890",
    "SECURITY_GROUP_IDS":"sg-12345678",
    "ANTHROPIC_API_KEY":"your-api-key",
    "OUTPUT_BUCKET":"ghcompletedreports",
    "AWS_REGION":"us-east-1"
  }'
```

### 2. Register Task Definitions

```bash
# Register JSON task definition
aws ecs register-task-definition --cli-input-json file://json-task-definition.json

# Register PDF task definition
aws ecs register-task-definition --cli-input-json file://pdf-task-definition.json
```

### 3. Create CloudWatch Log Groups

```bash
aws logs create-log-group --log-group-name /ecs/report-generator-json
aws logs create-log-group --log-group-name /ecs/report-generator-pdf
```

## Usage Examples

### 1. S3 Trigger (Automatic)
When a JSON file is uploaded to S3, the Lambda function automatically triggers the JSON container.

### 2. API Gateway (On-demand JSON generation)
```bash
curl -X POST https://your-api-gateway-url/generate \
  -H "Content-Type: application/json" \
  -d '{
    "report_type": "json",
    "template_s3": "s3://bucket/template.json",
    "vcf_s3": "s3://bucket/sample.vcf",
    "annotated_s3": "s3://bucket/annotated.vcf"
  }'
```

### 3. API Gateway (On-demand PDF generation)
```bash
curl -X POST https://your-api-gateway-url/generate \
  -H "Content-Type: application/json" \
  -d '{
    "report_type": "pdf",
    "input_json_s3": "s3://bucket/report.json"
  }'
```

### 4. Direct Lambda Invocation
```bash
aws lambda invoke \
  --function-name report-generator-orchestrator \
  --payload '{
    "report_type": "json",
    "template_s3": "s3://bucket/template.json",
    "vcf_s3": "s3://bucket/sample.vcf",
    "annotated_s3": "s3://bucket/annotated.vcf"
  }' \
  response.json
```

## Benefits of This Approach

1. **No Lambda Limitations**: Containers can run for hours and use as much memory/CPU as needed
2. **Scalability**: ECS/Fargate automatically scales based on demand
3. **Cost Efficiency**: Only pay for container runtime, not idle Lambda time
4. **Flexibility**: Easy to update containers without redeploying Lambda
5. **Monitoring**: Better logging and monitoring through ECS and CloudWatch
6. **Resource Management**: Containers can be optimized for specific workloads

## Monitoring and Troubleshooting

- Check ECS task logs in CloudWatch: `/ecs/report-generator-json` and `/ecs/report-generator-pdf`
- Monitor Lambda function logs: `/aws/lambda/report-generator-orchestrator`
- Use ECS console to view task status and resource utilization
- Set up CloudWatch alarms for failed tasks or high resource usage