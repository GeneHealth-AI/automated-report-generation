# Genetic Report Generation System - Architecture Documentation

## System Overview

The Genetic Report Generation System is a cloud-native application designed to process genomic data (VCF files) and generate comprehensive medical reports using AI-powered analysis.

## Architecture Diagram

```
┌────────────────────────────────────────────────────────────────────────┐
│                          CLIENT APPLICATIONS                            │
└───────────────────────────────┬────────────────────────────────────────┘
                                │
                                │ HTTPS
                                │
                ┌───────────────▼────────────────┐
                │      API Gateway (REST)        │
                │  - Rate Limiting               │
                │  - Authentication (IAM/API Key)│
                └───────────────┬────────────────┘
                                │
                                │ Invoke
                                │
                ┌───────────────▼────────────────┐
                │      Lambda Function           │
                │  - Request Validation          │
                │  - Task Orchestration          │
                │  - Database Logging            │
                └───────┬───────────────┬────────┘
                        │               │
                ┌───────▼──────┐        │
                │  RDS         │        │
                │  PostgreSQL  │        │
                │  - Metadata  │        │
                │  - Audit     │        │
                └──────────────┘        │
                                        │ RunTask
                                        │
                        ┌───────────────▼────────────────┐
                        │      ECS Fargate Cluster       │
                        │                                 │
                        │  ┌─────────────────────────┐   │
                        │  │   Report Generator      │   │
                        │  │   Container             │   │
                        │  │                         │   │
                        │  │  - Download VCF files   │   │
                        │  │  - Enrich positions     │   │
                        │  │  - Generate blocks      │   │
                        │  │  - Create PDF/JSON/HTML │   │
                        │  │  - Upload to S3         │   │
                        │  └─────────┬───────────────┘   │
                        │            │                    │
                        └────────────┼────────────────────┘
                                     │
        ┌────────────────────────────┼────────────────────────────┐
        │                            │                             │
┌───────▼────────┐         ┌────────▼──────┐          ┌──────────▼─────────┐
│  S3 - Input    │         │  S3 - GWAS    │          │  S3 - Output       │
│  - VCF files   │         │  - Catalog    │          │  - PDFs            │
│  - Templates   │         │  - Reference  │          │  - JSON reports    │
└────────────────┘         └───────────────┘          │  - HTML reports    │
                                                       └────────────────────┘

┌────────────────────────────────────────────────────────────────────────┐
│                    EXTERNAL SERVICES                                    │
├────────────────────────────────────────────────────────────────────────┤
│  - Anthropic Claude API (AI analysis)                                  │
│  - Google Gemini API (Variant classification)                          │
└────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────┐
│                    MONITORING & LOGGING                                 │
├────────────────────────────────────────────────────────────────────────┤
│  - CloudWatch Logs (All components)                                    │
│  - CloudWatch Metrics (Performance monitoring)                          │
│  - CloudWatch Alarms (Alerting)                                        │
└────────────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. API Gateway

**Purpose**: Entry point for all API requests

**Features**:
- RESTful API endpoints
- API key authentication
- Request/response validation
- Rate limiting and throttling
- CORS support
- Request/response logging

**Endpoints**:
- `POST /generate` - Trigger report generation

**Request Format**:
```json
{
  "annotated_vcf_path": "s3://bucket/annotated.vcf",
  "vcf_path": "s3://bucket/input.vcf",
  "template_path": "s3://bucket/template.json",
  "name": "Patient Name",
  "id": "patient_id",
  "provider": "Provider Name",
  "output_s3_bucket": "output-bucket"
}
```

### 2. Lambda Function (Orchestrator)

**Purpose**: Orchestrates the report generation workflow

**Runtime**: Python 3.9
**Memory**: 512 MB
**Timeout**: 60 seconds
**VPC**: Yes (for RDS access)

**Responsibilities**:
1. Validate incoming requests
2. Create database records for tracking
3. Trigger ECS Fargate tasks
4. Return task status to client
5. Handle errors and retries

**Environment Variables**:
- `ECS_CLUSTER_NAME`: ECS cluster name
- `ECS_TASK_DEFINITION`: Task definition family
- `ECS_SUBNET_IDS`: VPC subnet IDs
- `ECS_SECURITY_GROUP_ID`: Security group ID
- `OUTPUT_S3_BUCKET`: Default output bucket
- `DB_SECRET_ARN`: Database credentials secret

### 3. ECS Fargate (Report Generator)

**Purpose**: Heavy compute for report generation

**Configuration**:
- **CPU**: 2 vCPUs (2048 units)
- **Memory**: 4 GB (4096 MB)
- **Launch Type**: Fargate
- **Network**: awsvpc mode (private subnets with NAT)

**Container Image**: Custom Docker image from ECR

**Processing Steps**:
1. **Download Input Files**: Fetch VCF files from S3
2. **Mutation Extraction**: Parse VCF and extract mutations
3. **GWAS Enrichment**: Match mutations with GWAS catalog
4. **AI Analysis**: Use Anthropic/Gemini for clinical interpretation
5. **Block Generation**: Create report sections
6. **Report Assembly**: Generate PDF, JSON, HTML outputs
7. **Upload Results**: Save reports to S3
8. **Update Database**: Record completion status

**Environment Variables**:
- `ANNOTATED_VCF_PATH`: S3 path to annotated VCF
- `VCF_PATH`: S3 path to input VCF
- `TEMPLATE`: Report template JSON
- `NAME`: Patient name
- `ID`: Patient ID
- `PROVIDER`: Provider name
- `OUTPUT_S3_BUCKET`: Output bucket
- `ANTHROPIC_API_KEY`: Retrieved from Secrets Manager
- `GEMINI_API_KEY`: Retrieved from Secrets Manager
- `DB_*`: Database connection details

### 4. RDS PostgreSQL Database

**Purpose**: Store report metadata, queries, and audit trails

**Configuration**:
- **Engine**: PostgreSQL 15.4
- **Instance Class**: db.t3.medium
- **Storage**: 100 GB (GP3, auto-scaling)
- **Multi-AZ**: Yes (production)
- **Backups**: 7-day retention
- **Encryption**: At rest

**Key Tables**:
- `patients`: Patient information
- `report_requests`: Request tracking
- `generated_reports`: Report metadata
- `mutations_analyzed`: Genetic variants analyzed
- `api_usage`: Cost tracking
- `system_logs`: Application logs
- `audit_trail`: Compliance logging

### 5. S3 Buckets

**Input Bucket**:
- Stores VCF files and templates
- Versioning enabled
- Lifecycle: Delete after 90 days
- Server-side encryption (AES256)

**Output Bucket**:
- Stores generated reports
- Versioning enabled
- Lifecycle: Intelligent-Tiering after 30 days
- Server-side encryption (AES256)

**GWAS Data Bucket**:
- Stores GWAS catalog and reference data
- Versioning enabled
- No lifecycle policy (permanent storage)

### 6. Secrets Manager

**Stored Secrets**:
1. **Database Credentials**: RDS username/password
2. **Anthropic API Key**: Claude API access
3. **Gemini API Key**: Google AI access

**Access Pattern**:
- Retrieved by ECS tasks at runtime
- Cached in memory for task duration
- Never logged or exposed

### 7. CloudWatch

**Log Groups**:
- `/ecs/genetic-reports-{env}`: Container logs
- `/aws/lambda/genetic-reports-fargate-trigger-{env}`: Lambda logs
- `/aws/apigateway/genetic-reports-{env}`: API logs

**Metrics**:
- ECS CPU/Memory utilization
- Lambda invocation count, errors, duration
- API Gateway requests, latency, errors
- RDS connections, CPU, storage

**Alarms**:
- High CPU/Memory on ECS
- Lambda errors exceed threshold
- RDS storage low
- API Gateway error rate

## Data Flow

### Report Generation Flow

```
1. Client → API Gateway
   POST /generate with request payload

