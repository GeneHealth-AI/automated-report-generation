#!/usr/bin/env python3
"""
Simplified AWS Lambda Function for ECR Container Orchestration

This Lambda function triggers ECR containers to generate reports instead of 
running the report generation directly in Lambda. This approach:
- Avoids Lambda size and timeout limitations
- Uses your existing ECR containers
- Provides better scalability and resource management
"""

import json
import os
import boto3
import logging
from datetime import datetime
import uuid
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize AWS clients
ecs = boto3.client('ecs')
s3 = boto3.client('s3')

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Simplified Lambda handler that triggers ECR containers for report generation.
    
    Args:
        event: Lambda event data
        context: Lambda context object
        
    Returns:
        Dict containing status and task information
    """
    request_id = context.aws_request_id if hasattr(context, 'aws_request_id') else str(uuid.uuid4())
    
    logger.info(f"[{request_id}] Lambda invocation started")
    
    try:
        # Determine event type and route accordingly
        if _is_s3_event(event):
            return handle_s3_trigger(event, request_id)
        elif _is_api_gateway_event(event):
            return handle_api_request(event, request_id)
        else:
            return handle_direct_invocation(event, request_id)
            
    except Exception as e:
        logger.error(f"[{request_id}] Lambda execution failed: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'error': str(e),
                'message': 'Container orchestration failed',
                'request_id': request_id
            })
        }

def handle_s3_trigger(event: Dict[str, Any], request_id: str) -> Dict[str, Any]:
    """Handle S3 event by triggering JSON report generation container."""
    logger.info(f"[{request_id}] Processing S3 trigger for JSON report generation")
    
    try:
        # Extract S3 information
        record = event['Records'][0]
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']
        
        logger.info(f"[{request_id}] Triggering container for s3://{bucket}/{key}")
        
        # Trigger JSON report generation container
        task_arn = run_json_container(bucket, key, request_id)
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'message': 'JSON report generation container started',
                'task_arn': task_arn,
                'source_file': f"s3://{bucket}/{key}",
                'request_id': request_id
            })
        }
        
    except Exception as e:
        logger.error(f"[{request_id}] Error handling S3 trigger: {str(e)}")
        raise

def handle_api_request(event: Dict[str, Any], request_id: str) -> Dict[str, Any]:
    """Handle API Gateway request for on-demand report generation."""
    logger.info(f"[{request_id}] Processing API request")
    
    try:
        # Parse request body
        if isinstance(event.get('body'), str):
            body = json.loads(event['body'])
        else:
            body = event.get('body', {})
        
        report_type = body.get('report_type', 'json')  # 'json' or 'pdf'
        
        if report_type == 'json':
            # Trigger JSON generation container
            task_arn = run_json_container_from_api(body, request_id)
            message = 'JSON report generation container started'
        elif report_type == 'pdf':
            # Trigger PDF generation container
            task_arn = run_pdf_container_from_api(body, request_id)
            message = 'PDF report generation container started'
        else:
            raise ValueError(f"Invalid report_type: {report_type}. Must be 'json' or 'pdf'")
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'message': message,
                'task_arn': task_arn,
                'report_type': report_type,
                'request_id': request_id,
                'status_check_url': f"/status/{task_arn.split('/')[-1]}"
            })
        }
        
    except Exception as e:
        logger.error(f"[{request_id}] Error handling API request: {str(e)}")
        return {
            'statusCode': 400,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': str(e),
                'message': 'Invalid API request',
                'request_id': request_id
            })
        }

def handle_direct_invocation(event: Dict[str, Any], request_id: str) -> Dict[str, Any]:
    """Handle direct Lambda invocation."""
    logger.info(f"[{request_id}] Processing direct invocation")
    
    try:
        report_type = event.get('report_type', 'json')
        
        if report_type == 'json':
            task_arn = run_json_container_from_api(event, request_id)
        elif report_type == 'pdf':
            task_arn = run_pdf_container_from_api(event, request_id)
        else:
            raise ValueError(f"Invalid report_type: {report_type}")
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'message': f'{report_type.upper()} container started successfully',
                'task_arn': task_arn,
                'request_id': request_id
            })
        }
        
    except Exception as e:
        logger.error(f"[{request_id}] Error in direct invocation: {str(e)}")
        raise

def run_json_container(bucket: str, key: str, request_id: str) -> str:
    """Run the JSON report generation container."""
    
    # Get configuration from environment variables
    cluster_name = os.environ.get('ECS_CLUSTER', 'report-generation-cluster')
    task_definition = os.environ.get('JSON_TASK_DEFINITION', 'report-generator-json')
    subnet_ids = os.environ.get('SUBNET_IDS', '').split(',')
    security_group_ids = os.environ.get('SECURITY_GROUP_IDS', '').split(',')
    
    # Prepare environment variables for the container
    environment_overrides = [
        {'name': 'REPORT_TEMPLATE', 'value': f's3://{bucket}/{key}'},
        {'name': 'PURE_VCF', 'value': f's3://{bucket}/{key.replace(".json", ".vcf")}'},
        {'name': 'ANNOTATED_PATH', 'value': f's3://{bucket}/{key.replace(".json", "_annotated.vcf")}'},
        {'name': 'OUTPUT_PREFIX', 'value': f'report-{request_id}-'},
        {'name': 'ANTHROPIC_API_KEY', 'value': os.environ.get('ANTHROPIC_API_KEY', '')},
        {'name': 'AWS_REGION', 'value': os.environ.get('AWS_REGION', 'us-east-1')}
    ]
    
    # Run the ECS task
    response = ecs.run_task(
        cluster=cluster_name,
        taskDefinition=task_definition,
        launchType='FARGATE',
        networkConfiguration={
            'awsvpcConfiguration': {
                'subnets': subnet_ids,
                'securityGroups': security_group_ids,
                'assignPublicIp': 'ENABLED'
            }
        },
        overrides={
            'containerOverrides': [
                {
                    'name': 'report-generator-json',
                    'environment': environment_overrides
                }
            ]
        },
        tags=[
            {'key': 'RequestId', 'value': request_id},
            {'key': 'TriggerType', 'value': 'S3Event'},
            {'key': 'SourceBucket', 'value': bucket},
            {'key': 'SourceKey', 'value': key}
        ]
    )
    
    task_arn = response['tasks'][0]['taskArn']
    logger.info(f"[{request_id}] Started JSON container task: {task_arn}")
    
    return task_arn

def run_json_container_from_api(data: Dict[str, Any], request_id: str) -> str:
    """Run JSON container from API request data."""
    
    cluster_name = os.environ.get('ECS_CLUSTER', 'report-generation-cluster')
    task_definition = os.environ.get('JSON_TASK_DEFINITION', 'report-generator-json')
    subnet_ids = os.environ.get('SUBNET_IDS', '').split(',')
    security_group_ids = os.environ.get('SECURITY_GROUP_IDS', '').split(',')
    
    # Extract required parameters from API data
    template_s3 = data.get('template_s3', '')
    vcf_s3 = data.get('vcf_s3', '')
    annotated_s3 = data.get('annotated_s3', '')
    
    if not all([template_s3, vcf_s3, annotated_s3]):
        raise ValueError("Missing required S3 paths: template_s3, vcf_s3, annotated_s3")
    
    environment_overrides = [
        {'name': 'REPORT_TEMPLATE', 'value': template_s3},
        {'name': 'PURE_VCF', 'value': vcf_s3},
        {'name': 'ANNOTATED_PATH', 'value': annotated_s3},
        {'name': 'OUTPUT_PREFIX', 'value': f'api-report-{request_id}-'},
        {'name': 'ANTHROPIC_API_KEY', 'value': os.environ.get('ANTHROPIC_API_KEY', '')},
        {'name': 'AWS_REGION', 'value': os.environ.get('AWS_REGION', 'us-east-1')}
    ]
    
    response = ecs.run_task(
        cluster=cluster_name,
        taskDefinition=task_definition,
        launchType='FARGATE',
        networkConfiguration={
            'awsvpcConfiguration': {
                'subnets': subnet_ids,
                'securityGroups': security_group_ids,
                'assignPublicIp': 'ENABLED'
            }
        },
        overrides={
            'containerOverrides': [
                {
                    'name': 'report-generator-json',
                    'environment': environment_overrides
                }
            ]
        },
        tags=[
            {'key': 'RequestId', 'value': request_id},
            {'key': 'TriggerType', 'value': 'APIRequest'}
        ]
    )
    
    task_arn = response['tasks'][0]['taskArn']
    logger.info(f"[{request_id}] Started JSON container task from API: {task_arn}")
    
    return task_arn

def run_pdf_container_from_api(data: Dict[str, Any], request_id: str) -> str:
    """Run PDF container from API request data."""
    
    cluster_name = os.environ.get('ECS_CLUSTER', 'report-generation-cluster')
    task_definition = os.environ.get('PDF_TASK_DEFINITION', 'report-generator-pdf')
    subnet_ids = os.environ.get('SUBNET_IDS', '').split(',')
    security_group_ids = os.environ.get('SECURITY_GROUP_IDS', '').split(',')
    
    # Extract required parameters
    input_json_s3 = data.get('input_json_s3', '')
    
    if not input_json_s3:
        raise ValueError("Missing required parameter: input_json_s3")
    
    environment_overrides = [
        {'name': 'INPUT_JSON', 'value': input_json_s3},
        {'name': 'OUTPUT_PREFIX', 'value': f'pdf-report-{request_id}-'},
        {'name': 'OUTPUT_BUCKET', 'value': os.environ.get('OUTPUT_BUCKET', 'ghcompletedreports')},
        {'name': 'AWS_REGION', 'value': os.environ.get('AWS_REGION', 'us-east-1')}
    ]
    
    response = ecs.run_task(
        cluster=cluster_name,
        taskDefinition=task_definition,
        launchType='FARGATE',
        networkConfiguration={
            'awsvpcConfiguration': {
                'subnets': subnet_ids,
                'securityGroups': security_group_ids,
                'assignPublicIp': 'ENABLED'
            }
        },
        overrides={
            'containerOverrides': [
                {
                    'name': 'report-generator-pdf',
                    'environment': environment_overrides
                }
            ]
        },
        tags=[
            {'key': 'RequestId', 'value': request_id},
            {'key': 'TriggerType', 'value': 'APIRequest'}
        ]
    )
    
    task_arn = response['tasks'][0]['taskArn']
    logger.info(f"[{request_id}] Started PDF container task from API: {task_arn}")
    
    return task_arn

def _is_s3_event(event: Dict[str, Any]) -> bool:
    """Check if event is from S3."""
    return ('Records' in event and 
            len(event['Records']) > 0 and 
            event['Records'][0].get('eventSource') == 'aws:s3')

def _is_api_gateway_event(event: Dict[str, Any]) -> bool:
    """Check if event is from API Gateway."""
    return 'body' in event and ('httpMethod' in event or 'requestContext' in event)

# For local testing
if __name__ == "__main__":
    # Test event for JSON generation
    test_event = {
        "report_type": "json",
        "template_s3": "s3://your-bucket/template.json",
        "vcf_s3": "s3://your-bucket/sample.vcf",
        "annotated_s3": "s3://your-bucket/annotated.vcf"
    }
    
    class MockContext:
        aws_request_id = "test-request-123"
    
    result = lambda_handler(test_event, MockContext())
    print(json.dumps(result, indent=2))