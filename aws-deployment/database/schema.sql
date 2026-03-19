-- Database Schema for Genetic Report Generation System
-- PostgreSQL 15.x

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- Create schema for better organization
CREATE SCHEMA IF NOT EXISTS reports;

-- Set search path
SET search_path TO reports, public;

-- ============================================================================
-- Table: patients
-- Stores basic patient information
-- ============================================================================
CREATE TABLE IF NOT EXISTS patients (
    patient_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    external_id VARCHAR(255) UNIQUE NOT NULL,  -- External patient ID from client system
    patient_name VARCHAR(500),
    date_of_birth DATE,
    gender VARCHAR(50),
    email VARCHAR(255),
    phone VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Indexes
    CONSTRAINT patients_external_id_unique UNIQUE (external_id)
);

CREATE INDEX idx_patients_external_id ON patients(external_id);
CREATE INDEX idx_patients_created_at ON patients(created_at);
CREATE INDEX idx_patients_metadata_gin ON patients USING gin(metadata);

-- ============================================================================
-- Table: providers
-- Stores healthcare provider information
-- ============================================================================
CREATE TABLE IF NOT EXISTS providers (
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

CREATE INDEX idx_providers_name ON providers(provider_name);
CREATE INDEX idx_providers_organization ON providers(organization);

-- ============================================================================
-- Table: report_requests
-- Stores report generation requests and their status
-- ============================================================================
CREATE TABLE IF NOT EXISTS report_requests (
    request_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    provider_id UUID REFERENCES providers(provider_id) ON DELETE SET NULL,

    -- Request details
    request_type VARCHAR(100) NOT NULL DEFAULT 'full_report',  -- full_report, summary, custom
    focus VARCHAR(500),  -- e.g., "ADHD", "Cardiovascular Disease", "Cancer Risk"
    family_history TEXT,

    -- File locations
    vcf_s3_path TEXT NOT NULL,
    annotated_vcf_s3_path TEXT,
    template_s3_path TEXT,

    -- Status tracking
    status VARCHAR(50) NOT NULL DEFAULT 'pending',  -- pending, processing, completed, failed
    ecs_task_arn VARCHAR(500),
    lambda_request_id VARCHAR(255),

    -- Timestamps
    requested_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,

    -- Error handling
    error_message TEXT,
    error_details JSONB,
    retry_count INTEGER DEFAULT 0,

    -- Metadata
    request_metadata JSONB DEFAULT '{}'::jsonb,

    -- Constraints
    CONSTRAINT valid_status CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'cancelled'))
);

CREATE INDEX idx_report_requests_patient_id ON report_requests(patient_id);
CREATE INDEX idx_report_requests_provider_id ON report_requests(provider_id);
CREATE INDEX idx_report_requests_status ON report_requests(status);
CREATE INDEX idx_report_requests_requested_at ON report_requests(requested_at);
CREATE INDEX idx_report_requests_focus ON report_requests(focus);

-- ============================================================================
-- Table: generated_reports
-- Stores metadata about generated reports
-- ============================================================================
CREATE TABLE IF NOT EXISTS generated_reports (
    report_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id UUID NOT NULL REFERENCES report_requests(request_id) ON DELETE CASCADE,

    -- Report details
    report_type VARCHAR(50) NOT NULL,  -- pdf, json, html
    report_format VARCHAR(50) NOT NULL,  -- standard, enhanced, summary

    -- File locations
    s3_bucket VARCHAR(255) NOT NULL,
    s3_key TEXT NOT NULL,
    s3_uri TEXT NOT NULL,

    -- File metadata
    file_size_bytes BIGINT,
    file_hash VARCHAR(128),

    -- Generation details
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    generation_time_seconds NUMERIC(10, 2),

    -- Report metadata
    report_metadata JSONB DEFAULT '{}'::jsonb,

    -- Version control
    version INTEGER DEFAULT 1,
    is_latest BOOLEAN DEFAULT true
);

CREATE INDEX idx_generated_reports_request_id ON generated_reports(request_id);
CREATE INDEX idx_generated_reports_type ON generated_reports(report_type);
CREATE INDEX idx_generated_reports_generated_at ON generated_reports(generated_at);
CREATE INDEX idx_generated_reports_s3_uri ON generated_reports(s3_uri);
CREATE INDEX idx_generated_reports_latest ON generated_reports(is_latest) WHERE is_latest = true;

