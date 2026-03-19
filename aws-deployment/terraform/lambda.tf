# Lambda Function to Trigger ECS Fargate Tasks

# CloudWatch Log Group for Lambda
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.project_name}-fargate-trigger-${var.environment}"
  retention_in_days = var.log_retention_days

  tags = {
    Name        = "${var.project_name}-lambda-logs-${var.environment}"
    Environment = var.environment
  }
}

# Lambda Execution Role
resource "aws_iam_role" "lambda_execution" {
  name_prefix = "${var.project_name}-lambda-exec-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Name = "${var.project_name}-lambda-execution-role-${var.environment}"
  }
}

# Attach AWS managed policy for Lambda VPC execution
resource "aws_iam_role_policy_attachment" "lambda_vpc_execution" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# Lambda Execution Policy
resource "aws_iam_role_policy" "lambda_execution" {
  name_prefix = "${var.project_name}-lambda-policy-"
  role        = aws_iam_role.lambda_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.lambda.arn}:*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecs:RunTask",
          "ecs:DescribeTasks",
          "ecs:ListTasks"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "iam:PassRole"
        ]
        Resource = [
          aws_iam_role.ecs_task_execution.arn,
          aws_iam_role.ecs_task.arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.input.arn,
          "${aws_s3_bucket.input.arn}/*",
          aws_s3_bucket.output.arn,
          "${aws_s3_bucket.output.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          aws_secretsmanager_secret.db_password.arn
        ]
      }
    ]
  })
}

# Lambda Function (placeholder - actual code needs to be packaged)
resource "aws_lambda_function" "fargate_trigger" {
  function_name = "${var.project_name}-fargate-trigger-${var.environment}"
  role          = aws_iam_role.lambda_execution.arn
  handler       = "lambda_fargate_caller.lambda_handler"
  runtime       = "python3.9"
  timeout       = var.lambda_timeout
  memory_size   = var.lambda_memory_size

  # Placeholder for function code - will be updated by deployment script
  filename         = "${path.module}/../lambda/lambda_package.zip"
  source_code_hash = fileexists("${path.module}/../lambda/lambda_package.zip") ? filebase64sha256("${path.module}/../lambda/lambda_package.zip") : null

  vpc_config {
    subnet_ids         = aws_subnet.private[*].id
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      ECS_CLUSTER_NAME      = aws_ecs_cluster.main.name
      ECS_TASK_DEFINITION   = aws_ecs_task_definition.report_generator.family
      ECS_SUBNET_IDS        = join(",", aws_subnet.private[*].id)
      ECS_SECURITY_GROUP_ID = aws_security_group.ecs_tasks.id
      OUTPUT_S3_BUCKET      = aws_s3_bucket.output.id
      DB_SECRET_ARN         = aws_secretsmanager_secret.db_password.arn
      ENVIRONMENT           = var.environment
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda]

  tags = {
    Name        = "${var.project_name}-fargate-trigger-${var.environment}"
    Environment = var.environment
  }

  lifecycle {
    ignore_changes = [
      filename,
      source_code_hash
    ]
  }
}

# Lambda Permission for API Gateway (if using API Gateway)
resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.fargate_trigger.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.main.execution_arn}/*/*"
}

# Lambda Permission for S3 (optional - for S3 triggered processing)
resource "aws_lambda_permission" "s3" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.fargate_trigger.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.input.arn
}

# S3 Bucket Notification (optional - trigger Lambda on file upload)
resource "aws_s3_bucket_notification" "input_bucket" {
  bucket = aws_s3_bucket.input.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.fargate_trigger.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "vcf/"
    filter_suffix       = ".vcf"
  }

  depends_on = [aws_lambda_permission.s3]
}

# CloudWatch Alarms for Lambda
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "${var.project_name}-lambda-errors-${var.environment}"
  alarm_description   = "Lambda function errors are too high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 5

  dimensions = {
    FunctionName = aws_lambda_function.fargate_trigger.function_name
  }

  alarm_actions = []  # Add SNS topic ARN here for notifications
}

resource "aws_cloudwatch_metric_alarm" "lambda_duration" {
  alarm_name          = "${var.project_name}-lambda-duration-${var.environment}"
  alarm_description   = "Lambda function duration is too high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Average"
  threshold           = var.lambda_timeout * 1000 * 0.8  # 80% of timeout in milliseconds

  dimensions = {
    FunctionName = aws_lambda_function.fargate_trigger.function_name
  }

  alarm_actions = []  # Add SNS topic ARN here for notifications
}

resource "aws_cloudwatch_metric_alarm" "lambda_throttles" {
  alarm_name          = "${var.project_name}-lambda-throttles-${var.environment}"
  alarm_description   = "Lambda function is being throttled"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Throttles"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 1

  dimensions = {
    FunctionName = aws_lambda_function.fargate_trigger.function_name
  }

  alarm_actions = []  # Add SNS topic ARN here for notifications
}
