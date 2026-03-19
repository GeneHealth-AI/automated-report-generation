#!/bin/bash
set -e

# Run database migrations

echo "Running database migrations..."

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATABASE_DIR="$SCRIPT_DIR/../database"
TERRAFORM_DIR="$SCRIPT_DIR/../terraform"

# Get database credentials from Terraform
cd "$TERRAFORM_DIR"
DB_SECRET_ARN=$(terraform output -raw rds_secret_arn 2>/dev/null)

if [ -z "$DB_SECRET_ARN" ]; then
    echo "Error: Could not get database secret ARN from Terraform."
    echo "Please run 'terraform apply' first."
    exit 1
fi

# Fetch credentials from Secrets Manager
echo "Fetching database credentials from Secrets Manager..."
DB_CREDS=$(aws secretsmanager get-secret-value --secret-id "$DB_SECRET_ARN" --query SecretString --output text)

DB_HOST=$(echo "$DB_CREDS" | python3 -c "import sys, json; print(json.load(sys.stdin)['host'])")
DB_NAME=$(echo "$DB_CREDS" | python3 -c "import sys, json; print(json.load(sys.stdin)['dbname'])")
DB_USER=$(echo "$DB_CREDS" | python3 -c "import sys, json; print(json.load(sys.stdin)['username'])")
DB_PASS=$(echo "$DB_CREDS" | python3 -c "import sys, json; print(json.load(sys.stdin)['password'])")

echo "Database Host: $DB_HOST"
echo "Database Name: $DB_NAME"

# Check if psql is installed
if ! command -v psql &> /dev/null; then
    echo "Error: psql is not installed."
    echo "Please install PostgreSQL client tools."
    exit 1
fi

# Set password for psql
export PGPASSWORD="$DB_PASS"

# Run schema.sql
echo "Running schema.sql..."
psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -f "$DATABASE_DIR/schema.sql"

echo "Migrations completed successfully!"
