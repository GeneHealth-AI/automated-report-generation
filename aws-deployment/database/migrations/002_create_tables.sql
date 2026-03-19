-- Migration 002: Create Core Tables
-- Created: 2025-01-26
-- Description: Creates the core tables for the system

BEGIN;

SET search_path TO reports, public;

-- Create patients table
CREATE TABLE IF NOT EXISTS patients (
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

CREATE INDEX idx_patients_external_id ON patients(external_id);
CREATE INDEX idx_patients_created_at ON patients(created_at);

-- Create providers table
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

-- Create report_requests table
CREATE TABLE IF NOT EXISTS report_requests (
    request_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    provider_id UUID REFERENCES providers(provider_id) ON DELETE SET NULL,
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

CREATE INDEX idx_report_requests_patient_id ON report_requests(patient_id);
CREATE INDEX idx_report_requests_status ON report_requests(status);

-- Create generated_reports table
CREATE TABLE IF NOT EXISTS generated_reports (
    report_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id UUID NOT NULL REFERENCES report_requests(request_id) ON DELETE CASCADE,
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

CREATE INDEX idx_generated_reports_request_id ON generated_reports(request_id);

COMMIT;
