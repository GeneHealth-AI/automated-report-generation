# Database Documentation - Genetic Report Generation System

## Overview

The system uses PostgreSQL 15.x on Amazon RDS to store report metadata, patient information, and audit trails. This document describes the database schema, relationships, and usage patterns.

## Database Schema

### Entity Relationship Diagram

```
┌─────────────┐         ┌─────────────────┐         ┌──────────────┐
│  patients   │────────▶│ report_requests │◀────────│  providers   │
│             │         │                 │         │              │
│  patient_id │         │   request_id    │         │  provider_id │
│ external_id │         │   patient_id    │         │ provider_name│
│patient_name │         │   provider_id   │         │ organization │
└─────────────┘         │   status        │         └──────────────┘
                        │   vcf_s3_path   │
                        │   focus         │
                        └─────────┬───────┘
                                  │
                    ┌─────────────┴─────────────────┐
                    │                               │
          ┌─────────▼──────────┐         ┌─────────▼────────────┐
          │ generated_reports  │         │ mutations_analyzed   │
          │                    │         │                      │
          │     report_id      │         │   mutation_id        │
          │    request_id      │         │   request_id         │
          │    report_type     │         │   rsid               │
          │    s3_uri          │         │   gene_symbol        │
          │    file_size       │         │   clinical_significance│
          └────────────────────┘         └──────────────────────┘
```

## Table Definitions

### 1. patients

Stores patient information for report generation.

```sql
CREATE TABLE reports.patients (
    patient_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    external_id VARCHAR(255) UNIQUE NOT NULL,
    patient_name VARCHAR(500),
    date_of_birth DATE,
    gender VARCHAR(50),
    email VARCHAR(255),
    phone VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb
);
```

**Indexes**:
- Primary key on `patient_id`
- Unique index on `external_id`
- Index on `created_at` for time-based queries
- GIN index on `metadata` for JSONB queries

**Usage**:
```sql
-- Insert or update patient
INSERT INTO reports.patients (external_id, patient_name, email)
VALUES ('PAT-001', 'John Doe', 'john@example.com')
ON CONFLICT (external_id) DO UPDATE
SET patient_name = EXCLUDED.patient_name,
    updated_at = CURRENT_TIMESTAMP;

-- Query patient
SELECT * FROM reports.patients WHERE external_id = 'PAT-001';
```

### 2. providers

Healthcare providers who order reports.

```sql
CREATE TABLE reports.providers (
    provider_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    provider_name VARCHAR(500) NOT NULL,
    organization VARCHAR(500),
    email VARCHAR(255),
    phone VARCHAR(50),
    license_number VARCHAR(100),
    specialization VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb
);
```

**Usage**:
```sql
-- Create provider
INSERT INTO reports.providers (provider_name, organization, email)
VALUES ('Dr. Jane Smith', 'City Hospital', 'jane@cityhospital.com')
RETURNING provider_id;
```

### 3. report_requests

Tracks all report generation requests and their status.

```sql
CREATE TABLE reports.report_requests (
    request_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES reports.patients(patient_id) ON DELETE CASCADE,
    provider_id UUID REFERENCES reports.providers(provider_id) ON DELETE SET NULL,
    request_type VARCHAR(100) NOT NULL DEFAULT 'full_report',
    focus VARCHAR(500),
    family_history TEXT,
    vcf_s3_path TEXT NOT NULL,
    annotated_vcf_s3_path TEXT,
    template_s3_path TEXT,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    ecs_task_arn VARCHAR(500),
    lambda_request_id VARCHAR(255),
    requested_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    error_details JSONB,
    retry_count INTEGER DEFAULT 0,
    request_metadata JSONB DEFAULT '{}'::jsonb,
    CONSTRAINT valid_status CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'cancelled'))
);
```

**Status Flow**:
```
pending → processing → completed
               ↓
           failed (can retry)
```

**Indexes**:
- Primary key on `request_id`
- Foreign key indexes on `patient_id`, `provider_id`
- Index on `status` for filtering active requests
- Index on `requested_at` for time-range queries
- Index on `focus` for report type queries

**Usage**:
```sql
-- Create report request
INSERT INTO reports.report_requests (
    patient_id,
    provider_id,
    vcf_s3_path,
    focus
)
VALUES (
    '123e4567-e89b-12d3-a456-426614174000',
    '123e4567-e89b-12d3-a456-426614174001',
    's3://bucket/patient.vcf',
    'ADHD'
)
RETURNING request_id;

-- Update status to processing
UPDATE reports.report_requests
SET status = 'processing',
    started_at = CURRENT_TIMESTAMP,
    ecs_task_arn = 'arn:aws:ecs:...'
WHERE request_id = '...';

-- Mark as completed
UPDATE reports.report_requests
SET status = 'completed',
    completed_at = CURRENT_TIMESTAMP
WHERE request_id = '...';

-- Query active requests
SELECT * FROM reports.report_requests
WHERE status IN ('pending', 'processing')
ORDER BY requested_at DESC;
```

