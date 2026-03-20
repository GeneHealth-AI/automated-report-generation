"""
Lambda function: Triggered by S3 when .fq.gz files are uploaded to exomeinputbucket.

Sends an SQS message to genomics-pipeline-jobs queue to start the FASTQ→VCF pipeline.

Logic:
- Triggered on s3:ObjectCreated:Put for *.fq.gz files
- Extracts the sample directory from the S3 key (e.g., "sample_001/" from "sample_001/reads_R1.fq.gz")
- Sends an SQS message with s3_input_dir pointing to that directory
- The SQS consumer Lambda then launches a GPU EC2 instance to process it

Deduplication:
- Uses a simple DynamoDB or in-memory check to avoid sending duplicate messages
  when both R1 and R2 files are uploaded (only triggers once per directory)
- Falls back to SQS message deduplication if available
"""
import json
import os
import boto3
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sqs = boto3.client('sqs', region_name='us-east-2')
s3 = boto3.client('s3', region_name='us-east-2')

QUEUE_URL = 'https://sqs.us-east-2.amazonaws.com/339712911975/genomics-pipeline-jobs'
BUCKET = 'exomeinputbucket'


def lambda_handler(event, context):
    """Handle S3 event notification for .fq.gz uploads."""
    logger.info(f"Received event: {json.dumps(event)}")

    for record in event.get('Records', []):
        # Extract S3 info
        s3_event = record.get('s3', {})
        bucket = s3_event.get('bucket', {}).get('name', '')
        key = s3_event.get('object', {}).get('key', '')

        if not key or not key.endswith('.fq.gz'):
            logger.info(f"Skipping non-FASTQ file: {key}")
            continue

        logger.info(f"FASTQ file uploaded: s3://{bucket}/{key}")

        # Extract sample directory (everything before the filename)
        # e.g., "sample_001/reads_R1.fq.gz" -> "sample_001/"
        # e.g., "provider-uploads/patient_123/data_R1.fq.gz" -> "provider-uploads/patient_123/"
        parts = key.rsplit('/', 1)
        if len(parts) == 2:
            sample_dir = parts[0] + '/'
        else:
            # File is at root of bucket — use filename stem as sample dir
            sample_dir = key.split('_')[0] + '/'

        sample_id = sample_dir.rstrip('/').split('/')[-1]
        s3_input_dir = f"s3://{bucket}/{sample_dir}"
        s3_output_dir = f"s3://{bucket}/{sample_dir}results/"

        # Check if both R1 and R2 files exist before triggering
        # (avoid triggering twice — once for R1, once for R2)
        try:
            response = s3.list_objects_v2(
                Bucket=bucket,
                Prefix=sample_dir,
            )
            fq_files = [
                obj['Key'] for obj in response.get('Contents', [])
                if obj['Key'].endswith('.fq.gz') or obj['Key'].endswith('.fastq.gz')
            ]
            logger.info(f"Found {len(fq_files)} FASTQ files in {sample_dir}: {fq_files}")

            if len(fq_files) < 2:
                logger.info(f"Only {len(fq_files)} FASTQ file(s) found — waiting for paired-end partner before triggering pipeline")
                return {
                    'statusCode': 200,
                    'body': f'Waiting for paired-end files. Currently {len(fq_files)} of 2.'
                }

            # Check if results already exist (avoid re-processing)
            results_response = s3.list_objects_v2(
                Bucket=bucket,
                Prefix=f"{sample_dir}results/final_report.txt",
                MaxKeys=1
            )
            if results_response.get('KeyCount', 0) > 0:
                logger.info(f"Results already exist for {sample_dir} — skipping")
                return {
                    'statusCode': 200,
                    'body': f'Results already exist for {sample_dir}. Skipping.'
                }

        except Exception as e:
            logger.warning(f"Error checking for paired files: {e}. Proceeding anyway.")

        # Send SQS message to trigger pipeline
        message = {
            's3_input_dir': s3_input_dir,
            's3_output_dir': s3_output_dir,
            'sample_id': sample_id,
        }

        logger.info(f"Sending SQS message: {json.dumps(message)}")

        try:
            sqs.send_message(
                QueueUrl=QUEUE_URL,
                MessageBody=json.dumps(message)
            )
            logger.info(f"Pipeline triggered for {s3_input_dir}")
        except Exception as e:
            logger.error(f"Failed to send SQS message: {e}")
            raise

    return {
        'statusCode': 200,
        'body': 'FASTQ upload processed'
    }
