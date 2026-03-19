#!/bin/bash
set -e

# Update API keys in AWS Secrets Manager

echo "Updating API keys in AWS Secrets Manager..."

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="$SCRIPT_DIR/../terraform"

# Get secret ARNs from Terraform
cd "$TERRAFORM_DIR"
ANTHROPIC_SECRET_ARN=$(terraform output -raw anthropic_secret_arn 2>/dev/null)
GEMINI_SECRET_ARN=$(terraform output -raw gemini_secret_arn 2>/dev/null)

if [ -z "$ANTHROPIC_SECRET_ARN" ] || [ -z "$GEMINI_SECRET_ARN" ]; then
    echo "Error: Could not get secret ARNs from Terraform."
    exit 1
fi

echo "Secret ARNs retrieved successfully."
echo ""

# Prompt for Anthropic API key
read -sp "Enter Anthropic API Key (or press Enter to skip): " ANTHROPIC_KEY
echo ""

if [ -n "$ANTHROPIC_KEY" ]; then
    echo "Updating Anthropic API key..."
    aws secretsmanager put-secret-value \
        --secret-id "$ANTHROPIC_SECRET_ARN" \
        --secret-string "$ANTHROPIC_KEY"
    echo "Anthropic API key updated successfully!"
else
    echo "Skipping Anthropic API key update."
fi

echo ""

# Prompt for Gemini API key
read -sp "Enter Google Gemini API Key (or press Enter to skip): " GEMINI_KEY
echo ""

if [ -n "$GEMINI_KEY" ]; then
    echo "Updating Gemini API key..."
    aws secretsmanager put-secret-value \
        --secret-id "$GEMINI_SECRET_ARN" \
        --secret-string "$GEMINI_KEY"
    echo "Gemini API key updated successfully!"
else
    echo "Skipping Gemini API key update."
fi

echo ""
echo "API key update process completed!"