### 4. generated_reports

Metadata about generated report files.

```sql
CREATE TABLE reports.generated_reports (
    report_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id UUID NOT NULL REFERENCES reports.report_requests(request_id) ON DELETE CASCADE,
    report_type VARCHAR(50) NOT NULL,
    report_format VARCHAR(50) NOT NULL,
    s3_bucket VARCHAR(255) NOT NULL,
    s3_key TEXT NOT NULL,
    s3_uri TEXT NOT NULL,
    file_size_bytes BIGINT,
    file_hash VARCHAR(128),
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    generation_time_seconds NUMERIC(10, 2),
    report_metadata JSONB DEFAULT '{}'::jsonb,
    version INTEGER DEFAULT 1,
    is_latest BOOLEAN DEFAULT true
);
```

**Report Types**:
- `pdf`: PDF report
- `json`: JSON structured data
- `html`: HTML visual report

**Usage**:
```sql
-- Save generated report
INSERT INTO reports.generated_reports (
    request_id,
    report_type,
    report_format,
    s3_bucket,
    s3_key,
    s3_uri,
    file_size_bytes,
    generation_time_seconds
)
VALUES (
    '...',
    'pdf',
    'standard',
    'output-bucket',
    'reports/patient-123.pdf',
    's3://output-bucket/reports/patient-123.pdf',
    1024000,
    45.5
);

-- Get all reports for a request
SELECT * FROM reports.generated_reports
WHERE request_id = '...'
ORDER BY generated_at DESC;
```

### 5. mutations_analyzed

Details of genetic mutations analyzed in reports.

```sql
CREATE TABLE reports.mutations_analyzed (
    mutation_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id UUID NOT NULL REFERENCES reports.report_requests(request_id) ON DELETE CASCADE,
    rsid VARCHAR(50),
    chromosome VARCHAR(10),
    position BIGINT,
    reference_allele VARCHAR(1000),
    alternate_allele VARCHAR(1000),
    genotype VARCHAR(50),
    variant_type VARCHAR(100),
    clinical_significance VARCHAR(100),
    consequence VARCHAR(255),
    gene_symbol VARCHAR(100),
    gene_id VARCHAR(100),
    transcript_id VARCHAR(100),
    protein_change VARCHAR(500),
    gwas_traits TEXT[],
    gwas_studies INTEGER DEFAULT 0,
    max_p_value NUMERIC,
    disease_associations JSONB DEFAULT '[]'::jsonb,
    drug_interactions JSONB DEFAULT '[]'::jsonb,
    annotation_source VARCHAR(100),
    annotation_version VARCHAR(50),
    confidence_score NUMERIC(5, 4),
    analyzed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    raw_annotation JSONB DEFAULT '{}'::jsonb
);
```

**Indexes**:
- Primary key on `mutation_id`
- Foreign key index on `request_id`
- Index on `rsid` for variant lookups
- Index on `gene_symbol` for gene-based queries
- Index on `clinical_significance` for filtering
- GIN indexes on `gwas_traits`, `disease_associations`

**Usage**:
```sql
-- Save analyzed mutation
INSERT INTO reports.mutations_analyzed (
    request_id,
    rsid,
    gene_symbol,
    clinical_significance,
    gwas_traits
)
VALUES (
    '...',
    'rs1234567',
    'APOE',
    'pathogenic',
    ARRAY['Alzheimer disease', 'Cardiovascular disease']
);

-- Query mutations by gene
SELECT * FROM reports.mutations_analyzed
WHERE gene_symbol = 'APOE'
AND clinical_significance = 'pathogenic';

-- Query mutations with GWAS associations
SELECT * FROM reports.mutations_analyzed
WHERE gwas_traits && ARRAY['ADHD'];
```

### 6. api_usage

Tracks API usage for cost monitoring.

```sql
CREATE TABLE reports.api_usage (
    usage_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id UUID REFERENCES reports.report_requests(request_id) ON DELETE SET NULL,
    api_provider VARCHAR(100) NOT NULL,
    api_model VARCHAR(100),
    api_endpoint VARCHAR(255),
    tokens_input INTEGER,
    tokens_output INTEGER,
    tokens_total INTEGER,
    api_calls_count INTEGER DEFAULT 1,
    estimated_cost_usd NUMERIC(10, 6),
    request_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    response_time_ms INTEGER,
    status VARCHAR(50),
    error_message TEXT,
    usage_metadata JSONB DEFAULT '{}'::jsonb
);
```

