#!/bin/bash
set -euo pipefail

# Build and push genomics pipeline Docker image to AWS ECR.
# Usage: ./build_and_push.sh [--tag TAG] [--region REGION]

AWS_REGION="${AWS_REGION:-us-east-2}"
REPO_NAME="${REPO_NAME:-genomics-pipeline}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

# Parse args
while [[ $# -gt 0 ]]; do
    case $1 in
        --tag) IMAGE_TAG="$2"; shift 2 ;;
        --region) AWS_REGION="$2"; shift 2 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPO_NAME}"

echo "=== Building Genomics Pipeline Image ==="
echo "Repo:   $REPO_NAME"
echo "Tag:    $IMAGE_TAG"
echo "Region: $AWS_REGION"
echo "ECR:    $ECR_URI"

# Prepare build context: copy entprise/entpriseX into build dir
echo "Preparing build context..."
ENTPRISE_SRC="${ENTPRISE_SRC:-/home/ec2-user/entprise}"
ENTPRISEX_SRC="${ENTPRISEX_SRC:-/home/ec2-user/entpriseX}"

if [ -d "$ENTPRISE_SRC" ]; then
    echo "Copying entprise from $ENTPRISE_SRC..."
    # Copy only essential files (skip test dirs, temp files, large tarballs)
    rsync -a --exclude='str_entprise.tar.gz' --exclude='test/' --exclude='__tmp*' \
        --exclude='_tmp*' --exclude='_x10*' --exclude='April/' \
        --exclude='scoring_input.lst' --exclude='rsid.lst' \
        "$ENTPRISE_SRC/" "$SCRIPT_DIR/entprise/"
else
    echo "WARNING: $ENTPRISE_SRC not found. Downloading from S3 at build time..."
    mkdir -p "$SCRIPT_DIR/entprise"
    aws s3 sync "${ENTPRISE_S3_URI:-s3://entprises/entprise/}" "$SCRIPT_DIR/entprise/"
fi

if [ -d "$ENTPRISEX_SRC" ]; then
    echo "Copying entpriseX from $ENTPRISEX_SRC..."
    rsync -a --exclude='test/' --exclude='__tmp*' --exclude='_tmp*' --exclude='_x10*' \
        --exclude='rsid.lst' \
        "$ENTPRISEX_SRC/" "$SCRIPT_DIR/entpriseX/"
else
    echo "WARNING: $ENTPRISEX_SRC not found. Downloading from S3 at build time..."
    mkdir -p "$SCRIPT_DIR/entpriseX"
    aws s3 sync "${ENTPRISEX_S3_URI:-s3://entprises/entpriseX/}" "$SCRIPT_DIR/entpriseX/"
fi

# Build image
echo "Building Docker image..."
docker build -t "${REPO_NAME}:${IMAGE_TAG}" -f "$SCRIPT_DIR/Dockerfile" "$SCRIPT_DIR"

# Login to ECR
echo "Logging into ECR..."
aws ecr get-login-password --region "$AWS_REGION" | \
    docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# Create repo if needed
aws ecr describe-repositories --repository-names "$REPO_NAME" --region "$AWS_REGION" 2>/dev/null || \
    aws ecr create-repository --repository-name "$REPO_NAME" --region "$AWS_REGION"

# Tag and push
echo "Pushing to ECR..."
docker tag "${REPO_NAME}:${IMAGE_TAG}" "${ECR_URI}:${IMAGE_TAG}"
docker push "${ECR_URI}:${IMAGE_TAG}"

echo ""
echo "=== Success ==="
echo "Image: ${ECR_URI}:${IMAGE_TAG}"

# Clean up build context copies
rm -rf "$SCRIPT_DIR/entprise" "$SCRIPT_DIR/entpriseX"
