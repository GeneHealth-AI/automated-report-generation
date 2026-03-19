# Automated Report Generation — Deployment & Usage Guide

## Overview

Generates precision medicine HTML reports from genomic variant data. Takes annotated VCF + disease scores from the genomics pipeline and produces a complete patient-facing report with risk comparisons, lifestyle recommendations, monitoring plans, and clinical analysis.

**Deployed on**: AWS ECS Fargate (us-east-2)
**Container**: `339712911975.dkr.ecr.us-east-2.amazonaws.com/report-generator-json:latest`
**Task Definition**: `report-generator-json` (latest revision)
**Cluster**: `report-generation-cluster`
**Output Bucket**: `s3://ghcompletedreports/`
**GitHub**: https://github.com/GeneHealth-AI/automated-report-generation

---

## How to Generate a Report

### Required Inputs

| Parameter | Description | Example |
|-----------|-------------|---------|
| `ANNOTATED_VCF_PATH` | S3 path to the annotated VCF / disease scores file | `s3://exomeinputbucket/sample/results/final_report.txt` |
| `VCF_PATH` | S3 path to the raw VCF file | `s3://exomeinputbucket/sample/results/raw_variants.vcf` |
| `TEMPLATE_PATH` | S3 path to the report template JSON | `s3://gh-templates/cancer_template.json` |
| `NAME` | Patient full name | `Jane Doe` |
| `ID` | Patient ID | `GHID12345` |
| `PROVIDER` | Provider name | `Dr. Smith` |
| `OUTPUT_S3_BUCKET` | S3 bucket for report output | `ghcompletedreports` |
| `GEMINI_API_KEY` | Google Gemini API key for LLM generation | `AIzaSy...` |

### Optional Inputs

| Parameter | Description | Default |
|-----------|-------------|---------|
| `PATIENT_GENDER` | `Male`, `Female`, or `Unknown` — filters sex-specific conditions | `Unknown` |
| `OUTPUT_FILENAME` | Custom filename for the output | Auto-generated from patient ID + name + timestamp |

### Available Templates

Templates are stored in `s3://gh-templates/`:

- `cancer_template.json` — Hereditary cancer risk
- `cardiovascular_template.json` — Cardiovascular disease
- `cardiomyopathy_template.json` — Cardiomyopathy
- `hematology_template.json` — Blood disorders
- `hereditary_cancer_template.json` — Hereditary cancer syndromes
- `immunology_template.json` — Immune disorders
- `metabolic_disorders_template.json` — Metabolic conditions
- `general_disease_template.json` — General disease risk
- `connective_tissue_template.json` — Connective tissue disorders
- `familial_hypercholesterolemia_template.json` — FH

---

## Method 1: AWS CLI (Direct ECS Task)

```bash
aws ecs run-task \
  --cluster report-generation-cluster \
  --task-definition report-generator-json \
  --launch-type FARGATE \
  --network-configuration 'awsvpcConfiguration={
    subnets=["subnet-06bed7fd9557c191c"],
    securityGroups=["sg-008a6c6e922e707cc"],
    assignPublicIp="ENABLED"
  }' \
  --overrides '{
    "containerOverrides": [{
      "name": "report-generator-json",
      "environment": [
        {"name": "ANNOTATED_VCF_PATH", "value": "s3://exomeinputbucket/SAMPLE/results/final_report.txt"},
        {"name": "VCF_PATH", "value": "s3://exomeinputbucket/SAMPLE/results/raw_variants.vcf"},
        {"name": "TEMPLATE_PATH", "value": "s3://gh-templates/cancer_template.json"},
        {"name": "NAME", "value": "Jane Doe"},
        {"name": "ID", "value": "GHID12345"},
        {"name": "PROVIDER", "value": "Dr. Smith"},
        {"name": "OUTPUT_S3_BUCKET", "value": "ghcompletedreports"},
        {"name": "PATIENT_GENDER", "value": "Female"},
        {"name": "GEMINI_API_KEY", "value": "YOUR_GEMINI_KEY"}
      ]
    }]
  }' \
  --region us-east-2
```

This returns a task ARN you can use to monitor progress.

## Method 2: From Website / Application Code

Use the AWS SDK to call `ecs.runTask()` with the same parameters:

