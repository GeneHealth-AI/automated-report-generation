# ECS Fargate Configuration for Report Generation

# ECS Cluster
resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-cluster-${var.environment}"

  setting {
    name  = "containerInsights"
    value = var.enable_enhanced_monitoring ? "enabled" : "disabled"
  }

  tags = {
    Name        = "${var.project_name}-cluster-${var.environment}"
    Environment = var.environment
  }
}

# CloudWatch Log Group for ECS
resource "aws_cloudwatch_log_group" "ecs_tasks" {
  name              = "/ecs/${var.project_name}-${var.environment}"
  retention_in_days = var.log_retention_days

  tags = {
    Name        = "${var.project_name}-ecs-logs-${var.environment}"
    Environment = var.environment
  }
}

# ECS Task Execution Role
resource "aws_iam_role" "ecs_task_execution" {
  name_prefix = "${var.project_name}-ecs-exec-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Name = "${var.project_name}-ecs-execution-role-${var.environment}"
  }
}

# Attach AWS managed policy for ECS task execution
resource "aws_iam_role_policy_attachment" "ecs_task_execution" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Additional policy for task execution (Secrets Manager, ECR)
resource "aws_iam_role_policy" "ecs_task_execution_additional" {
  name_prefix = "${var.project_name}-ecs-exec-additional-"
  role        = aws_iam_role.ecs_task_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "kms:Decrypt"
        ]
        Resource = [
          aws_secretsmanager_secret.anthropic_api_key.arn,
          aws_secretsmanager_secret.gemini_api_key.arn,
          aws_secretsmanager_secret.db_password.arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage"
        ]
        Resource = "*"
      }
    ]
  })
}

# ECS Task Role (for the running container)
resource "aws_iam_role" "ecs_task" {
  name_prefix = "${var.project_name}-ecs-task-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Name = "${var.project_name}-ecs-task-role-${var.environment}"
  }
}

# ECS Task Role Policy
resource "aws_iam_role_policy" "ecs_task" {
  name_prefix = "${var.project_name}-ecs-task-policy-"
  role        = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.input.arn,
          "${aws_s3_bucket.input.arn}/*",
          aws_s3_bucket.output.arn,
          "${aws_s3_bucket.output.arn}/*",
          aws_s3_bucket.gwas_data.arn,
          "${aws_s3_bucket.gwas_data.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          aws_secretsmanager_secret.anthropic_api_key.arn,
          aws_secretsmanager_secret.gemini_api_key.arn,
          aws_secretsmanager_secret.db_password.arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.ecs_tasks.arn}:*"
      }
    ]
  })
}

# ECS Task Definition
resource "aws_ecs_task_definition" "report_generator" {
  family                   = "${var.project_name}-report-generator"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.fargate_cpu
  memory                   = var.fargate_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "report-generator"
      image     = "${aws_ecr_repository.report_generator.repository_url}:latest"
      essential = true

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs_tasks.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }

      environment = [
        {
          name  = "AWS_DEFAULT_REGION"
          value = var.aws_region
        },
        {
          name  = "ENVIRONMENT"
          value = var.environment
        },
        {
          name  = "OUTPUT_S3_BUCKET"
          value = aws_s3_bucket.output.id
        },
        {
          name  = "GWAS_DATA_BUCKET"
          value = aws_s3_bucket.gwas_data.id
        },
        {
          name  = "TEMPLATE_PATH"
          value = "s3://${aws_s3_bucket.input.id}/templates/template.json"
        }
      ]

      secrets = [
        {
          name      = "ANTHROPIC_API_KEY"
          valueFrom = aws_secretsmanager_secret.anthropic_api_key.arn
        },
        {
          name      = "GEMINI_API_KEY"
          valueFrom = aws_secretsmanager_secret.gemini_api_key.arn
        },
        {
          name      = "DB_HOST"
          valueFrom = "${aws_secretsmanager_secret.db_password.arn}:host::"
        },
        {
          name      = "DB_NAME"
          valueFrom = "${aws_secretsmanager_secret.db_password.arn}:dbname::"
        },
        {
          name      = "DB_USERNAME"
          valueFrom = "${aws_secretsmanager_secret.db_password.arn}:username::"
        },
        {
          name      = "DB_PASSWORD"
          valueFrom = "${aws_secretsmanager_secret.db_password.arn}:password::"
        }
      ]

      cpu    = var.fargate_cpu
      memory = var.fargate_memory
    }
  ])

  tags = {
    Name        = "${var.project_name}-task-definition-${var.environment}"
    Environment = var.environment
  }
}

# CloudWatch Alarms for ECS
resource "aws_cloudwatch_metric_alarm" "ecs_cpu_high" {
  alarm_name          = "${var.project_name}-ecs-cpu-high-${var.environment}"
  alarm_description   = "ECS task CPU utilization is too high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  period              = 300
  statistic           = "Average"
  threshold           = 80

  dimensions = {
    ClusterName = aws_ecs_cluster.main.name
    ServiceName = "${var.project_name}-service"
  }

  alarm_actions = []  # Add SNS topic ARN here for notifications
}

resource "aws_cloudwatch_metric_alarm" "ecs_memory_high" {
  alarm_name          = "${var.project_name}-ecs-memory-high-${var.environment}"
  alarm_description   = "ECS task memory utilization is too high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "MemoryUtilization"
  namespace           = "AWS/ECS"
  period              = 300
  statistic           = "Average"
  threshold           = 80

  dimensions = {
    ClusterName = aws_ecs_cluster.main.name
    ServiceName = "${var.project_name}-service"
  }

  alarm_actions = []  # Add SNS topic ARN here for notifications
}
