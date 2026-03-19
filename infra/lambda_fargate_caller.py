#!/usr/bin/env python3
"""
Lambda function that calls ECS Fargate task for report generation.
This is a dummy implementation showing how to invoke the Fargate container.
"""

import json
import boto3
import logging
from datetime import datetime

import os

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ECS Configuration from environment variables (set by Terraform)
ECS_CLUSTER_NAME = os.environ.get('ECS_CLUSTER_NAME', "report-generation-cluster")
ECS_TASK_DEFINITION = os.environ.get('ECS_TASK_DEFINITION', "report-generator-task")
ECS_SUBNET_IDS = os.environ.get('ECS_SUBNET_IDS', "").split(",")
ECS_SECURITY_GROUP_IDS = [os.environ.get('ECS_SECURITY_GROUP_ID', "")]

def lambda_handler(event, context):
    """
    Lambda handler that triggers Fargate task for report generation.
    
    Expected event structure:
    {
        "annotated_vcf_path": "s3://bucket/path/to/annotated.vcf",
        "vcf_path": "s3://bucket/path/to/input.vcf", 
        "template_path": "s3://bucket/path/to/template.json",
        "name": "Patient Name",
        "id": "patient_id_123",
        "provider": "Provider Name",
        "output_s3_bucket": "output-bucket-name"  # Optional
    }
    """
    
    try:
        logger.info(f"Received event: {json.dumps(event)}")
        
        # Extract parameters from event
        annotated_vcf = event.get('annotated_vcf_path')
        vcf_path = event.get('vcf_path')
        template_path = event.get('template_path')
        name = event.get('name')
        patient_id = event.get('id')
        provider = event.get('provider')
        output_bucket = event.get('output_s3_bucket', os.environ.get('OUTPUT_S3_BUCKET', 'ghcompletedreports'))
        
        # Validate required parameters
        required_params = {
            'annotated_vcf_path': annotated_vcf,
            'vcf_path': vcf_path,
            'template_path': template_path,
            'name': name,
            'id': patient_id,
            'provider': provider
        }
        
        missing_params = [k for k, v in required_params.items() if not v]
        if missing_params:
            raise ValueError(f"Missing required parameters: {', '.join(missing_params)}")
        
        # Prepare environment variables for Fargate task
        # Use exact names expected by fargate_entrypoint.py
        fargate_env_vars = {
            'ANNOTATED_VCF_PATH': annotated_vcf,
            'VCF_PATH': vcf_path,
            'TEMPLATE_PATH': template_path,
            'NAME': name,
            'ID': patient_id,
            'PROVIDER': provider,
            'OUTPUT_S3_BUCKET': output_bucket
        }
        
        # Create ECS client
        ecs_client = boto3.client('ecs')
        
        # Prepare task definition overrides
        container_overrides = [{
            'name': 'report-generator',  # Container name from task definition
            'environment': [
                {'name': key, 'value': str(value)} 
                for key, value in fargate_env_vars.items()
            ]
        }]
        
        # Launch Fargate task
        logger.info(f"Launching Fargate task for patient {name} (ID: {patient_id})")
        
        # Ensure we have subnets and security groups
        if not ECS_SUBNET_IDS or not ECS_SUBNET_IDS[0]:
            raise ValueError("ECS_SUBNET_IDS environment variable is not set")
        if not ECS_SECURITY_GROUP_IDS or not ECS_SECURITY_GROUP_IDS[0]:
            raise ValueError("ECS_SECURITY_GROUP_ID environment variable is not set")

        response = ecs_client.run_task(
            cluster=ECS_CLUSTER_NAME,
            taskDefinition=ECS_TASK_DEFINITION,
            launchType='FARGATE',
            networkConfiguration={
                'awsvpcConfiguration': {
                    'subnets': ECS_SUBNET_IDS,
                    'securityGroups': ECS_SECURITY_GROUP_IDS,
                    'assignPublicIp': 'ENABLED'  # Set to DISABLED if using NAT Gateway in private subnets
                }
            },
            overrides={
                'containerOverrides': container_overrides
            },
            tags=[
                {'key': 'PatientId', 'value': str(patient_id)},
                {'key': 'LaunchedBy', 'value': 'Lambda'},
                {'key': 'Timestamp', 'value': datetime.utcnow().isoformat()}
            ]
        )
        
        task_arn = response['tasks'][0]['taskArn']
        logger.info(f"Successfully launched Fargate task: {task_arn}")
        
        return {
            'statusCode': 200,
            'body': {
                'message': 'Report generation task launched successfully',
                'task_arn': task_arn,
                'patient_id': patient_id,
                'patient_name': name,
                'provider': provider,
                'expected_output_bucket': output_bucket
            }
        }
        
    except Exception as e:
        logger.error(f"Error launching Fargate task: {str(e)}")
        
        return {
            'statusCode': 500,
            'body': {
                'error': str(e),
                'message': 'Failed to launch report generation task'
            }
        }


def create_dummy_event():
    """
    Create a dummy event for testing the Lambda function locally.
    """
    return {
        "annotated_vcf_path": "s3://input-bucket/samples/patient123_annotated.vcf",
        "vcf_path": "s3://input-bucket/samples/patient123.vcf",
        "template_path": "s3://templates-bucket/adhd_template.json",
        "name": "John Doe",
        "id": "patient_123",
        "provider": "Dr. Smith Medical Center",
        "output_s3_bucket": "ghcompletedreports"
    }


if __name__ == "__main__":
    # Test the function locally with dummy data
    dummy_event = create_dummy_event()
    dummy_context = {}
    
    print("Testing Lambda function with dummy event:")
    print(json.dumps(dummy_event, indent=2))
    
    result = lambda_handler(dummy_event, dummy_context)
    print("\nResult:")
    print(json.dumps(result, indent=2))