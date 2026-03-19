#!/bin/bash
# Helper script to test the Parabricks Genomics ECR Image

# 1. Configuration
IMAGE_URI="339712911975.dkr.ecr.us-east-1.amazonaws.com/parabricks-genomics-pipeline:latest"

# 2. Local Test (using files on this instance)
# Note: Requires --gpus all for Parabricks tools
run_local_test() {
    echo "Starting Local Test..."
    docker run --rm --gpus all \
        -v /home/ec2-user:/data \
        -e R1=/data/test_R1.fq.gz \
        -e R2=/data/test_R2.fq.gz \
        -e STR_S3_URI="s3://exomeinputbucket/str_entprise.tar.gz" \
        -e ENTPRISE_S3_URI="s3://entprises/entprise/" \
        -e ENTPRISEX_S3_URI="s3://entprises/entpriseX/" \
        -e OUTPUT_S3_PATH="/data/local_test_output" \
        $IMAGE_URI
}

# 3. S3 Test (simulating a production run)
run_s3_test() {
    echo "Starting S3 Test..."
    # Replace these with real S3 paths if you want to test full S3 flow
    S3_R1="s3://exomeinputbucket/test_R1.fq.gz"
    S3_R2="s3://exomeinputbucket/test_R2.fq.gz"
    S3_OUTPUT="s3://exomeinputbucket/test_results_$(date +%Y%m%d)/"

    docker run --rm --gpus all \
        -e R1=$S3_R1 \
        -e R2=$S3_R2 \
        -e STR_S3_URI="s3://exomeinputbucket/str_entprise.tar.gz" \
        -e ENTPRISE_S3_URI="s3://entprises/entprise/" \
        -e ENTPRISEX_S3_URI="s3://entprises/entpriseX/" \
        -e OUTPUT_S3_PATH=$S3_OUTPUT \
        $IMAGE_URI
}

# Usage
echo "Choose a test mode:"
echo "1) Local Test (uses /home/ec2-user/test_R*.fq.gz)"
echo "2) S3 Test (requires valid S3 URIs)"
read -p "Enter choice [1-2]: " choice

if [ "$choice" == "1" ]; then
    run_local_test
elif [ "$choice" == "2" ]; then
    run_s3_test
else
    echo "Invalid choice."
fi
