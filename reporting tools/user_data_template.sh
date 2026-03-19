#!/bin/bash
# EC2 User Data Script Template
# Use this when launching an EC2 instance to automatically run the Parabricks pipeline.

exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1
echo "Starting Pipeline Job..."

# Configuration
REGION="us-east-1"
# REPLACE WITH YOUR IMAGE URI
IMAGE_URI="<YOUR_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/parabricks-pipeline:latest"
INPUT_R1="s3://your-bucket/path/to/R1.fq.gz"
INPUT_R2="s3://your-bucket/path/to/R2.fq.gz"
OUTPUT_S3="s3://your-bucket/output/folder"

# 1. Install Docker & Nvidia Runtime
# (Assumes Amazon Linux 2 / 2023 or Ubuntu with Nvidia drivers pre-installed like Deep Learning AMI)
# If using basic AMI, you need to install drivers first. Recommended: Use "Deep Learning AMI" or "NVIDIA GPU AMI".

echo "Checking Docker..."
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    yum install -y docker
    systemctl start docker
    systemctl enable docker
    usermod -aG docker ec2-user
fi

# 2. Login to ECR
# Instance needs IAM Role with: output/folder
# - AmazonEC2ContainerRegistryReadOnly
# - S3 Access (for inputs/outputs)

echo "Logging into ECR..."
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$(echo $IMAGE_URI | cut -d/ -f1)"

# 3. Run Pipeline
echo "Running Container..."

# Note: We use --gpus all. Ensure the instance has GPUs.
docker run --rm --gpus all \
    -e AWS_DEFAULT_REGION=$REGION \
    -e REF_S3_URI="s3://entprises/ref/" \
    -e ENTPRISE_S3_URI="s3://entprises/entprise/" \
    -e ENTPRISEX_S3_URI="s3://entprises/entpriseX/" \
    $IMAGE_URI \
    "$INPUT_R1" \
    "$INPUT_R2" \
    "$OUTPUT_S3"

echo "Job Complete. Shutting down..."
shutdown -h now
