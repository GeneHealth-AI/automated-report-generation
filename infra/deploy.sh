#!/bin/bash

# Deployment Script for PDF Report Generator Lambda Function
# This script handles the complete deployment process

set -e

# Configuration
STACK_NAME="precision-medicine-pdf-generator"
REGION="us-east-1"
LAYER_BUCKET="your-lambda-layers-bucket"  # Change this to your bucket
FUNCTION_CODE_BUCKET="your-lambda-code-bucket"  # Change this to your bucket

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 PDF Report Generator Deployment Script${NC}"
echo "=============================================="

# Check prerequisites
echo -e "${YELLOW}🔍 Checking prerequisites...${NC}"

if ! command -v aws &> /dev/null; then
    echo -e "${RED}❌ AWS CLI not found. Please install AWS CLI.${NC}"
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 not found. Please install Python 3.${NC}"
    exit 1
fi

if ! command -v pip &> /dev/null; then
    echo -e "${RED}❌ pip not found. Please install pip.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Prerequisites check passed${NC}"

# Get AWS account ID and region
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
CURRENT_REGION=$(aws configure get region)
REGION=${CURRENT_REGION:-$REGION}

echo -e "${BLUE}📋 Deployment Configuration:${NC}"
echo "  Account ID: $ACCOUNT_ID"
echo "  Region: $REGION"
echo "  Stack Name: $STACK_NAME"

# Step 1: Build Lambda Layer
echo -e "${YELLOW}📦 Step 1: Building Lambda Layer...${NC}"
./build_lambda_layer.sh

# Step 2: Create S3 buckets if they don't exist
echo -e "${YELLOW}☁️  Step 2: Setting up S3 buckets...${NC}"

# Check if layer bucket exists, create if not
if ! aws s3 ls "s3://$LAYER_BUCKET" 2>/dev/null; then
    echo "Creating layer bucket: $LAYER_BUCKET"
    aws s3 mb "s3://$LAYER_BUCKET" --region $REGION
else
    echo "Layer bucket already exists: $LAYER_BUCKET"
fi

# Check if function code bucket exists, create if not
if ! aws s3 ls "s3://$FUNCTION_CODE_BUCKET" 2>/dev/null; then
    echo "Creating function code bucket: $FUNCTION_CODE_BUCKET"
    aws s3 mb "s3://$FUNCTION_CODE_BUCKET" --region $REGION
else
    echo "Function code bucket already exists: $FUNCTION_CODE_BUCKET"
fi

# Step 3: Upload Lambda Layer
echo -e "${YELLOW}⬆️  Step 3: Uploading Lambda Layer...${NC}"
LAYER_S3_KEY="layers/pdf-generator-dependencies.zip"
aws s3 cp pdf-generator-dependencies.zip "s3://$LAYER_BUCKET/$LAYER_S3_KEY"
echo -e "${GREEN}✅ Layer uploaded to s3://$LAYER_BUCKET/$LAYER_S3_KEY${NC}"

# Step 4: Package Lambda Function Code
echo -e "${YELLOW}📦 Step 4: Packaging Lambda Function Code...${NC}"
FUNCTION_ZIP="lambda-function.zip"
zip -r $FUNCTION_ZIP lambda_function.py professional_pdf_generator.py -q
echo -e "${GREEN}✅ Function code packaged: $FUNCTION_ZIP${NC}"

# Step 5: Upload Function Code
echo -e "${YELLOW}⬆️  Step 5: Uploading Function Code...${NC}"
FUNCTION_S3_KEY="code/lambda-function.zip"
aws s3 cp $FUNCTION_ZIP "s3://$FUNCTION_CODE_BUCKET/$FUNCTION_S3_KEY"
echo -e "${GREEN}✅ Function code uploaded to s3://$FUNCTION_CODE_BUCKET/$FUNCTION_S3_KEY${NC}"

# Step 6: Deploy CloudFormation Stack
echo -e "${YELLOW}☁️  Step 6: Deploying CloudFormation Stack...${NC}"

# Check if stack exists
if aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION >/dev/null 2>&1; then
    echo "Stack exists, updating..."
    OPERATION="update-stack"
else
    echo "Stack doesn't exist, creating..."
    OPERATION="create-stack"
fi