2. API Gateway → Lambda
   Validates request, invokes Lambda

3. Lambda → RDS
   Creates patient and report_request records

4. Lambda → ECS
   Launches Fargate task with environment variables

5. ECS Task → S3
   Downloads VCF files and template

6. ECS Task → GWAS Catalog
   Reads GWAS data from S3

7. ECS Task → Anthropic/Gemini APIs
   Sends variants for clinical interpretation

8. ECS Task → RDS
   Logs API usage, updates status

9. ECS Task → Report Generation
   Creates PDF, JSON, HTML reports

10. ECS Task → S3
    Uploads generated reports

11. ECS Task → RDS
    Updates report_request status to "completed"

12. Client ← API Gateway
    Returns task ARN and status
```

## Security Architecture

### Network Security

**VPC Layout**:
- Public Subnets: NAT Gateways, Bastion (optional)
- Private Subnets: ECS Tasks, Lambda
- Database Subnets: RDS instances

**Security Groups**:
- ALB SG: Allow 443 from internet
- ECS SG: Allow HTTPS out, PostgreSQL to RDS
- RDS SG: Allow PostgreSQL from ECS/Lambda
- Lambda SG: Allow all outbound

### IAM Roles and Policies

**ECS Task Execution Role**:
- ECR image pull permissions
- CloudWatch Logs write permissions
- Secrets Manager read permissions

**ECS Task Role**:
- S3 read/write permissions (input/output buckets)
- Secrets Manager read permissions
- RDS connect permissions

**Lambda Execution Role**:
- ECS RunTask permissions
- S3 read/write permissions
- RDS connect permissions
- CloudWatch Logs write permissions

### Encryption

**At Rest**:
- S3: SSE-S3 (AES-256)
- RDS: AWS-managed keys
- Secrets Manager: AWS-managed keys

**In Transit**:
- API Gateway: TLS 1.2+
- S3: HTTPS only
- RDS: SSL/TLS connections

## Scalability

### Horizontal Scaling

**ECS Fargate**:
- No upper limit on concurrent tasks
- Lambda can launch multiple tasks in parallel
- Each task is independent and stateless

**Lambda**:
- Default: 1000 concurrent executions
- Can request increase from AWS

**RDS**:
- Read replicas for read-heavy workloads
- Connection pooling in application

### Vertical Scaling

**ECS Task Size**:
- Can increase CPU/memory via Terraform variables
- Supported ranges: 0.25-4 vCPU, 0.5-30 GB memory

**RDS Instance**:
- Can resize instance class with minimal downtime
- Storage auto-scaling enabled

### Cost vs. Performance Trade-offs

**Fargate Spot**:
- 70% cost savings
- Suitable for non-time-critical reports
- May be interrupted (rare)

**Reserved Instances**:
- RDS: Up to 60% savings with 1-year commitment
- Fargate Savings Plans: Up to 50% savings

## High Availability

**Multi-AZ Deployment**:
- RDS: Automatic failover to standby
- NAT Gateways: One per AZ
- ECS Tasks: Distributed across AZs

**Backup and Recovery**:
- RDS: Automated daily backups, 7-day retention
- S3: Versioning enabled, cross-region replication (optional)

**Disaster Recovery**:
- RTO (Recovery Time Objective): < 1 hour
- RPO (Recovery Point Objective): < 5 minutes

## Monitoring and Observability

**Key Metrics to Monitor**:

1. **Performance**:
   - Report generation time
   - API response time
   - ECS task duration

2. **Errors**:
   - Lambda error rate
   - ECS task failures
   - API 5xx errors

3. **Cost**:
   - API usage (Anthropic, Gemini)
   - ECS task hours
   - Data transfer

4. **Usage**:
   - Reports generated per day
   - Active users
   - Storage growth

**Dashboards**:
- CloudWatch Dashboard with key metrics
- RDS Performance Insights
- ECS Container Insights

## Future Enhancements

1. **Caching Layer**: Redis for frequently accessed data
2. **Queue System**: SQS for asynchronous processing
3. **Batch Processing**: Process multiple reports in parallel
4. **Machine Learning**: Train custom models for variant interpretation
5. **API Versioning**: Support multiple API versions
6. **GraphQL API**: Alternative to REST
7. **WebSocket Support**: Real-time status updates
8. **Multi-Region**: Deploy to multiple AWS regions
