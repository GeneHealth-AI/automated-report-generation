"""
AWS Lambda: API Gateway → ECS Fargate Report Generation

Triggered by POST to /GenerateAutoReport. Launches a Fargate task to generate
a precision medicine HTML report from VCF/disease score data.

Required fields:
  - VCF_PATH: S3 path to the VCF or disease scores file
  - TEMPLATE: Either an inline JSON object or an S3 path string (s3://bucket/key.json)

Optional fields (have defaults):
  - ANNOTATED_VCF_PATH: S3 path to annotated VCF (defaults to VCF_PATH)
  - NAME: Patient name (default: "Patient")
  - ID: Patient ID (default: auto-generated)
  - PROVIDER: Provider name (default: "GeneHealth")
  - S3_OUTPUT_BUCKET: Output bucket (default: "completed-auto-reports")
  - OUTPUT_FILENAME: Output filename (default: auto-generated from ID + name)
  - PATIENT_GENDER: Male/Female/Unknown (default: "Unknown")
"""

import json
import os
import time
import boto3
import logging
import traceback
from typing import Dict, Any
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

ecs_client = boto3.client('ecs')
secrets_manager_client = boto3.client('secretsmanager')
s3_client = boto3.client('s3')


def _get_secret(secret_name: str) -> str:
    """Retrieve a secret from AWS Secrets Manager."""
    try:
        response = secrets_manager_client.get_secret_value(SecretId=secret_name)
        secret_string = response['SecretString']
        try:
            secret_json = json.loads(secret_string)
            if isinstance(secret_json, dict):
                return next(iter(secret_json.values()))
            return secret_string
        except json.JSONDecodeError:
            return secret_string
    except Exception as e:
        logger.error(f"Failed to retrieve secret '{secret_name}': {e}")
        raise


def _load_s3_template(s3_uri: str) -> str:
    """Download a template JSON file from S3 and return its content as a string."""
    parsed = urlparse(s3_uri)
    bucket = parsed.netloc
    key = parsed.path.lstrip('/')
    response = s3_client.get_object(Bucket=bucket, Key=key)
    return response['Body'].read().decode('utf-8')


def _resolve_template(template_input) -> str:
    """
    Resolve TEMPLATE field to a JSON string.

    Accepts:
      - An S3 path string (e.g., "s3://gh-templates/cancer_template.json") → downloads it
      - An inline JSON object (dict) → serializes it
      - A JSON string → passes through
    """
    if isinstance(template_input, str):
        stripped = template_input.strip()
        if stripped.startswith('s3://'):
            # S3 path — download the template
            logger.info(f"Downloading template from S3: {stripped}")
            content = _load_s3_template(stripped)
            return content
        else:
            # Assume it's already a JSON string
            return stripped
    elif isinstance(template_input, dict):
        # Inline JSON object
        return json.dumps(template_input)
    else:
        raise ValueError(f"TEMPLATE must be a string (S3 path) or JSON object, got {type(template_input)}")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main handler: validates input, resolves defaults, launches Fargate task."""
    request_id = getattr(context, 'aws_request_id', 'local-test')
    logger.info(f"[{request_id}] Received request")

    try:
        # --- API Key Auth ---
        expected_key = os.environ.get('API_KEY')
        headers = {k.lower(): v for k, v in event.get('headers', {}).items()}
        if expected_key and headers.get('x-api-key') != expected_key:
            return _response(403, {'message': 'Forbidden'})

        # --- Parse body ---
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return _response(400, {'error': 'Invalid JSON in request body'})

        # --- Required fields ---
        vcf_path = body.get('VCF_PATH')
        template_input = body.get('TEMPLATE')

        if not vcf_path:
            return _response(400, {'error': 'Missing required field: VCF_PATH'})
        if not template_input:
            return _response(400, {'error': 'Missing required field: TEMPLATE (S3 path or inline JSON object)'})

        # --- Resolve template ---
        try:
            template_json = _resolve_template(template_input)
        except Exception as e:
            return _response(400, {'error': f'Failed to resolve TEMPLATE: {e}'})

        # --- Optional fields with defaults ---
        annotated_vcf = body.get('ANNOTATED_VCF_PATH', vcf_path)
        name = body.get('NAME', 'Patient')
        patient_id = str(body.get('ID', f'AUTO-{int(time.time())}'))
        provider = body.get('PROVIDER', 'GeneHealth')
        output_bucket = body.get('S3_OUTPUT_BUCKET', 'completed-auto-reports')
        output_filename = body.get('OUTPUT_FILENAME', '')
        patient_gender = body.get('PATIENT_GENDER', 'Unknown')

        logger.info(f"[{request_id}] Generating report for {name} (ID: {patient_id}), VCF: {vcf_path}")

        # --- Get API keys from Secrets Manager ---
        gemini_key = _get_secret('SamsGeminiAPIKey')
        anthropic_key = _get_secret('keyforanthropicGH')

        # --- Build Fargate environment ---
        fargate_env = {
            'ANNOTATED_VCF_PATH': annotated_vcf,
            'VCF_PATH': vcf_path,
            'TEMPLATE': template_json,
            'NAME': name,
            'ID': patient_id,
            'PROVIDER': provider,
            'OUTPUT_S3_BUCKET': output_bucket,
            'OUTPUT_FILENAME': output_filename,
            'PATIENT_GENDER': patient_gender,
            'GEMINI_API_KEY': gemini_key,
            'ANTHROPIC_API_KEY': anthropic_key,
            'REQUEST_ID': request_id,
        }

        # --- Launch Fargate task ---
        task_arn = _launch_fargate(fargate_env, request_id)

        return _response(200, {
            'message': 'Report generation started',
            'taskArn': task_arn,
            'patient_id': patient_id,
            'output_bucket': output_bucket,
        })

    except Exception as e:
        logger.error(f"[{request_id}] Error: {e}\n{traceback.format_exc()}")
        return _response(500, {'error': str(e)})


def _launch_fargate(env_overrides: Dict[str, str], request_id: str) -> str:
    """Launch an ECS Fargate task with the given environment overrides."""
    cluster = os.environ['ECS_CLUSTER_NAME']
    task_def = os.environ['ECS_TASK_DEFINITION_ARN']
    container = os.environ['ECS_CONTAINER_NAME']
    subnets = [s.strip() for s in os.environ['ECS_SUBNET_IDS'].split(',')]
    sgs = [s.strip() for s in os.environ['ECS_SECURITY_GROUP_IDS'].split(',')]

    container_env = [{'name': k, 'value': str(v)} for k, v in env_overrides.items()]

    response = ecs_client.run_task(
        cluster=cluster,
        launchType='FARGATE',
        taskDefinition=task_def,
        count=1,
        networkConfiguration={
            'awsvpcConfiguration': {
                'subnets': subnets,
                'securityGroups': sgs,
                'assignPublicIp': 'ENABLED'
            }
        },
        overrides={
            'containerOverrides': [{
                'name': container,
                'environment': container_env
            }]
        }
    )

    task_arn = response['tasks'][0]['taskArn']
    logger.info(f"[{request_id}] Fargate task launched: {task_arn}")
    return task_arn


def _response(status: int, body: dict) -> dict:
    return {
        'statusCode': status,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps(body)
    }