aws cloudformation $OPERATION \
    --stack-name $STACK_NAME \
    --template-body file://cloudformation-template.yaml \
    --parameters \
        ParameterKey=LayerS3Bucket,ParameterValue=$LAYER_BUCKET \
        ParameterKey=LayerS3Key,ParameterValue=$LAYER_S3_KEY \
    --capabilities CAPABILITY_NAMED_IAM \
    --region $REGION

echo "Waiting for stack operation to complete..."
aws cloudformation wait stack-${OPERATION%-stack}-complete --stack-name $STACK_NAME --region $REGION

# Step 7: Update Lambda Function Code
echo -e "${YELLOW}🔄 Step 7: Updating Lambda Function Code...${NC}"
FUNCTION_NAME=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`LambdaFunctionArn`].OutputValue' \
    --output text | cut -d':' -f7)

aws lambda update-function-code \
    --function-name $FUNCTION_NAME \
    --s3-bucket $FUNCTION_CODE_BUCKET \
    --s3-key $FUNCTION_S3_KEY \
    --region $REGION

echo -e "${GREEN}✅ Lambda function code updated${NC}"

# Step 8: Get Stack Outputs
echo -e "${YELLOW}📋 Step 8: Getting Stack Information...${NC}"

OUTPUTS=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $REGION \
    --query 'Stacks[0].Outputs')

INPUT_BUCKET=$(echo $OUTPUTS | jq -r '.[] | select(.OutputKey=="InputBucketName") | .OutputValue')
OUTPUT_BUCKET=$(echo $OUTPUTS | jq -r '.[] | select(.OutputKey=="OutputBucketName") | .OutputValue')
API_ENDPOINT=$(echo $OUTPUTS | jq -r '.[] | select(.OutputKey=="APIEndpoint") | .OutputValue')
LAMBDA_ARN=$(echo $OUTPUTS | jq -r '.[] | select(.OutputKey=="LambdaFunctionArn") | .OutputValue')

# Step 9: Test the deployment
echo -e "${YELLOW}🧪 Step 9: Testing the deployment...${NC}"

# Create test directories in input bucket
aws s3api put-object --bucket $INPUT_BUCKET --key pending/ --region $REGION
aws s3api put-object --bucket $INPUT_BUCKET --key processed/ --region $REGION
aws s3api put-object --bucket $INPUT_BUCKET --key failed/ --region $REGION

echo -e "${GREEN}✅ Test directories created in input bucket${NC}"

# Clean up temporary files
echo -e "${YELLOW}🧹 Cleaning up temporary files...${NC}"
rm -f $FUNCTION_ZIP pdf-generator-dependencies.zip
rm -rf layer/

echo -e "${GREEN}✅ Cleanup complete${NC}"

# Display deployment summary
echo ""
echo -e "${BLUE}🎉 Deployment Complete!${NC}"
echo "=========================="
echo -e "${GREEN}✅ Stack Name:${NC} $STACK_NAME"
echo -e "${GREEN}✅ Region:${NC} $REGION"
echo -e "${GREEN}✅ Input Bucket:${NC} $INPUT_BUCKET"
echo -e "${GREEN}✅ Output Bucket:${NC} $OUTPUT_BUCKET"
echo -e "${GREEN}✅ API Endpoint:${NC} $API_ENDPOINT"
echo -e "${GREEN}✅ Lambda Function:${NC} $LAMBDA_ARN"
echo ""
echo -e "${BLUE}📋 Usage Instructions:${NC}"
echo "1. S3 Trigger: Upload JSON files to s3://$INPUT_BUCKET/pending/"
echo "2. API Gateway: POST to $API_ENDPOINT"
echo "3. Direct Invocation: Use AWS CLI or SDK to invoke $FUNCTION_NAME"
echo ""
echo -e "${BLUE}📝 Example API Request:${NC}"
echo "curl -X POST $API_ENDPOINT \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -d '{"
echo "    \"report_data\": {"
echo "      \"report_metadata\": {"
echo "        \"patient_name\": \"Test Patient\","
echo "        \"patient_id\": \"TEST001\","
echo "        \"focus\": \"ADHD\""
echo "      },"
echo "      \"blocks\": {"
echo "        \"executive_summary\": {"
echo "          \"content\": \"{\\\"executive_summary\\\": {\\\"summary_statement\\\": \\\"Test report\\\"}}\""
echo "        }"
echo "      }"
echo "    }"
echo "  }'"
echo ""
echo -e "${GREEN}🎉 Ready to generate PDF reports!${NC}"