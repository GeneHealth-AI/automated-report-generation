# Genetic Report Generation System - AWS Deployment Guide

This directory contains everything needed to deploy the Genetic Report Generation System to AWS.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Prerequisites](#prerequisites)
3. [Quick Start](#quick-start)
4. [Detailed Setup](#detailed-setup)
5. [Database Setup](#database-setup)
6. [Deployment Scripts](#deployment-scripts)
7. [Monitoring and Logging](#monitoring-and-logging)
8. [Troubleshooting](#troubleshooting)
9. [Cost Estimation](#cost-estimation)

---

## Architecture Overview

The system consists of the following AWS components:

```
┌─────────────────────────────────────────────────────────────┐
│                         AWS Cloud                            │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌───────────────┐         ┌──────────────┐                 │
│  │  API Gateway  │────────▶│   Lambda     │                 │
│  │               │         │  (Trigger)   │                 │
│  └───────────────┘         └──────┬───────┘                 │
│         │                          │                         │
│         │                          ▼                         │
│         │                  ┌───────────────┐                │
│         │                  │  ECS Fargate  │                │
│         │                  │  (Processing) │                │
│         │                  └───────┬───────┘                │
│         │                          │                         │
│  ┌──────▼────────┐        ┌───────▼───────┐                │
│  │   S3 Buckets  │        │ RDS PostgreSQL│                │
│  │  Input/Output │        │   (Metadata)  │                │
│  └───────────────┘        └───────────────┘                │
│         │                          │                         │
│  ┌──────▼──────────────────────────▼──────┐                │
│  │         CloudWatch Logs                 │                │
│  └─────────────────────────────────────────┘                │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### Components:

1. **API Gateway**: RESTful API for triggering report generation
2. **Lambda**: Orchestrates ECS Fargate task execution
3. **ECS Fargate**: Runs containerized report generation
4. **RDS PostgreSQL**: Stores report metadata and query results
5. **S3**: Stores input VCF files, templates, and output reports
6. **ECR**: Docker container registry
7. **Secrets Manager**: Stores API keys and database credentials
8. **CloudWatch**: Logs and metrics

---

## Prerequisites

Before deploying, ensure you have:

### Required Tools

- **AWS CLI** (v2.x): [Installation Guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
- **Terraform** (v1.0+): [Installation Guide](https://learn.hashicorp.com/tutorials/terraform/install-cli)
- **Docker** (v20.x+): [Installation Guide](https://docs.docker.com/get-docker/)
- **Python** (v3.9+): [Installation Guide](https://www.python.org/downloads/)
- **PostgreSQL Client** (psql): [Installation Guide](https://www.postgresql.org/download/)

### AWS Account Setup

1. **AWS Account**: Active AWS account with appropriate permissions
2. **AWS Credentials**: Configured via `aws configure`
3. **IAM Permissions**: Administrator access or equivalent

Required IAM permissions:
- EC2 (VPC, Subnets, Security Groups)
- RDS (Database instances)
- S3 (Buckets and objects)
- ECS (Clusters, Task Definitions)
- Lambda (Functions)
- API Gateway
- Secrets Manager
- CloudWatch Logs
- ECR

### API Keys

- **Anthropic API Key**: For Claude AI (https://console.anthropic.com/)
- **Google Gemini API Key**: For Gemini AI (https://makersuite.google.com/)

---

## Quick Start

For a rapid deployment, run the automated deployment script:

```bash
cd aws-deployment
./scripts/deploy.sh
```

This script will:
1. Check prerequisites
2. Initialize Terraform
3. Deploy infrastructure
4. Build and push Docker image
5. Run database migrations
6. Provide next steps

---

## Detailed Setup

### Step 1: Configure Terraform Variables

1. Copy the example variables file:
   ```bash
   cd terraform
   cp terraform.tfvars.example terraform.tfvars
   ```

2. Edit `terraform.tfvars` with your settings:
   ```hcl
   aws_region  = "us-east-1"
   environment = "prod"
   project_name = "genetic-reports"

   # ECS Configuration
   fargate_cpu    = 2048  # 2 vCPUs
   fargate_memory = 4096  # 4 GB

   # RDS Configuration
   db_instance_class = "db.t3.medium"
   db_allocated_storage = 100
   ```

3. Configure backend for Terraform state (optional but recommended):
   Edit `terraform/main.tf`:
   ```hcl
   backend "s3" {
     bucket = "your-terraform-state-bucket"
     key    = "genetic-reports/terraform.tfstate"
     region = "us-east-1"
   }
   ```

### Step 2: Deploy Infrastructure with Terraform

```bash
cd terraform

# Initialize Terraform
terraform init

# Review the deployment plan
terraform plan

# Apply the configuration
terraform apply
```

### Step 3: Build and Push Docker Image

```bash
# Automated script
../scripts/build-docker.sh

# OR manually:
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <ECR_URL>
cd ../..
docker build -f infra/Dockerfile -t genetic-reports:latest .
docker tag genetic-reports:latest <ECR_URL>:latest
docker push <ECR_URL>:latest
```

### Step 4: Update API Keys

```bash
# Automated script
./scripts/update-secrets.sh

# OR manually:
aws secretsmanager put-secret-value \
  --secret-id <ANTHROPIC_SECRET_ARN> \
  --secret-string "YOUR_ANTHROPIC_API_KEY"

aws secretsmanager put-secret-value \
  --secret-id <GEMINI_SECRET_ARN> \
  --secret-string "YOUR_GEMINI_API_KEY"
```

### Step 5: Run Database Migrations

```bash
# Automated script
./scripts/run-migrations.sh

# OR manually:
cd database
psql -h <RDS_ENDPOINT> -U report_admin -d genetic_reports -f schema.sql
```

### Step 6: Upload GWAS Data

```bash
# Upload GWAS catalog to S3
aws s3 cp ../gwas_catalog_v1.0.2-associations_e114_r2025-07-10.tsv \
  s3://<GWAS_BUCKET>/gwas_catalog.tsv
```

### Step 7: Test the Deployment

```bash
# Test the API endpoint
./scripts/test-api.sh
```

---

## Database Setup

### Schema Overview

The database includes the following tables:

- **patients**: Patient information
- **providers**: Healthcare provider information
- **report_requests**: Report generation requests and status
- **generated_reports**: Metadata about generated reports
- **mutations_analyzed**: Genetic mutations analyzed in reports
- **api_usage**: API usage tracking for cost monitoring
- **system_logs**: System logs
- **audit_trail**: Audit trail for compliance

### Connecting to the Database

```bash
# Get database credentials
aws secretsmanager get-secret-value \
  --secret-id <DB_SECRET_ARN> \
  --query SecretString \
  --output text | jq .

# Connect using psql
psql -h <RDS_ENDPOINT> -U report_admin -d genetic_reports
```

### Running Custom Queries

See `database/db_client.py` for Python client examples:

```python
from database.db_client import DatabaseClient

db = DatabaseClient()

# Create a patient
patient_id = db.create_patient(
    external_id="PATIENT-001",
    patient_name="John Doe"
)

# Create a report request
request_id = db.create_report_request(
    patient_id=patient_id,
    vcf_s3_path="s3://bucket/file.vcf",
    focus="ADHD"
)
```

---

## Deployment Scripts

### Available Scripts

| Script | Description |
|--------|-------------|
| `deploy.sh` | Complete deployment automation |
| `build-docker.sh` | Build and push Docker image to ECR |
| `run-migrations.sh` | Run database migrations |
| `update-secrets.sh` | Update API keys in Secrets Manager |
| `test-api.sh` | Test the API Gateway endpoint |

### Usage Examples

```bash
# Full deployment
./scripts/deploy.sh

# Rebuild and push Docker image only
./scripts/build-docker.sh

# Update database schema
./scripts/run-migrations.sh

# Update API keys
./scripts/update-secrets.sh

# Test API
./scripts/test-api.sh
```

---

## Monitoring and Logging

### CloudWatch Log Groups

- `/ecs/genetic-reports-{env}`: ECS Fargate task logs
- `/aws/lambda/genetic-reports-fargate-trigger-{env}`: Lambda function logs
- `/aws/apigateway/genetic-reports-{env}`: API Gateway logs

### Viewing Logs

```bash
# View recent ECS logs
aws logs tail /ecs/genetic-reports-prod --follow

# View Lambda logs
aws logs tail /aws/lambda/genetic-reports-fargate-trigger-prod --follow

# Search for errors
aws logs filter-log-events \
  --log-group-name /ecs/genetic-reports-prod \
  --filter-pattern ERROR
```

### CloudWatch Alarms

Pre-configured alarms:
- RDS CPU utilization
- RDS storage space
- ECS CPU/Memory utilization
- Lambda errors and duration
- S3 error rates

View alarms:
```bash
aws cloudwatch describe-alarms \
  --alarm-name-prefix genetic-reports
```

---

## Troubleshooting

### Common Issues

#### 1. Terraform Apply Fails

**Error**: "Resource already exists"
```bash
# Import existing resource
terraform import aws_s3_bucket.input bucket-name
```

**Error**: "Insufficient permissions"
- Check IAM permissions
- Ensure AWS credentials are configured correctly

#### 2. Docker Build Fails

**Error**: "Permission denied"
```bash
# Re-authenticate with ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <ECR_URL>
```

#### 3. ECS Task Fails to Start

Check CloudWatch logs:
```bash
aws logs tail /ecs/genetic-reports-prod --follow
```

Common causes:
- Missing API keys in Secrets Manager
- Incorrect IAM permissions
- Docker image pull errors

#### 4. Database Connection Issues

Test connectivity:
```bash
# From within VPC
psql -h <RDS_ENDPOINT> -U report_admin -d genetic_reports

# Check security groups
aws ec2 describe-security-groups --group-ids <SG_ID>
```

#### 5. API Gateway Returns 403

- Verify API key is correct
- Check IAM authentication settings
- Review CloudWatch logs for detailed errors

---

## Cost Estimation

### Monthly Cost Breakdown (Approximate)

**Compute:**
- ECS Fargate (2 vCPU, 4GB): $0.04048/hour × 720 hours = ~$29/month (if running continuously)
- Lambda: $0.20 per 1M requests + $0.0000166667/GB-second
- Spot pricing: Use Fargate Spot for 70% savings on compute

**Storage:**
- S3 Standard: $0.023/GB/month
- RDS (db.t3.medium): ~$60/month
- RDS Storage (100GB): ~$11.50/month

**Data Transfer:**
- Within AWS: Free (same region)
- Internet egress: $0.09/GB

**APIs:**
- Anthropic Claude: ~$0.003-0.015 per 1K tokens
- Google Gemini: ~$0.00025-0.0005 per 1K characters

**Total Estimated Monthly Cost**: $150-300 (depending on usage)

### Cost Optimization Tips

1. Use Fargate Spot instances for non-critical workloads (70% savings)
2. Enable S3 Intelligent-Tiering for automatic cost optimization
3. Use RDS Reserved Instances for production (up to 60% savings)
4. Set up CloudWatch alarms for cost anomalies
5. Use S3 lifecycle policies to archive old reports
6. Optimize API usage with caching and batching

---

## Security Best Practices

1. **Secrets Management**: Never commit API keys or passwords
2. **IAM Roles**: Use least-privilege access
3. **VPC**: Keep RDS and ECS in private subnets
4. **Encryption**: Enable encryption at rest for S3, RDS, and EBS
5. **Audit Trail**: Review audit_trail table regularly
6. **API Gateway**: Use API keys and throttling
7. **Security Groups**: Restrict access to necessary ports only

---

## Support and Maintenance

### Updating the System

```bash
# Update Terraform infrastructure
cd terraform
terraform plan
terraform apply

# Update Docker image
cd ..
./scripts/build-docker.sh

# Update database schema
./scripts/run-migrations.sh
```

### Backup and Recovery

**RDS Automated Backups**: Enabled with 7-day retention

**Manual Backup**:
```bash
aws rds create-db-snapshot \
  --db-instance-identifier genetic-reports-db-prod \
  --db-snapshot-identifier manual-backup-$(date +%Y%m%d)
```

**S3 Versioning**: Enabled on all buckets

---

## Additional Resources

- [AWS ECS Documentation](https://docs.aws.amazon.com/ecs/)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Anthropic API Documentation](https://docs.anthropic.com/)

---

## License

[Your License Here]

## Contributing

[Contributing Guidelines]
