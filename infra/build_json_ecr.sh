#!/bin/bash
# Enhanced script to build and push the JSON container for Linux/x86

set -e  # Exit immediately if a command exits with a non-zero status

# Set your AWS region and account ID
AWS_REGION="us-east-2"  # Change to your preferred region
AWS_ACCOUNT_ID="339712911975"  # Your specific ECR account number

# Repository name
ECR_REPO_JSON="report-generator-json"

echo "=== Starting JSON container build process ==="
echo "Target architecture: linux/amd64"
echo "AWS Account: $AWS_ACCOUNT_ID"
echo "ECR Repository: $ECR_REPO_JSON"

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
  echo "Error: Docker is not running or not accessible"
  exit 1
fi

# Ensure we're building for the right platform
echo "=== Setting up platform for build ==="
export DOCKER_DEFAULT_PLATFORM=linux/amd64

# Print Docker version info
echo "=== Docker version information ==="
docker version
echo ""

# Print system information
echo "=== System information ==="
uname -a
echo ""

# Check if required files exist
echo "=== Checking required files ==="
required_files=("Dockerfile.json" "requirements.txt" "StartReportGeneration.py" "ReportGenerator.py" "block_generator.py")
for file in "${required_files[@]}"; do
  if [ ! -f "$file" ]; then
    echo "Error: Required file $file not found"
    exit 1
  else
    echo "✓ $file found"
  fi
done
echo ""

# Build the container with detailed output
echo "=== Building JSON container ==="
echo "This may take a few minutes..."
docker build --platform=linux/amd64 --progress=plain -t $ECR_REPO_JSON:latest -f Dockerfile.json . || {
  echo "Error: Docker build failed"
  exit 1
}

echo "=== Container built successfully ==="

# Test the container locally (optional)
echo "=== Testing container locally ==="
docker run --rm $ECR_REPO_JSON:latest python -c "import sys, pkg_resources; print(f'Python version: {sys.version}'); print('Installed packages:'); print('openai: ' + pkg_resources.get_distribution('openai').version); print('anthropic: ' + pkg_resources.get_distribution('anthropic').version); print('biopython: ' + pkg_resources.get_distribution('biopython').version)" || {
  echo "Warning: Container test failed, but continuing with push"
}

# Login to ECR
echo "=== Logging in to ECR ==="
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com || {
  echo "Error: Failed to log in to ECR"
  exit 1
}

# Create repository if it doesn't exist
echo "=== Creating ECR repository if needed ==="
aws ecr describe-repositories --repository-names $ECR_REPO_JSON --region $AWS_REGION || {
  echo "Repository doesn't exist, creating it now..."
  aws ecr create-repository --repository-name $ECR_REPO_JSON --region $AWS_REGION || {
    echo "Error: Failed to create ECR repository"
    exit 1
  }
}

# Tag and push the container
echo "=== Tagging and pushing container to ECR ==="
docker tag $ECR_REPO_JSON:latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_JSON:latest || {
  echo "Error: Failed to tag container"
  exit 1
}

docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_JSON:latest || {
  echo "Error: Failed to push container to ECR"
  exit 1
}

echo "=== JSON container successfully pushed to ECR ==="
echo "Container URI: $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_JSON:latest"
echo ""
echo "To use this container in ECS/Fargate, create a task definition with the following container definition:"
echo "{
  \"name\": \"report-generator-json\",
  \"image\": \"$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_JSON:latest\",
  \"essential\": true,
  \"environment\": [
    {\"name\": \"REPORT_TEMPLATE\", \"value\": \"s3://your-bucket/template.json\"},
    {\"name\": \"PURE_VCF\", \"value\": \"s3://your-bucket/sample.vcf\"},
    {\"name\": \"ANNOTATED_PATH\", \"value\": \"s3://your-bucket/annotated.vcf\"},
    {\"name\": \"OUTPUT_PREFIX\", \"value\": \"report-\"},
    {\"name\": \"ANTHROPIC_API_KEY\", \"value\": \"your-api-key\"}
  ]
}"