```javascript
// Node.js / Laravel example
const params = {
  cluster: 'report-generation-cluster',
  taskDefinition: 'report-generator-json',
  launchType: 'FARGATE',
  networkConfiguration: {
    awsvpcConfiguration: {
      subnets: ['subnet-06bed7fd9557c191c'],
      securityGroups: ['sg-008a6c6e922e707cc'],
      assignPublicIp: 'ENABLED'
    }
  },
  overrides: {
    containerOverrides: [{
      name: 'report-generator-json',
      environment: [
        { name: 'ANNOTATED_VCF_PATH', value: 's3://exomeinputbucket/sample/results/final_report.txt' },
        { name: 'VCF_PATH', value: 's3://exomeinputbucket/sample/results/raw_variants.vcf' },
        { name: 'TEMPLATE_PATH', value: 's3://gh-templates/cancer_template.json' },
        { name: 'NAME', value: 'Jane Doe' },
        { name: 'ID', value: 'GHID12345' },
        { name: 'PROVIDER', value: 'Dr. Smith' },
        { name: 'OUTPUT_S3_BUCKET', value: 'ghcompletedreports' },
        { name: 'PATIENT_GENDER', value: 'Female' },
        { name: 'GEMINI_API_KEY', value: process.env.GEMINI_API_KEY }
      ]
    }]
  }
};

const ecs = new AWS.ECS({ region: 'us-east-2' });
const result = await ecs.runTask(params).promise();
const taskArn = result.tasks[0].taskArn;
```

## Method 3: Lambda / API Gateway

The existing Lambda function `precision-medicine-pdf-generator` can also trigger report generation. It accepts S3 events or API Gateway POST requests.

---

## What Happens After Generation

1. **Report files uploaded to S3** (`ghcompletedreports` bucket):
   - `{ID}_{Name}_report_{timestamp}.html` — The main HTML report
   - `{ID}_{Name}_report_{timestamp}.json` — JSON data
   - `{ID}_{Name}_report_{timestamp}.pdf` — PDF version

2. **Webhook fired**: `POST https://www.genehealth.ai/api/amazon/report-ready`
   ```json
   {
     "path": "GHID12345_Jane_Doe_report_1773899943.html"
   }
   ```
   This notifies the website that the report is ready. The path is relative to the `ghcompletedreports` bucket (no bucket prefix).

3. **Review results**: A quality review JSON is also uploaded alongside the report.

---

## Monitoring & Troubleshooting

### Check task status

```bash
# Get task status (replace TASK_ID with the ID from run-task response)
aws ecs describe-tasks \
  --cluster report-generation-cluster \
  --tasks TASK_ID \
  --region us-east-2 \
  --query 'tasks[0].{status:lastStatus,exitCode:containers[0].exitCode,reason:stoppedReason}'
```

### Watch logs in real-time

```bash
aws logs tail /ecs/report-generator-json --region us-east-2 --follow
```

### Get logs for a specific task

```bash
aws logs get-log-events \
  --log-group-name /ecs/report-generator-json \
  --log-stream-name "ecs/report-generator-json/TASK_ID" \
  --region us-east-2 \
  --query 'events[-20:].message' \
  --output text
```

### Check output in S3

```bash
aws s3 ls s3://ghcompletedreports/ --region us-east-2 | tail -10
```

### Common Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| Exit code 0 but empty report | `final_report.txt` has no disease scores (all `.`) | System auto-falls back to `enterprise_scores.txt`. If that's also missing, no genetic data available for that sample |
| Exit code 1 | Container error — check logs | `aws logs tail /ecs/report-generator-json --region us-east-2` |
| 403 on S3 download | IAM permissions | Check `ecsTaskRole` has access to the S3 bucket |
| Webhook returns 404 | Report path not registered in website DB | Expected if website hasn't created the report record yet |
| Task stays PENDING | No Fargate capacity or networking issue | Check subnet has internet access, security group allows outbound |

---

## Verification Checklist

Run this to verify the full system is functional:

