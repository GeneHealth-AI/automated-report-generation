# S3 Buckets for Genetic Report Generation System

locals {
  input_bucket_name  = var.input_bucket_name != "" ? var.input_bucket_name : "${var.project_name}-input-${data.aws_caller_identity.current.account_id}-${var.environment}"
  output_bucket_name = var.output_bucket_name != "" ? var.output_bucket_name : "${var.project_name}-output-${data.aws_caller_identity.current.account_id}-${var.environment}"
}

# Input S3 Bucket (for VCF files and templates)
resource "aws_s3_bucket" "input" {
  bucket = local.input_bucket_name

  tags = {
    Name        = "${var.project_name}-input-${var.environment}"
    Purpose     = "Input VCF files and templates"
    Environment = var.environment
  }
}

# Input Bucket - Versioning
resource "aws_s3_bucket_versioning" "input" {
  bucket = aws_s3_bucket.input.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Input Bucket - Encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "input" {
  bucket = aws_s3_bucket.input.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Input Bucket - Public Access Block
resource "aws_s3_bucket_public_access_block" "input" {
  bucket = aws_s3_bucket.input.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Input Bucket - Lifecycle Policy
resource "aws_s3_bucket_lifecycle_configuration" "input" {
  bucket = aws_s3_bucket.input.id

  rule {
    id     = "delete-old-files"
    status = "Enabled"

    expiration {
      days = 90  # Delete input files after 90 days
    }

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }

  rule {
    id     = "transition-to-glacier"
    status = "Enabled"

    transition {
      days          = 30
      storage_class = "GLACIER"
    }
  }
}

# Output S3 Bucket (for generated reports)
resource "aws_s3_bucket" "output" {
  bucket = local.output_bucket_name

  tags = {
    Name        = "${var.project_name}-output-${var.environment}"
    Purpose     = "Generated reports (PDF, JSON, HTML)"
    Environment = var.environment
  }
}

# Output Bucket - Versioning
resource "aws_s3_bucket_versioning" "output" {
  bucket = aws_s3_bucket.output.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Output Bucket - Encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "output" {
  bucket = aws_s3_bucket.output.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Output Bucket - Public Access Block
resource "aws_s3_bucket_public_access_block" "output" {
  bucket = aws_s3_bucket.output.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Output Bucket - Lifecycle Policy
resource "aws_s3_bucket_lifecycle_configuration" "output" {
  bucket = aws_s3_bucket.output.id

  rule {
    id     = "transition-to-intelligent-tiering"
    status = "Enabled"

    transition {
      days          = 30
      storage_class = "INTELLIGENT_TIERING"
    }
  }

  rule {
    id     = "transition-to-glacier-deep-archive"
    status = "Enabled"

    transition {
      days          = 365
      storage_class = "DEEP_ARCHIVE"
    }
  }
}

# GWAS Data Bucket (for storing GWAS catalog files)
resource "aws_s3_bucket" "gwas_data" {
  bucket = "${var.project_name}-gwas-data-${data.aws_caller_identity.current.account_id}-${var.environment}"

  tags = {
    Name        = "${var.project_name}-gwas-data-${var.environment}"
    Purpose     = "GWAS catalog and reference data"
    Environment = var.environment
  }
}

# GWAS Bucket - Versioning
resource "aws_s3_bucket_versioning" "gwas_data" {
  bucket = aws_s3_bucket.gwas_data.id

  versioning_configuration {
    status = "Enabled"
  }
}

# GWAS Bucket - Encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "gwas_data" {
  bucket = aws_s3_bucket.gwas_data.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# GWAS Bucket - Public Access Block
resource "aws_s3_bucket_public_access_block" "gwas_data" {
  bucket = aws_s3_bucket.gwas_data.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# CloudWatch Metrics for S3
resource "aws_cloudwatch_metric_alarm" "s3_4xx_errors" {
  alarm_name          = "${var.project_name}-s3-4xx-errors-${var.environment}"
  alarm_description   = "S3 4XX errors are too high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "4xxErrors"
  namespace           = "AWS/S3"
  period              = 300
  statistic           = "Sum"
  threshold           = 10

  dimensions = {
    BucketName = aws_s3_bucket.input.id
  }

  alarm_actions = []  # Add SNS topic ARN here for notifications
}
