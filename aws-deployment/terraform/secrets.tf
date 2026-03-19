# AWS Secrets Manager for API Keys and Sensitive Data

# Anthropic API Key Secret
resource "aws_secretsmanager_secret" "anthropic_api_key" {
  name_prefix             = "${var.project_name}-anthropic-key-"
  description             = "Anthropic API Key for Claude"
  recovery_window_in_days = 7

  tags = {
    Name        = "${var.project_name}-anthropic-key-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_secretsmanager_secret_version" "anthropic_api_key" {
  secret_id     = aws_secretsmanager_secret.anthropic_api_key.id
  secret_string = var.anthropic_api_key != "" ? var.anthropic_api_key : "PLACEHOLDER_CHANGE_ME"

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# Google Gemini API Key Secret
resource "aws_secretsmanager_secret" "gemini_api_key" {
  name_prefix             = "${var.project_name}-gemini-key-"
  description             = "Google Gemini API Key"
  recovery_window_in_days = 7

  tags = {
    Name        = "${var.project_name}-gemini-key-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_secretsmanager_secret_version" "gemini_api_key" {
  secret_id     = aws_secretsmanager_secret.gemini_api_key.id
  secret_string = var.gemini_api_key != "" ? var.gemini_api_key : "PLACEHOLDER_CHANGE_ME"

  lifecycle {
    ignore_changes = [secret_string]
  }
}
