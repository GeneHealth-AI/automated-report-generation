#!/bin/bash
set -e

# Test the API Gateway endpoint

echo "Testing API Gateway endpoint..."

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="$SCRIPT_DIR/../terraform"

# Get API Gateway URL from Terraform
cd "$TERRAFORM_DIR"
API_URL=$(terraform output -raw api_gateway_url 2>/dev/null)
API_KEY_ID=$(terraform output -raw api_key_id 2>/dev/null)

if [ -z "$API_URL" ]; then
    echo "Error: Could not get API Gateway URL from Terraform."
    exit 1
fi

# Get the actual API key value
echo "Fetching API key..."
API_KEY=$(aws apigateway get-api-key --api-key "$API_KEY_ID" --include-value --query 'value' --output text)

echo "API URL: $API_URL"

# Create test payload
cat > /tmp/test-payload.json <<EOF
{
  "annotated_vcf_path": "s3://test-bucket/test-annotated.vcf",
  "vcf_path": "s3://test-bucket/test.vcf",
  "template_path": "s3://test-bucket/template.json",
  "name": "Test Patient",
  "id": "test-123",
  "provider": "Test Provider",
  "output_s3_bucket": "output-bucket"
}
EOF

echo "Sending test request..."
curl -X POST "$API_URL" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $API_KEY" \
  -d @/tmp/test-payload.json \
  | python3 -m json.tool

echo ""
echo "Test completed!"
