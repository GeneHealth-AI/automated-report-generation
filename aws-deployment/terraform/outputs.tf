# Terraform Outputs for Genetic Report Generation System

# VPC Outputs
output "vpc_id" {
  description = "ID of the VPC"
  value       = aws_vpc.main.id
}

output "private_subnet_ids" {
  description = "IDs of private subnets"
  value       = aws_subnet.private[*].id
}

output "public_subnet_ids" {
  description = "IDs of public subnets"
  value       = aws_subnet.public[*].id
}

# RDS Outputs
output "rds_endpoint" {
  description = "RDS instance endpoint"
  value       = aws_db_instance.main.endpoint
}

output "rds_database_name" {
  description = "RDS database name"
  value       = aws_db_instance.main.db_name
}

output "rds_secret_arn" {
  description = "ARN of the RDS credentials secret"
  value       = aws_secretsmanager_secret.db_password.arn
  sensitive   = true
}

# S3 Outputs
output "input_bucket_name" {
  description = "Name of the input S3 bucket"
  value       = aws_s3_bucket.input.id
}

output "output_bucket_name" {
  description = "Name of the output S3 bucket"
  value       = aws_s3_bucket.output.id
}

output "gwas_data_bucket_name" {
  description = "Name of the GWAS data S3 bucket"
  value       = aws_s3_bucket.gwas_data.id
}

# ECR Outputs
output "ecr_repository_url" {
  description = "URL of the ECR repository"
  value       = aws_ecr_repository.report_generator.repository_url
}

# ECS Outputs
output "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  value       = aws_ecs_cluster.main.name
}

output "ecs_task_definition_arn" {
  description = "ARN of the ECS task definition"
  value       = aws_ecs_task_definition.report_generator.arn
}

output "ecs_security_group_id" {
  description = "ID of the ECS security group"
  value       = aws_security_group.ecs_tasks.id
}

# Lambda Outputs
output "lambda_function_name" {
  description = "Name of the Lambda function"
  value       = aws_lambda_function.fargate_trigger.function_name
}

output "lambda_function_arn" {
  description = "ARN of the Lambda function"
  value       = aws_lambda_function.fargate_trigger.arn
}

# API Gateway Outputs
output "api_gateway_url" {
  description = "URL of the API Gateway endpoint"
  value       = "${aws_api_gateway_stage.main.invoke_url}/generate"
}

output "api_gateway_id" {
  description = "ID of the API Gateway"
  value       = aws_api_gateway_rest_api.main.id
}

output "api_key_id" {
  description = "ID of the API key"
  value       = aws_api_gateway_api_key.main.id
  sensitive   = true
}

# Secrets Manager Outputs
output "anthropic_secret_arn" {
  description = "ARN of the Anthropic API key secret"
  value       = aws_secretsmanager_secret.anthropic_api_key.arn
  sensitive   = true
}

output "gemini_secret_arn" {
  description = "ARN of the Gemini API key secret"
  value       = aws_secretsmanager_secret.gemini_api_key.arn
  sensitive   = true
}

# Deployment Information
output "deployment_instructions" {
  description = "Instructions for completing the deployment"
  value       = <<-EOT
    ========================================
    Genetic Report Generation System Deployed
    ========================================

    Next Steps:

    1. Update API Keys in Secrets Manager:
       aws secretsmanager put-secret-value --secret-id ${aws_secretsmanager_secret.anthropic_api_key.arn} --secret-string "YOUR_ANTHROPIC_KEY"
       aws secretsmanager put-secret-value --secret-id ${aws_secretsmanager_secret.gemini_api_key.arn} --secret-string "YOUR_GEMINI_KEY"

    2. Build and Push Docker Image:
       aws ecr get-login-password --region ${var.aws_region} | docker login --username AWS --password-stdin ${aws_ecr_repository.report_generator.repository_url}
       cd ../docker
       docker build -t ${aws_ecr_repository.report_generator.repository_url}:latest .
       docker push ${aws_ecr_repository.report_generator.repository_url}:latest

    3. Upload GWAS Data to S3:
       aws s3 cp gwas_catalog_v1.0.2-associations_e114_r2025-07-10.tsv s3://${aws_s3_bucket.gwas_data.id}/

    4. Run Database Migrations:
       See database/migrations/ folder

    5. Test the API:
       curl -X POST ${aws_api_gateway_stage.main.invoke_url}/generate \
         -H "x-api-key: YOUR_API_KEY" \
         -d @test-payload.json

    API Endpoint: ${aws_api_gateway_stage.main.invoke_url}/generate
    Input Bucket: s3://${aws_s3_bucket.input.id}
    Output Bucket: s3://${aws_s3_bucket.output.id}

    ========================================
  EOT
}
