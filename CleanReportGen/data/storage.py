import boto3
import logging
import os
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Use environment variable for AWS region or fallback to default
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

def download_from_s3(s3_uri: str, local_path: str):
    """Download a file from S3 to local disk."""
    try:
        parsed = urlparse(s3_uri)
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        s3 = boto3.client("s3", region_name=AWS_REGION)
        s3.download_file(bucket, key, local_path)
        logger.info(f"Downloaded {s3_uri} -> {local_path}")
    except Exception as e:
        logger.error(f"Failed to download from S3: {e}")
        raise

def upload_to_s3(local_path: str, bucket: str, key: str):
    """Upload a local file to S3."""
    try:
        s3 = boto3.client("s3", region_name=AWS_REGION)
        s3.upload_file(local_path, bucket, key)
        logger.info(f"Uploaded {local_path} -> s3://{bucket}/{key}")
    except Exception as e:
        logger.error(f"Failed to upload to S3: {e}")
        raise

def get_instance_id() -> str:
    """Grab this EC2’s instance ID via IMDSv2 (placeholder/safe check)."""
    import requests
    try:
        token = requests.put(
            "http://169.254.169.254/latest/api/token",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"},
            timeout=2
        ).text
        return requests.get(
            "http://169.254.169.254/latest/meta-data/instance-id",
            headers={"X-aws-ec2-metadata-token": token},
            timeout=2
        ).text
    except Exception:
        return "local-instance"