```bash
# 1. Check the ECS cluster exists
aws ecs describe-clusters --clusters report-generation-cluster --region us-east-2 \
  --query 'clusters[0].status'
# Expected: "ACTIVE"

# 2. Check the task definition exists
aws ecs describe-task-definition --task-definition report-generator-json --region us-east-2 \
  --query 'taskDefinition.revision'
# Expected: a number (latest revision)

# 3. Check the ECR image exists
aws ecr describe-images --repository-name report-generator-json --region us-east-2 \
  --query 'imageDetails[0].imagePushedAt'
# Expected: recent timestamp

# 4. Check S3 buckets are accessible
aws s3 ls s3://ghcompletedreports/ --region us-east-2 | tail -3
aws s3 ls s3://gh-templates/ --region us-east-2 | head -3
aws s3 ls s3://exomeinputbucket/ --region us-east-2 | head -3

# 5. Check IAM role has required permissions
aws iam get-role-policy --role-name ecsTaskRole --policy-name S3GetAndPut \
  --query 'PolicyDocument.Statement[*].Resource'

# 6. Check CloudWatch log group exists
aws logs describe-log-groups --log-group-name-prefix /ecs/report-generator-json --region us-east-2 \
  --query 'logGroups[0].logGroupName'

# 7. Run a test report
aws ecs run-task \
  --cluster report-generation-cluster \
  --task-definition report-generator-json \
  --launch-type FARGATE \
  --network-configuration 'awsvpcConfiguration={subnets=["subnet-06bed7fd9557c191c"],securityGroups=["sg-008a6c6e922e707cc"],assignPublicIp="ENABLED"}' \
  --overrides '{
    "containerOverrides": [{
      "name": "report-generator-json",
      "environment": [
        {"name": "ANNOTATED_VCF_PATH", "value": "s3://exomeinputbucket/A_ALPHA_test/results/final_report.txt"},
        {"name": "VCF_PATH", "value": "s3://exomeinputbucket/A_ALPHA_test/results/raw_variants.vcf"},
        {"name": "TEMPLATE_PATH", "value": "s3://gh-templates/cancer_template.json"},
        {"name": "NAME", "value": "Test Patient"},
        {"name": "ID", "value": "VERIFY-001"},
        {"name": "PROVIDER", "value": "Verification Test"},
        {"name": "OUTPUT_S3_BUCKET", "value": "ghcompletedreports"},
        {"name": "PATIENT_GENDER", "value": "Female"},
        {"name": "GEMINI_API_KEY", "value": "YOUR_GEMINI_KEY"}
      ]
    }]
  }' \
  --region us-east-2 \
  --query 'tasks[0].taskArn'
# Expected: returns a task ARN

# 8. Wait ~5 minutes, then check output
aws s3 ls s3://ghcompletedreports/VERIFY-001 --region us-east-2
# Expected: .html, .json, .pdf files
```

---

## End-to-End Pipeline Flow

```
1. FASTQ uploaded to S3
        ↓
2. Genomics pipeline (GPU EC2) — ~20 min
   FASTQ → BAM → VCF → Annotated VCF → Disease Scores
        ↓
3. Pipeline calls POST /api/amazon/conversion-complete
   Website knows VCF is ready
        ↓
4. Website triggers report generation (ECS RunTask)
        ↓
5. Report generator (Fargate) — ~5-10 min
   Scores → LLM blocks → HTML/JSON/PDF → S3
        ↓
6. Report generator calls POST /api/amazon/report-ready
   Website knows report is viewable
        ↓
7. Provider/patient gets email, views report
```

### Webhook API Reference

Both APIs require the custom auth header:
```
x-auth-amazon: Ax1AAlZCCEdON7WXxZOkUDdGbC-0zuXnCGF6dwl7lor5l+Nukd2yh3HWtoNbo
```

**Report Ready** (called automatically by report generator):
```
POST https://www.genehealth.ai/api/amazon/report-ready
Content-Type: application/json
x-auth-amazon: Ax1AAlZCCEdON7WXxZOkUDdGbC-0zuXnCGF6dwl7lor5l+Nukd2yh3HWtoNbo

{ "path": "GHID12345_Jane_Doe_report_1773899943.html" }
```
Path is relative to `ghcompletedreports` bucket — do NOT include bucket name.

**Conversion Complete** (called by genomics pipeline):
```
POST https://www.genehealth.ai/api/amazon/conversion-complete
Content-Type: application/json
x-auth-amazon: Ax1AAlZCCEdON7WXxZOkUDdGbC-0zuXnCGF6dwl7lor5l+Nukd2yh3HWtoNbo

{ "path": "provider-uploads/sample_001.vcf" }
```
Path is relative to `exomeinputbucket` bucket — do NOT include bucket name.

---

## Redeploying After Code Changes

From the project directory:
```bash
./deploy.sh
```

This builds the Docker image, pushes to ECR, and registers a new task definition. New tasks will automatically use the latest image.
