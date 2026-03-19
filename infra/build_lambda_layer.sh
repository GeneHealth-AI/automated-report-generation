#!/bin/bash

# Build Lambda Layer for PDF Report Generator
# This script creates a Lambda layer with all required dependencies

set -e

echo "🚀 Building Lambda Layer for PDF Report Generator"
echo "=================================================="

# Configuration
LAYER_NAME="pdf-generator-dependencies"
PYTHON_VERSION="python3.9"
LAYER_DIR="layer"
PACKAGE_DIR="$LAYER_DIR/python"

# Clean up previous builds
echo "🧹 Cleaning up previous builds..."
rm -rf $LAYER_DIR
rm -f ${LAYER_NAME}.zip

# Create layer directory structure
echo "📁 Creating layer directory structure..."
mkdir -p $PACKAGE_DIR

# Install dependencies
echo "📦 Installing dependencies..."
pip install -r lambda_requirements.txt -t $PACKAGE_DIR --no-deps

# Install reportlab with dependencies
echo "📊 Installing ReportLab with dependencies..."
pip install reportlab -t $PACKAGE_DIR

# Remove unnecessary files to reduce layer size
echo "🗑️  Removing unnecessary files..."
find $PACKAGE_DIR -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find $PACKAGE_DIR -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
find $PACKAGE_DIR -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
find $PACKAGE_DIR -name "*.pyc" -delete 2>/dev/null || true
find $PACKAGE_DIR -name "*.pyo" -delete 2>/dev/null || true

# Create zip file
echo "📦 Creating layer zip file..."
cd $LAYER_DIR
zip -r ../${LAYER_NAME}.zip . -q
cd ..

# Get zip file size
ZIP_SIZE=$(du -h ${LAYER_NAME}.zip | cut -f1)
echo "✅ Layer created successfully!"
echo "📄 File: ${LAYER_NAME}.zip"
echo "📊 Size: $ZIP_SIZE"

# Optional: Upload to S3 if AWS CLI is configured
if command -v aws &> /dev/null; then
    read -p "🤔 Upload layer to S3? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # You can customize this bucket name
        S3_BUCKET="your-lambda-layers-bucket"
        S3_KEY="layers/${LAYER_NAME}.zip"
        
        echo "☁️  Uploading to S3..."
        aws s3 cp ${LAYER_NAME}.zip s3://$S3_BUCKET/$S3_KEY
        echo "✅ Uploaded to s3://$S3_BUCKET/$S3_KEY"
        
        # Create or update Lambda layer
        read -p "🤔 Create/update Lambda layer? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "🔧 Creating/updating Lambda layer..."
            aws lambda publish-layer-version \
                --layer-name $LAYER_NAME \
                --description "Dependencies for PDF Report Generator" \
                --content S3Bucket=$S3_BUCKET,S3Key=$S3_KEY \
                --compatible-runtimes python3.9 python3.10 python3.11
            echo "✅ Lambda layer created/updated successfully!"
        fi
    fi
else
    echo "ℹ️  AWS CLI not found. Upload manually to S3 and create Lambda layer."
fi

echo ""
echo "📋 Next Steps:"
echo "1. Upload ${LAYER_NAME}.zip to S3"
echo "2. Create Lambda layer from S3 object"
echo "3. Create Lambda function with this layer"
echo "4. Deploy lambda_function.py as function code"
echo ""
echo "🎉 Build complete!"