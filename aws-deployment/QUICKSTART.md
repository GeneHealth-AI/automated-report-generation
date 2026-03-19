# Quick Start Guide - Genetic Report Generation System

Get your system running in AWS in under 30 minutes!

## Prerequisites Checklist

- [ ] AWS Account with administrator access
- [ ] AWS CLI installed and configured (`aws configure`)
- [ ] Terraform installed (v1.0+)
- [ ] Docker installed and running
- [ ] Python 3.9+ installed
- [ ] Anthropic API key
- [ ] Google Gemini API key

## Step-by-Step Deployment

### 1. Clone and Navigate to Deployment Directory (1 min)

```bash
cd aws-deployment
```

### 2. Configure Terraform Variables (2 mins)

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` and set at minimum:
```hcl
aws_region  = "us-east-1"  # Your preferred region
environment = "prod"        # or "dev", "staging"
project_name = "genetic-reports"
```

### 3. Run Automated Deployment (20-25 mins)

```bash
cd ..
./scripts/deploy.sh
```

**What this script does**:
- ✅ Checks prerequisites
- ✅ Initializes Terraform
- ✅ Plans infrastructure deployment
- ✅ Deploys all AWS resources (VPC, RDS, ECS, Lambda, etc.)
- ✅ Builds and pushes Docker image to ECR
- ✅ Uploads GWAS data to S3
- ✅ Runs database migrations

**You will be prompted for confirmation** before applying changes.

### 4. Update API Keys (2 mins)

After deployment completes, update your API keys:

```bash
./scripts/update-secrets.sh
```

Or manually:

```bash
# Get secret ARNs from Terraform output
cd terraform
terraform output anthropic_secret_arn
terraform output gemini_secret_arn

# Update secrets
aws secretsmanager put-secret-value \
  --secret-id <ANTHROPIC_SECRET_ARN> \
  --secret-string "your-anthropic-api-key"

aws secretsmanager put-secret-value \
  --secret-id <GEMINI_SECRET_ARN> \
  --secret-string "your-gemini-api-key"
```

### 5. Test Your Deployment (2 mins)

```bash
# Test the API endpoint
./scripts/test-api.sh
```

Or manually with curl:

```bash
# Get API URL and Key
cd terraform
API_URL=$(terraform output -raw api_gateway_url)
API_KEY=$(aws apigateway get-api-key --api-key $(terraform output -raw api_key_id) --include-value --query 'value' --output text)

# Test request
curl -X POST "$API_URL" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $API_KEY" \
  -d '{
    "annotated_vcf_path": "s3://your-bucket/test-annotated.vcf",
    "vcf_path": "s3://your-bucket/test.vcf",
    "template_path": "s3://your-bucket/template.json",
    "name": "Test Patient",
    "id": "test-001",
    "provider": "Test Provider"
  }'
```

## You're Done! 🎉

Your Genetic Report Generation System is now live on AWS!

## What You Have

### Infrastructure
- ✅ VPC with public/private subnets across 2 AZs
- ✅ RDS PostgreSQL database (encrypted)
- ✅ ECS Fargate cluster for report generation
- ✅ Lambda function for orchestration
- ✅ API Gateway for REST API
- ✅ S3 buckets for input/output
- ✅ CloudWatch for logging and monitoring
- ✅ Secrets Manager for API keys

### Outputs

Get your deployment information:

```bash
cd terraform
terraform output
```

Key outputs:
- `api_gateway_url`: Your API endpoint
- `input_bucket_name`: Upload VCF files here
- `output_bucket_name`: Generated reports stored here
- `rds_endpoint`: Database endpoint

## Next Steps

### 1. Upload Your First VCF Files

```bash
INPUT_BUCKET=$(cd terraform && terraform output -raw input_bucket_name)

# Upload VCF file
aws s3 cp your-file.vcf s3://$INPUT_BUCKET/vcf/

# Upload annotated VCF
aws s3 cp your-annotated.vcf s3://$INPUT_BUCKET/vcf/

# Upload template (optional)
aws s3 cp template.json s3://$INPUT_BUCKET/templates/
```

### 2. Generate Your First Report

```bash
# Using the API
curl -X POST "$API_URL" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $API_KEY" \
  -d @request.json
```

Example `request.json`:
```json
{
  "annotated_vcf_path": "s3://your-input-bucket/vcf/patient-001-annotated.vcf",
  "vcf_path": "s3://your-input-bucket/vcf/patient-001.vcf",
  "template_path": "s3://your-input-bucket/templates/adhd-template.json",
  "name": "John Doe",
  "id": "patient-001",
  "provider": "Dr. Jane Smith",
  "output_s3_bucket": "your-output-bucket"
}
```

### 3. Monitor Your Reports

```bash
# Check ECS tasks
aws ecs list-tasks --cluster genetic-reports-cluster-prod

# View logs
aws logs tail /ecs/genetic-reports-prod --follow

# Check report status in database
# (See DATABASE.md for connection details)
```

### 4. Download Generated Reports

```bash
OUTPUT_BUCKET=$(cd terraform && terraform output -raw output_bucket_name)

# List reports
aws s3 ls s3://$OUTPUT_BUCKET/

# Download a report
aws s3 cp s3://$OUTPUT_BUCKET/patient-001-report.pdf ./
```

## Common Issues and Fixes

### Issue: "Docker daemon not running"
**Fix**: Start Docker Desktop or Docker service

### Issue: "AWS credentials not configured"
**Fix**: Run `aws configure` and enter your credentials

### Issue: "Terraform state locked"
**Fix**:
```bash
cd terraform
terraform force-unlock <LOCK_ID>
```

### Issue: "ECS task fails to start"
**Fix**: Check CloudWatch logs for the ECS task:
```bash
aws logs tail /ecs/genetic-reports-prod --follow
```

Common causes:
- Missing API keys in Secrets Manager
- Docker image not found (re-run `./scripts/build-docker.sh`)

### Issue: "Database connection refused"
**Fix**: Check security groups allow access from ECS tasks

## Getting Help

1. Check the logs:
   ```bash
   ./scripts/view-logs.sh  # If available
   # Or manually:
   aws logs tail /ecs/genetic-reports-prod --follow
   ```

2. Review the documentation:
   - `README.md` - Full deployment guide
   - `docs/ARCHITECTURE.md` - System architecture
   - `docs/DATABASE.md` - Database documentation

3. Check AWS Console:
   - CloudWatch Logs for errors
   - ECS console for task status
   - RDS console for database health

## Clean Up (When Done Testing)

To delete all resources and avoid charges:

```bash
cd terraform

# Destroy all infrastructure
terraform destroy

# Confirm when prompted
```

**Note**: This will delete:
- All S3 buckets and their contents
- RDS database (final snapshot created)
- All ECS tasks and services
- Lambda functions
- API Gateway

**Before destroying**, make sure to:
- Back up any important reports from S3
- Export database data if needed
- Note down any custom configurations

## Cost Estimate

**Monthly costs** (approximate, varies by usage):
- RDS: $60-80
- ECS Fargate: $30-50 (if running 24/7)
- S3: $5-20 (depends on storage)
- Other services: $10-20

**Total**: ~$150-200/month for light usage

**Tip**: Use Fargate Spot instances to save 70% on compute costs!

## Support

For issues or questions:
1. Check documentation in `docs/` folder
2. Review CloudWatch logs
3. Check Terraform outputs for configuration details

---

**Congratulations!** You've successfully deployed a production-ready genetic report generation system on AWS!
