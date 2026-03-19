# Terraform variables for Genetic Report Generation System

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "prod"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "genetic-reports"
}

# VPC Configuration
variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Availability zones for resources"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

# ECS Fargate Configuration
variable "fargate_cpu" {
  description = "CPU units for Fargate task (1024 = 1 vCPU)"
  type        = number
  default     = 2048  # 2 vCPUs
}

variable "fargate_memory" {
  description = "Memory for Fargate task in MB"
  type        = number
  default     = 4096  # 4 GB
}

# RDS Configuration
variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.medium"
}

variable "db_name" {
  description = "Database name"
  type        = string
  default     = "genetic_reports"
}

variable "db_username" {
  description = "Database master username"
  type        = string
  default     = "report_admin"
  sensitive   = true
}

variable "db_allocated_storage" {
  description = "Allocated storage for RDS in GB"
  type        = number
  default     = 100
}

variable "db_backup_retention_period" {
  description = "Backup retention period in days"
  type        = number
  default     = 7
}

# S3 Configuration
variable "input_bucket_name" {
  description = "S3 bucket for input VCF files"
  type        = string
  default     = ""  # Will be auto-generated if empty
}

variable "output_bucket_name" {
  description = "S3 bucket for output reports"
  type        = string
  default     = ""  # Will be auto-generated if empty
}

# Lambda Configuration
variable "lambda_memory_size" {
  description = "Memory allocation for Lambda function in MB"
  type        = number
  default     = 512
}

variable "lambda_timeout" {
  description = "Timeout for Lambda function in seconds"
  type        = number
  default     = 60
}

# Secrets Configuration
variable "anthropic_api_key" {
  description = "Anthropic API key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "gemini_api_key" {
  description = "Google Gemini API key"
  type        = string
  sensitive   = true
  default     = ""
}

# Monitoring Configuration
variable "enable_enhanced_monitoring" {
  description = "Enable enhanced CloudWatch monitoring"
  type        = bool
  default     = true
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

# Tags
variable "additional_tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}