**Usage**:
```sql
-- Log API usage
INSERT INTO reports.api_usage (
    request_id,
    api_provider,
    api_model,
    tokens_input,
    tokens_output,
    tokens_total,
    estimated_cost_usd,
    status
)
VALUES (
    '...',
    'anthropic',
    'claude-3-sonnet',
    1000,
    500,
    1500,
    0.015,
    'success'
);

-- Monthly cost summary
SELECT
    api_provider,
    api_model,
    COUNT(*) as total_calls,
    SUM(tokens_total) as total_tokens,
    SUM(estimated_cost_usd) as total_cost
FROM reports.api_usage
WHERE request_timestamp >= DATE_TRUNC('month', CURRENT_DATE)
GROUP BY api_provider, api_model
ORDER BY total_cost DESC;
```

### 7. system_logs

General system logging.

```sql
CREATE TABLE reports.system_logs (
    log_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id UUID REFERENCES reports.report_requests(request_id) ON DELETE SET NULL,
    log_level VARCHAR(20) NOT NULL,
    component VARCHAR(100) NOT NULL,
    message TEXT NOT NULL,
    stack_trace TEXT,
    user_id VARCHAR(255),
    session_id VARCHAR(255),
    logged_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    log_metadata JSONB DEFAULT '{}'::jsonb,
    CONSTRAINT valid_log_level CHECK (log_level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'))
);
```

**Usage**:
```sql
-- Insert log
INSERT INTO reports.system_logs (
    request_id,
    log_level,
    component,
    message
)
VALUES (
    '...',
    'ERROR',
    'report_generator',
    'Failed to generate PDF'
);

-- Query recent errors
SELECT * FROM reports.system_logs
WHERE log_level = 'ERROR'
AND logged_at >= NOW() - INTERVAL '1 day'
ORDER BY logged_at DESC;
```

### 8. audit_trail

Audit trail for compliance.

```sql
CREATE TABLE reports.audit_trail (
    audit_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    table_name VARCHAR(100) NOT NULL,
    record_id UUID NOT NULL,
    action VARCHAR(50) NOT NULL,
    user_id VARCHAR(255),
    user_role VARCHAR(100),
    old_values JSONB,
    new_values JSONB,
    changed_fields TEXT[],
    ip_address INET,
    user_agent TEXT,
    request_id UUID,
    action_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    audit_metadata JSONB DEFAULT '{}'::jsonb,
    CONSTRAINT valid_action CHECK (action IN ('INSERT', 'UPDATE', 'DELETE', 'VIEW', 'DOWNLOAD'))
);
```

**Usage**:
```sql
-- Log audit event
INSERT INTO reports.audit_trail (
    table_name,
    record_id,
    action,
    user_id,
    new_values
)
VALUES (
    'patients',
    '...',
    'INSERT',
    'user@example.com',
    '{"patient_name": "John Doe"}'::jsonb
);
```

## Views

### active_reports

View of currently active report requests.

```sql
CREATE OR REPLACE VIEW reports.active_reports AS
SELECT
    rr.request_id,
    rr.patient_id,
    p.external_id as patient_external_id,
    p.patient_name,
    pr.provider_name,
    rr.focus,
    rr.status,
    rr.requested_at,
    rr.started_at,
    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - rr.requested_at)) / 60 as minutes_elapsed
FROM reports.report_requests rr
LEFT JOIN reports.patients p ON rr.patient_id = p.patient_id
LEFT JOIN reports.providers pr ON rr.provider_id = pr.provider_id
WHERE rr.status IN ('pending', 'processing');
```

### report_statistics

Daily report statistics.

```sql
CREATE OR REPLACE VIEW reports.report_statistics AS
SELECT
    DATE(rr.requested_at) as report_date,
    rr.focus,
    COUNT(*) as total_requests,
    COUNT(*) FILTER (WHERE rr.status = 'completed') as completed,
    COUNT(*) FILTER (WHERE rr.status = 'failed') as failed,
    AVG(EXTRACT(EPOCH FROM (rr.completed_at - rr.started_at))) as avg_processing_time_seconds
FROM reports.report_requests rr
GROUP BY DATE(rr.requested_at), rr.focus
ORDER BY report_date DESC;
```

### api_usage_summary

API usage and cost summary.

