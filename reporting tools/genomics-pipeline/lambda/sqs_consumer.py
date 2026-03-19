"""
Lambda function: SQS -> Launch EC2 GPU instance to run genomics pipeline.

SQS Message Format:
{
    "s3_input_dir": "s3://bucket/path/to/fastq/",
    "s3_output_dir": "s3://bucket/path/to/output/",  (optional)
    "sample_id": "patient_001",                        (optional)
    "instance_type": "g4dn.xlarge"                     (optional)
}

The Lambda launches a GPU EC2 instance that pulls the Docker image from ECR,
runs the pipeline, uploads results, and self-terminates.
"""
import json
import os
import base64
import boto3

ec2 = boto3.client('ec2')

# Configuration from environment variables
ECR_IMAGE_URI = os.environ['ECR_IMAGE_URI']
SUBNET_ID = os.environ['SUBNET_ID']
SECURITY_GROUP_ID = os.environ['SECURITY_GROUP_ID']
INSTANCE_PROFILE_ARN = os.environ['INSTANCE_PROFILE_ARN']
KEY_NAME = os.environ.get('KEY_NAME', '')
DEFAULT_INSTANCE_TYPE = os.environ.get('DEFAULT_INSTANCE_TYPE', 'g5.2xlarge')
# AMI with NVIDIA drivers + Docker (e.g., AWS Deep Learning AMI or NVIDIA GPU AMI)
AMI_ID = os.environ['AMI_ID']
AWS_REGION = os.environ.get('PIPELINE_AWS_REGION', os.environ.get('AWS_REGION', 'us-east-2'))

# S3 URIs for large reference data
REF_S3_URI = os.environ.get('REF_S3_URI', 's3://entprises/ref/')
STR_S3_URI = os.environ.get('STR_S3_URI', 's3://exomeinputbucket/str_entprise.tar.gz')


def generate_user_data(message):
    """Generate EC2 user data script that runs the pipeline container."""
    s3_input_dir = message['s3_input_dir']
    s3_output_dir = message.get('s3_output_dir', s3_input_dir.rstrip('/') + '/results/')
    sample_id = message.get('sample_id', 'sample')

    sqs_message_json = json.dumps(message).replace('"', '\\"')

    script = f"""#!/bin/bash
exec > >(tee /var/log/genomics-pipeline.log | logger -t genomics-pipeline) 2>&1
echo "=== Genomics Pipeline EC2 Bootstrap at $(date) ==="

# Wait for Docker daemon
for i in $(seq 1 30); do
    docker info &>/dev/null && break
    echo "Waiting for Docker... ($i)"
    sleep 5
done

# Login to ECR
REGION="{AWS_REGION}"
ECR_REGISTRY=$(echo "{ECR_IMAGE_URI}" | cut -d/ -f1)
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"

# Pull latest image
echo "Pulling {ECR_IMAGE_URI}..."
docker pull "{ECR_IMAGE_URI}"

# Run pipeline
echo "Starting pipeline container..."
mkdir -p /scratch
docker run --rm --gpus all \
    --shm-size=8g \
    -v /scratch:/scratch \
    -e TMPDIR=/scratch \
    -e AWS_DEFAULT_REGION="$REGION" \
    -e REF_S3_URI="{REF_S3_URI}" \
    -e STR_S3_URI="{STR_S3_URI}" \
    -e SQS_MESSAGE="{sqs_message_json}" \
    "{ECR_IMAGE_URI}"

EXIT_CODE=$?
echo "Pipeline exited with code: $EXIT_CODE"

# Upload bootstrap log to S3
aws s3 cp /var/log/genomics-pipeline.log "{s3_output_dir}ec2_bootstrap.log"

# Self-terminate
echo "Shutting down instance..."
shutdown -h now
"""
    return base64.b64encode(script.encode()).decode()


def lambda_handler(event, context):
    """Process SQS messages and launch EC2 instances."""
    results = []

    for record in event.get('Records', []):
        try:
            message = json.loads(record['body'])
            print(f"Processing message: {json.dumps(message)}")

            if 's3_input_dir' not in message:
                print(f"Skipping invalid message (no s3_input_dir): {message}")
                continue

            instance_type = message.get('instance_type', DEFAULT_INSTANCE_TYPE)
            sample_id = message.get('sample_id', 'unknown')

            launch_params = {
                'ImageId': AMI_ID,
                'InstanceType': instance_type,
                'MinCount': 1,
                'MaxCount': 1,
                'UserData': generate_user_data(message),
                'IamInstanceProfile': {'Arn': INSTANCE_PROFILE_ARN},
                'SubnetId': SUBNET_ID,
                'SecurityGroupIds': [SECURITY_GROUP_ID],
                'TagSpecifications': [{
                    'ResourceType': 'instance',
                    'Tags': [
                        {'Key': 'Name', 'Value': f'genomics-pipeline-{sample_id}'},
                        {'Key': 'Pipeline', 'Value': 'genomics-fastq-to-disease-score'},
                        {'Key': 'SampleId', 'Value': sample_id},
                        {'Key': 'AutoTerminate', 'Value': 'true'},
                    ]
                }],
                'InstanceInitiatedShutdownBehavior': 'terminate',
                'BlockDeviceMappings': [{
                    'DeviceName': '/dev/xvda',
                    'Ebs': {
                        'VolumeSize': 500,  # GB - enough for FASTQ + ref + str + intermediate
                        'VolumeType': 'gp3',
                        'DeleteOnTermination': True,
                    }
                }],
            }

            if KEY_NAME:
                launch_params['KeyName'] = KEY_NAME

            response = ec2.run_instances(**launch_params)
            instance_id = response['Instances'][0]['InstanceId']

            print(f"Launched {instance_id} ({instance_type}) for sample {sample_id}")
            results.append({
                'sample_id': sample_id,
                'instance_id': instance_id,
                'instance_type': instance_type,
                'status': 'launched'
            })

        except Exception as e:
            print(f"Error processing message: {e}")
            results.append({'error': str(e), 'record': record['body']})

    return {'results': results}