-- ============================================================================
-- Table: mutations_analyzed
-- Stores information about mutations analyzed in each report
-- ============================================================================
CREATE TABLE IF NOT EXISTS mutations_analyzed (
    mutation_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id UUID NOT NULL REFERENCES report_requests(request_id) ON DELETE CASCADE,

    -- Mutation identification
    rsid VARCHAR(50),
    chromosome VARCHAR(10),
    position BIGINT,
    reference_allele VARCHAR(1000),
    alternate_allele VARCHAR(1000),
    genotype VARCHAR(50),

    -- Classification
    variant_type VARCHAR(100),  -- SNP, insertion, deletion, etc.
    clinical_significance VARCHAR(100),  -- benign, pathogenic, VUS, etc.
    consequence VARCHAR(255),  -- missense, synonymous, etc.

    -- Associated information
    gene_symbol VARCHAR(100),
    gene_id VARCHAR(100),
    transcript_id VARCHAR(100),
    protein_change VARCHAR(500),

    -- GWAS associations
    gwas_traits TEXT[],
    gwas_studies INTEGER DEFAULT 0,
    max_p_value NUMERIC,

    -- Clinical data
    disease_associations JSONB DEFAULT '[]'::jsonb,
    drug_interactions JSONB DEFAULT '[]'::jsonb,

    -- Metadata
    annotation_source VARCHAR(100),
    annotation_version VARCHAR(50),
    confidence_score NUMERIC(5, 4),

    -- Timestamps
    analyzed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Additional data
    raw_annotation JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_mutations_analyzed_request_id ON mutations_analyzed(request_id);
CREATE INDEX idx_mutations_analyzed_rsid ON mutations_analyzed(rsid);
CREATE INDEX idx_mutations_analyzed_gene_symbol ON mutations_analyzed(gene_symbol);
CREATE INDEX idx_mutations_analyzed_clinical_significance ON mutations_analyzed(clinical_significance);
CREATE INDEX idx_mutations_analyzed_gwas_traits_gin ON mutations_analyzed USING gin(gwas_traits);
CREATE INDEX idx_mutations_analyzed_disease_associations_gin ON mutations_analyzed USING gin(disease_associations);

-- ============================================================================
-- Table: api_usage
-- Tracks API usage for billing and monitoring
-- ============================================================================
CREATE TABLE IF NOT EXISTS api_usage (
    usage_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id UUID REFERENCES report_requests(request_id) ON DELETE SET NULL,

    -- API details
    api_provider VARCHAR(100) NOT NULL,  -- anthropic, gemini, etc.
    api_model VARCHAR(100),
    api_endpoint VARCHAR(255),

    -- Usage metrics
    tokens_input INTEGER,
    tokens_output INTEGER,
    tokens_total INTEGER,
    api_calls_count INTEGER DEFAULT 1,

    -- Cost tracking
    estimated_cost_usd NUMERIC(10, 6),

    -- Timing
    request_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    response_time_ms INTEGER,

    -- Status
    status VARCHAR(50),  -- success, error, timeout
    error_message TEXT,

    -- Metadata
    usage_metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_api_usage_request_id ON api_usage(request_id);
CREATE INDEX idx_api_usage_provider ON api_usage(api_provider);
CREATE INDEX idx_api_usage_timestamp ON api_usage(request_timestamp);
CREATE INDEX idx_api_usage_status ON api_usage(status);

-- ============================================================================
-- Table: system_logs
-- General system logging table
-- ============================================================================
CREATE TABLE IF NOT EXISTS system_logs (
    log_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id UUID REFERENCES report_requests(request_id) ON DELETE SET NULL,

    -- Log details
    log_level VARCHAR(20) NOT NULL,  -- DEBUG, INFO, WARNING, ERROR, CRITICAL
    component VARCHAR(100) NOT NULL,  -- lambda, fargate, rds, etc.
    message TEXT NOT NULL,

    -- Context
    stack_trace TEXT,
    user_id VARCHAR(255),
    session_id VARCHAR(255),

    -- Timestamp
    logged_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Additional context
    log_metadata JSONB DEFAULT '{}'::jsonb,

    CONSTRAINT valid_log_level CHECK (log_level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'))
);

CREATE INDEX idx_system_logs_request_id ON system_logs(request_id);
CREATE INDEX idx_system_logs_level ON system_logs(log_level);
CREATE INDEX idx_system_logs_component ON system_logs(component);
CREATE INDEX idx_system_logs_logged_at ON system_logs(logged_at);
CREATE INDEX idx_system_logs_metadata_gin ON system_logs USING gin(log_metadata);

-- ============================================================================
-- Table: audit_trail
-- Audit trail for compliance and tracking
-- ============================================================================
CREATE TABLE IF NOT EXISTS audit_trail (
    audit_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Entity tracking
    table_name VARCHAR(100) NOT NULL,
    record_id UUID NOT NULL,

    -- Action tracking
    action VARCHAR(50) NOT NULL,  -- INSERT, UPDATE, DELETE, VIEW
    user_id VARCHAR(255),
    user_role VARCHAR(100),

    -- Changes
    old_values JSONB,
    new_values JSONB,
    changed_fields TEXT[],

    -- Context
    ip_address INET,
    user_agent TEXT,
    request_id UUID,

    -- Timestamp
    action_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Metadata
    audit_metadata JSONB DEFAULT '{}'::jsonb,

    CONSTRAINT valid_action CHECK (action IN ('INSERT', 'UPDATE', 'DELETE', 'VIEW', 'DOWNLOAD'))
);

CREATE INDEX idx_audit_trail_table_name ON audit_trail(table_name);
CREATE INDEX idx_audit_trail_record_id ON audit_trail(record_id);
CREATE INDEX idx_audit_trail_action ON audit_trail(action);
CREATE INDEX idx_audit_trail_user_id ON audit_trail(user_id);
CREATE INDEX idx_audit_trail_timestamp ON audit_trail(action_timestamp);

-- ============================================================================
-- Views
-- ============================================================================

-- View: Active report requests
CREATE OR REPLACE VIEW active_reports AS
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
FROM report_requests rr
LEFT JOIN patients p ON rr.patient_id = p.patient_id
LEFT JOIN providers pr ON rr.provider_id = pr.provider_id
WHERE rr.status IN ('pending', 'processing');

-- View: Report statistics
CREATE OR REPLACE VIEW report_statistics AS
SELECT
    DATE(rr.requested_at) as report_date,
    rr.focus,
    COUNT(*) as total_requests,
    COUNT(*) FILTER (WHERE rr.status = 'completed') as completed,
    COUNT(*) FILTER (WHERE rr.status = 'failed') as failed,
    COUNT(*) FILTER (WHERE rr.status = 'processing') as processing,
    AVG(EXTRACT(EPOCH FROM (rr.completed_at - rr.started_at))) as avg_processing_time_seconds
FROM report_requests rr
GROUP BY DATE(rr.requested_at), rr.focus
ORDER BY report_date DESC;

-- View: API usage summary
CREATE OR REPLACE VIEW api_usage_summary AS
SELECT
    DATE(au.request_timestamp) as usage_date,
    au.api_provider,
    au.api_model,
    COUNT(*) as total_calls,
    SUM(au.tokens_total) as total_tokens,
    SUM(au.estimated_cost_usd) as total_cost_usd,
    AVG(au.response_time_ms) as avg_response_time_ms
FROM api_usage au
GROUP BY DATE(au.request_timestamp), au.api_provider, au.api_model
ORDER BY usage_date DESC, api_provider;

-- ============================================================================
-- Functions
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for updated_at
CREATE TRIGGER update_patients_updated_at BEFORE UPDATE ON patients
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_providers_updated_at BEFORE UPDATE ON providers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function to log report status changes
CREATE OR REPLACE FUNCTION log_report_status_change()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.status IS DISTINCT FROM NEW.status THEN
        INSERT INTO system_logs (request_id, log_level, component, message, log_metadata)
        VALUES (
            NEW.request_id,
            'INFO',
            'report_status',
            format('Report status changed from %s to %s', OLD.status, NEW.status),
            jsonencode(('{"old_status": "' || OLD.status || '", "new_status": "' || NEW.status || '"}')::jsonb)
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER log_report_status_changes AFTER UPDATE ON report_requests
    FOR EACH ROW EXECUTE FUNCTION log_report_status_change();

-- ============================================================================
-- Initial Data / Seed Data (Optional)
-- ============================================================================

-- Insert a default provider for system-generated reports
INSERT INTO providers (provider_name, organization, email, specialization, metadata)
VALUES (
    'System Administrator',
    'Genetic Reports System',
    'admin@example.com',
    'System',
    '{"is_system": true}'::jsonb
)
ON CONFLICT DO NOTHING;

-- Grant permissions (adjust as needed for your environment)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA reports TO report_admin;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA reports TO report_admin;
-- GRANT USAGE ON SCHEMA reports TO report_admin;

-- Comments for documentation
COMMENT ON SCHEMA reports IS 'Schema for genetic report generation system';
COMMENT ON TABLE patients IS 'Stores patient information for report generation';
COMMENT ON TABLE providers IS 'Healthcare providers who order reports';
COMMENT ON TABLE report_requests IS 'Tracks all report generation requests and their status';
COMMENT ON TABLE generated_reports IS 'Metadata about generated report files';
COMMENT ON TABLE mutations_analyzed IS 'Details of genetic mutations analyzed in reports';
COMMENT ON TABLE api_usage IS 'Tracks API usage for cost monitoring and optimization';
COMMENT ON TABLE system_logs IS 'System-wide logging for debugging and monitoring';
COMMENT ON TABLE audit_trail IS 'Audit trail for compliance and security';