```sql
CREATE OR REPLACE VIEW reports.api_usage_summary AS
SELECT
    DATE(au.request_timestamp) as usage_date,
    au.api_provider,
    au.api_model,
    COUNT(*) as total_calls,
    SUM(au.tokens_total) as total_tokens,
    SUM(au.estimated_cost_usd) as total_cost_usd,
    AVG(au.response_time_ms) as avg_response_time_ms
FROM reports.api_usage au
GROUP BY DATE(au.request_timestamp), au.api_provider, au.api_model
ORDER BY usage_date DESC, api_provider;
```

## Functions and Triggers

### Auto-update timestamp trigger

```sql
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_patients_updated_at BEFORE UPDATE ON reports.patients
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

### Status change logging trigger

```sql
CREATE OR REPLACE FUNCTION log_report_status_change()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.status IS DISTINCT FROM NEW.status THEN
        INSERT INTO reports.system_logs (request_id, log_level, component, message, log_metadata)
        VALUES (
            NEW.request_id,
            'INFO',
            'report_status',
            format('Report status changed from %s to %s', OLD.status, NEW.status),
            jsonb_build_object('old_status', OLD.status, 'new_status', NEW.status)
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER log_report_status_changes AFTER UPDATE ON reports.report_requests
    FOR EACH ROW EXECUTE FUNCTION log_report_status_change();
```

## Common Queries

### Get report with all details

```sql
SELECT
    rr.*,
    p.external_id,
    p.patient_name,
    pr.provider_name,
    array_agg(gr.s3_uri) as report_files,
    COUNT(DISTINCT ma.mutation_id) as mutations_count
FROM reports.report_requests rr
LEFT JOIN reports.patients p ON rr.patient_id = p.patient_id
LEFT JOIN reports.providers pr ON rr.provider_id = pr.provider_id
LEFT JOIN reports.generated_reports gr ON rr.request_id = gr.request_id
LEFT JOIN reports.mutations_analyzed ma ON rr.request_id = ma.request_id
WHERE rr.request_id = '...'
GROUP BY rr.request_id, p.external_id, p.patient_name, pr.provider_name;
```

### Find failed reports for retry

```sql
SELECT *
FROM reports.report_requests
WHERE status = 'failed'
AND retry_count < 3
AND requested_at >= NOW() - INTERVAL '1 day'
ORDER BY requested_at DESC;
```

### Cost analysis by focus

```sql
SELECT
    rr.focus,
    COUNT(*) as total_reports,
    SUM(au.estimated_cost_usd) as total_cost,
    AVG(au.estimated_cost_usd) as avg_cost_per_report
FROM reports.report_requests rr
JOIN reports.api_usage au ON rr.request_id = au.request_id
WHERE rr.completed_at >= DATE_TRUNC('month', CURRENT_DATE)
GROUP BY rr.focus
ORDER BY total_cost DESC;
```

## Maintenance

### Vacuum and Analyze

```sql
-- Run weekly
VACUUM ANALYZE reports.report_requests;
VACUUM ANALYZE reports.mutations_analyzed;
VACUUM ANALYZE reports.api_usage;
```

### Archive old data

```sql
-- Archive reports older than 1 year
BEGIN;

-- Move to archive table (create if needed)
CREATE TABLE IF NOT EXISTS reports.report_requests_archive (LIKE reports.report_requests INCLUDING ALL);

INSERT INTO reports.report_requests_archive
SELECT * FROM reports.report_requests
WHERE completed_at < NOW() - INTERVAL '1 year';

DELETE FROM reports.report_requests
WHERE completed_at < NOW() - INTERVAL '1 year';

COMMIT;
```

## Performance Optimization

### Suggested Indexes

```sql
-- Additional indexes for common queries
CREATE INDEX idx_report_requests_completed_at ON reports.report_requests(completed_at)
WHERE completed_at IS NOT NULL;

CREATE INDEX idx_mutations_analyzed_pathogenic ON reports.mutations_analyzed(clinical_significance)
WHERE clinical_significance IN ('pathogenic', 'likely_pathogenic');

CREATE INDEX idx_api_usage_cost ON reports.api_usage(api_provider, request_timestamp, estimated_cost_usd);
```

### Partitioning (for high-volume deployments)

```sql
-- Partition report_requests by month
CREATE TABLE reports.report_requests_partitioned (
    LIKE reports.report_requests INCLUDING ALL
) PARTITION BY RANGE (requested_at);

CREATE TABLE reports.report_requests_2025_01 PARTITION OF reports.report_requests_partitioned
FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
```

## Backup and Recovery

### Manual Backup

```bash
# Backup entire database
pg_dump -h <host> -U report_admin -d genetic_reports > backup_$(date +%Y%m%d).sql

# Backup specific schema
pg_dump -h <host> -U report_admin -d genetic_reports -n reports > reports_backup.sql
```

### Restore

```bash
psql -h <host> -U report_admin -d genetic_reports < backup.sql
```
