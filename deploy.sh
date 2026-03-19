#!/bin/bash
# Deploy the report generation system to AWS
# Builds Docker container, pushes to ECR, and updates ECS task definition
#
# Usage: ./deploy.sh
#
# Prerequisites:
#   - AWS CLI configured with proper credentials
#   - Docker running
#   - Account 339712911975 ECR access

set -e

# --- Configuration ---
AWS_REGION="us-east-2"
AWS_ACCOUNT_ID="339712911975"
ECR_REPO="report-generator-json"
ECS_CLUSTER="report-generation-cluster"
TASK_FAMILY="report-generator-json"
IMAGE_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:latest"

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "============================================"
echo "  Report Generator - AWS Deployment"
echo "============================================"
echo "Region:     ${AWS_REGION}"
echo "Account:    ${AWS_ACCOUNT_ID}"
echo "ECR Repo:   ${ECR_REPO}"
echo "Project:    ${PROJECT_DIR}"
echo ""

# --- Step 1: Verify prerequisites ---
echo "=== Step 1: Checking prerequisites ==="

if ! command -v aws &> /dev/null; then
    echo "Error: AWS CLI not found. Install it first."
    exit 1
fi
echo "✓ AWS CLI found"

if ! docker info > /dev/null 2>&1; then
    echo "Error: Docker is not running"
    exit 1
fi
echo "✓ Docker running"

# Verify AWS credentials
if ! aws sts get-caller-identity --region "${AWS_REGION}" > /dev/null 2>&1; then
    echo "Error: AWS credentials not configured or expired"
    exit 1
fi
CALLER=$(aws sts get-caller-identity --region "${AWS_REGION}" --query 'Arn' --output text)
echo "✓ AWS authenticated as: ${CALLER}"
echo ""

# --- Step 2: Prepare build context ---
echo "=== Step 2: Preparing build context ==="
BUILD_DIR=$(mktemp -d)
echo "Build directory: ${BUILD_DIR}"

# Copy Dockerfile
cp "${PROJECT_DIR}/infra/Dockerfile" "${BUILD_DIR}/Dockerfile"

# Copy all Python source files
for f in \
    fargate_entrypoint.py \
    ReportGenerator.py \
    json_report_writer.py \
    EnrichPositions.py \
    block_generator.py \
    report_blocks.py \
    token_counter.py \
    variant_classifier.py \
    enhanced_data_models.py \
    section_manager.py \
    mutation_cache_manager.py \
    mutation_description_generator.py \
    review_agent.py \
    pubmed_searcher.py \
    requirements.txt; do
    if [ -f "${PROJECT_DIR}/${f}" ]; then
        cp "${PROJECT_DIR}/${f}" "${BUILD_DIR}/"
        echo "  ✓ ${f}"
    else
        echo "  ⚠ ${f} not found, skipping"
    fi
done

# Copy directories
cp -r "${PROJECT_DIR}/blocks" "${BUILD_DIR}/blocks"
echo "  ✓ blocks/"

cp -r "${PROJECT_DIR}/scripts" "${BUILD_DIR}/scripts"
echo "  ✓ scripts/"

# Copy reference data
if [ -e "${PROJECT_DIR}/allproteins2knowgene" ]; then
    cp -r "${PROJECT_DIR}/allproteins2knowgene" "${BUILD_DIR}/allproteins2knowgene"
    echo "  ✓ allproteins2knowgene"
fi

GWAS_FILE=$(ls "${PROJECT_DIR}"/gwas_catalog_*.tsv 2>/dev/null | head -1)
if [ -n "${GWAS_FILE}" ]; then
    cp "${GWAS_FILE}" "${BUILD_DIR}/"
    echo "  ✓ $(basename ${GWAS_FILE})"
fi

echo ""

# --- Step 3: Build Docker image ---
echo "=== Step 3: Building Docker image (linux/amd64) ==="
cd "${BUILD_DIR}"
docker build --platform=linux/amd64 --progress=plain -t "${ECR_REPO}:latest" . 2>&1 | tail -20

echo ""
echo "✓ Docker image built successfully"
echo ""

# --- Step 4: Push to ECR ---
echo "=== Step 4: Pushing to ECR ==="

# Login to ECR
aws ecr get-login-password --region "${AWS_REGION}" \
    | docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
echo "✓ ECR login successful"

# Create repo if it doesn't exist
aws ecr describe-repositories --repository-names "${ECR_REPO}" --region "${AWS_REGION}" > /dev/null 2>&1 || {
    echo "Creating ECR repository..."
    aws ecr create-repository --repository-name "${ECR_REPO}" --region "${AWS_REGION}"
}

# Tag and push
docker tag "${ECR_REPO}:latest" "${IMAGE_URI}"
docker push "${IMAGE_URI}"
echo "✓ Image pushed to: ${IMAGE_URI}"
echo ""

