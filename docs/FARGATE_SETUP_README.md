# AWS ECS Fargate Report Generation Setup

This setup allows you to generate genetic reports using AWS ECS Fargate containers triggered by Lambda functions.

## Architecture Overview

```
Lambda Function → ECS Fargate Task → S3 Output
     ↓                ↓                ↓
Environment Vars → Report Generation → PDF/JSON Files
```

## Files Overview

### Core Files
- `fargate_entrypoint.py` - Main entrypoint for the Fargate container
- `Dockerfile` - Container definition for the report generator
- `pdf_generator.py` - Updated PDF generation functionality
- `lambda_fargate_caller.py` - Lambda function to trigger Fargate tasks

### Build & Deploy
- `build_fargate_container.sh` - Script to build and push container to ECR
- `fargate-task-definition.json` - ECS task definition template

### Testing
- `test_fargate_workflow.py` - Local testing script

## Setup Instructions

### 1. Prerequisites

- AWS CLI configured with appropriate permissions
- Docker installed and running
- Python 3.9+ for local testing

### 2. Build and Deploy Container

```bash
# Make the build script executable
chmod +x build_fargate_container.sh

# Build and push to ECR
./build_fargate_container.sh
```

### 3. Create ECS Task Definition

1. Update `fargate-task-definition.json` with your AWS account ID
2. Create the task definition:

```bash
aws ecs register-task-definition --cli-input-json file://fargate-task-definition.json
```

### 4. Create ECS Cluster

```bash
aws ecs create-cluster --cluster-name report-generation-cluster --capacity-providers FARGATE
```

### 5. Deploy Lambda Function

1. Update `lambda_fargate_caller.py` with your ECS cluster details
2. Create a deployment package and deploy to Lambda
3. Set appropriate IAM permissions for Lambda to call ECS

### 6. Required IAM Roles

#### ECS Task Execution Role
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "*"
    }
  ]
}
```

#### ECS Task Role
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:::your-input-bucket/*",
        "arn:aws:s3:::ghcompletedreports/*"
      ]
    }
  ]
}
```

#### Lambda Execution Role
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecs:RunTask",
        "ecs:DescribeTasks",
        "iam:PassRole"
      ],
      "Resource": "*"
    }
  ]
}
```

## Usage

### Environment Variables

The Lambda function passes these environment variables to the Fargate container:

- `ANNOTATED_VCF_PATH` - S3 URI to annotated VCF file
- `VCF_PATH` - S3 URI to raw VCF file  
- `TEMPLATE_PATH` - S3 URI to report template JSON
- `NAME` - Patient name
- `ID` - Patient ID
- `PROVIDER` - Healthcare provider name
- `OUTPUT_S3_BUCKET` - (Optional) Output S3 bucket name

### Lambda Event Format

```json
{
  "annotated_vcf_path": "s3://input-bucket/patient123_annotated.vcf",
  "vcf_path": "s3://input-bucket/patient123.vcf",
  "template_path": "s3://templates-bucket/adhd_template.json",
  "name": "John Doe",
  "id": "patient_123",
  "provider": "Dr. Smith Medical Center",
  "output_s3_bucket": "ghcompletedreports"
}
```

### Output

The system generates:
- JSON report: `s3://output-bucket/reports/{patient_id}/{patient_id}_{timestamp}.json`
- PDF report: `s3://output-bucket/reports/{patient_id}/{patient_id}_{timestamp}.pdf`

## Local Testing

Test the workflow locally without AWS:

```bash
python test_fargate_workflow.py
```

This creates dummy input files and tests the complete pipeline.

## Monitoring

- Check ECS task logs in CloudWatch: `/ecs/report-generator`
- Monitor Lambda function logs in CloudWatch
- Track S3 uploads in the output bucket

## Troubleshooting

### Common Issues

1. **Container fails to start**
   - Check ECS task logs
   - Verify IAM roles have correct permissions
   - Ensure ECR image exists and is accessible

2. **S3 download failures**
   - Verify S3 URIs are correct
   - Check IAM permissions for S3 access
   - Ensure files exist in specified locations

3. **Report generation errors**
   - Check input file formats (VCF, JSON template)
   - Monitor memory usage (increase if needed)
   - Review application logs for specific errors

### Scaling Considerations

- Adjust CPU/memory in task definition based on report complexity
- Use spot instances for cost optimization
- Consider using SQS for batch processing multiple reports

## Cost Optimization

- Use Fargate Spot for non-critical workloads
- Set appropriate CPU/memory limits
- Clean up old reports from S3 using lifecycle policies
- Monitor CloudWatch costs and set up billing alerts

## Security Best Practices

- Use least-privilege IAM policies
- Enable VPC Flow Logs for network monitoring
- Encrypt S3 buckets and ECS task storage
- Use AWS Secrets Manager for sensitive configuration
- Enable CloudTrail for API auditing