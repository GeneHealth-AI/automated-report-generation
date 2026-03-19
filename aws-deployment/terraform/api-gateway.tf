# API Gateway for Report Generation

# REST API
resource "aws_api_gateway_rest_api" "main" {
  name        = "${var.project_name}-api-${var.environment}"
  description = "API for Genetic Report Generation System"

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  tags = {
    Name        = "${var.project_name}-api-${var.environment}"
    Environment = var.environment
  }
}

# API Gateway Resource - /generate
resource "aws_api_gateway_resource" "generate" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_rest_api.main.root_resource_id
  path_part   = "generate"
}

# API Gateway Method - POST /generate
resource "aws_api_gateway_method" "generate_post" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.generate.id
  http_method   = "POST"
  authorization = "AWS_IAM"  # Use IAM for authorization

  request_validator_id = aws_api_gateway_request_validator.main.id
}

# API Gateway Integration with Lambda
resource "aws_api_gateway_integration" "generate_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.generate.id
  http_method             = aws_api_gateway_method.generate_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.fargate_trigger.invoke_arn
}

# API Gateway Method Response
resource "aws_api_gateway_method_response" "generate_200" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.generate.id
  http_method = aws_api_gateway_method.generate_post.http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Origin" = true
  }

  response_models = {
    "application/json" = "Empty"
  }
}

# API Gateway Request Validator
resource "aws_api_gateway_request_validator" "main" {
  name                        = "${var.project_name}-validator"
  rest_api_id                 = aws_api_gateway_rest_api.main.id
  validate_request_body       = true
  validate_request_parameters = true
}

# API Gateway Deployment
resource "aws_api_gateway_deployment" "main" {
  rest_api_id = aws_api_gateway_rest_api.main.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.generate.id,
      aws_api_gateway_method.generate_post.id,
      aws_api_gateway_integration.generate_lambda.id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [
    aws_api_gateway_integration.generate_lambda
  ]
}

# API Gateway Stage
resource "aws_api_gateway_stage" "main" {
  deployment_id = aws_api_gateway_deployment.main.id
  rest_api_id   = aws_api_gateway_rest_api.main.id
  stage_name    = var.environment

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      caller         = "$context.identity.caller"
      user           = "$context.identity.user"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      resourcePath   = "$context.resourcePath"
      status         = "$context.status"
      protocol       = "$context.protocol"
      responseLength = "$context.responseLength"
    })
  }

  xray_tracing_enabled = var.enable_enhanced_monitoring

  tags = {
    Name        = "${var.project_name}-api-stage-${var.environment}"
    Environment = var.environment
  }
}

# CloudWatch Log Group for API Gateway
resource "aws_cloudwatch_log_group" "api_gateway" {
  name              = "/aws/apigateway/${var.project_name}-${var.environment}"
  retention_in_days = var.log_retention_days

  tags = {
    Name        = "${var.project_name}-api-gateway-logs-${var.environment}"
    Environment = var.environment
  }
}

# API Gateway Account (for CloudWatch Logs)
resource "aws_api_gateway_account" "main" {
  cloudwatch_role_arn = aws_iam_role.api_gateway_cloudwatch.arn
}

# IAM Role for API Gateway CloudWatch Logs
resource "aws_iam_role" "api_gateway_cloudwatch" {
  name_prefix = "${var.project_name}-apigw-cw-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "apigateway.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

# IAM Policy Attachment for API Gateway CloudWatch
resource "aws_iam_role_policy_attachment" "api_gateway_cloudwatch" {
  role       = aws_iam_role.api_gateway_cloudwatch.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonAPIGatewayPushToCloudWatchLogs"
}

# Usage Plan
resource "aws_api_gateway_usage_plan" "main" {
  name        = "${var.project_name}-usage-plan-${var.environment}"
  description = "Usage plan for ${var.project_name}"

  api_stages {
    api_id = aws_api_gateway_rest_api.main.id
    stage  = aws_api_gateway_stage.main.stage_name
  }

  throttle_settings {
    rate_limit  = 100
    burst_limit = 200
  }

  quota_settings {
    limit  = 10000
    period = "DAY"
  }

  tags = {
    Name        = "${var.project_name}-usage-plan-${var.environment}"
    Environment = var.environment
  }
}

# API Key
resource "aws_api_gateway_api_key" "main" {
  name        = "${var.project_name}-api-key-${var.environment}"
  description = "API key for ${var.project_name}"
  enabled     = true

  tags = {
    Name        = "${var.project_name}-api-key-${var.environment}"
    Environment = var.environment
  }
}

# Usage Plan Key
resource "aws_api_gateway_usage_plan_key" "main" {
  key_id        = aws_api_gateway_api_key.main.id
  key_type      = "API_KEY"
  usage_plan_id = aws_api_gateway_usage_plan.main.id
}