# --- Step 5: Update ECS task definition ---
echo "=== Step 5: Updating ECS task definition ==="

# Check if cluster exists, create if not
aws ecs describe-clusters --clusters "${ECS_CLUSTER}" --region "${AWS_REGION}" --query 'clusters[0].status' --output text 2>/dev/null | grep -q ACTIVE || {
    echo "Creating ECS cluster: ${ECS_CLUSTER}"
    aws ecs create-cluster --cluster-name "${ECS_CLUSTER}" --region "${AWS_REGION}"
}
echo "✓ ECS cluster: ${ECS_CLUSTER}"

# Register updated task definition
TASK_DEF=$(cat <<TASKEOF
{
    "family": "${TASK_FAMILY}",
    "networkMode": "awsvpc",
    "requiresCompatibilities": ["FARGATE"],
    "cpu": "1024",
    "memory": "2048",
    "executionRoleArn": "arn:aws:iam::${AWS_ACCOUNT_ID}:role/ecsTaskExecutionRole",
    "taskRoleArn": "arn:aws:iam::${AWS_ACCOUNT_ID}:role/ecsTaskRole",
    "containerDefinitions": [
        {
            "name": "report-generator-json",
            "image": "${IMAGE_URI}",
            "essential": true,
            "environment": [
                {"name": "PYTHONUNBUFFERED", "value": "1"},
                {"name": "BLOCKS_PATH", "value": "./blocks"},
                {"name": "KNOWGENE_PATH", "value": "./allproteins2knowgene"},
                {"name": "HTTP_PROXY", "value": ""},
                {"name": "HTTPS_PROXY", "value": ""},
                {"name": "NO_PROXY", "value": "*"}
            ],
            "logConfiguration": {
                "logDriver": "awslogs",
                "options": {
                    "awslogs-group": "/ecs/report-generator-json",
                    "awslogs-region": "${AWS_REGION}",
                    "awslogs-stream-prefix": "ecs",
                    "awslogs-create-group": "true"
                }
            }
        }
    ]
}
TASKEOF
)

echo "${TASK_DEF}" > /tmp/task-def.json
aws ecs register-task-definition --cli-input-json file:///tmp/task-def.json --region "${AWS_REGION}" > /dev/null
REVISION=$(aws ecs describe-task-definition --task-definition "${TASK_FAMILY}" --region "${AWS_REGION}" --query 'taskDefinition.revision' --output text)
echo "✓ Task definition registered: ${TASK_FAMILY}:${REVISION}"
echo ""

# --- Step 6: Cleanup ---
echo "=== Step 6: Cleanup ==="
rm -rf "${BUILD_DIR}"
echo "✓ Build directory cleaned up"
echo ""

# --- Done ---
echo "============================================"
echo "  Deployment Complete!"
echo "============================================"
echo ""
echo "Image:           ${IMAGE_URI}"
echo "Task Definition: ${TASK_FAMILY}:${REVISION}"
echo "Cluster:         ${ECS_CLUSTER}"
echo ""
echo "To run a test report generation:"
echo ""
echo "  aws ecs run-task \\"
echo "    --cluster ${ECS_CLUSTER} \\"
echo "    --task-definition ${TASK_FAMILY}:${REVISION} \\"
echo "    --launch-type FARGATE \\"
echo "    --network-configuration 'awsvpcConfiguration={subnets=[\"YOUR_SUBNET\"],securityGroups=[\"YOUR_SG\"],assignPublicIp=\"ENABLED\"}' \\"
echo "    --overrides '{"
echo "      \"containerOverrides\": [{"
echo "        \"name\": \"report-generator-json\","
echo "        \"environment\": ["
echo "          {\"name\": \"ANNOTATED_VCF_PATH\", \"value\": \"s3://exomeinputbucket/sample/results/final_report.txt\"},"
echo "          {\"name\": \"VCF_PATH\", \"value\": \"s3://exomeinputbucket/sample/results/raw_variants.vcf\"},"
echo "          {\"name\": \"TEMPLATE_PATH\", \"value\": \"s3://gh-templates/cancer_template.json\"},"
echo "          {\"name\": \"NAME\", \"value\": \"Test Patient\"},"
echo "          {\"name\": \"ID\", \"value\": \"TEST-001\"},"
echo "          {\"name\": \"PROVIDER\", \"value\": \"Test Provider\"},"
echo "          {\"name\": \"OUTPUT_S3_BUCKET\", \"value\": \"ghcompletedreports\"},"
echo "          {\"name\": \"GEMINI_API_KEY\", \"value\": \"YOUR_KEY\"}"
echo "        ]"
echo "      }]"
echo "    }' \\"
echo "    --region ${AWS_REGION}"
echo ""
echo "To watch logs:"
echo "  aws logs tail /ecs/report-generator-json --region ${AWS_REGION} --follow"
