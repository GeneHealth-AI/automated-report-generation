-- Migration 001: Initial Database Setup
-- Created: 2025-01-26
-- Description: Creates the initial database schema for genetic report generation

BEGIN;

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- Create reports schema
CREATE SCHEMA IF NOT EXISTS reports;

COMMIT;
