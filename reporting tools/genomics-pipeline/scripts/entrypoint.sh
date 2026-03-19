#!/bin/bash
set -euo pipefail

# Entrypoint for the genomics pipeline container.
# Accepts either:
#   1. Environment variables: S3_INPUT_DIR, S3_OUTPUT_DIR
#   2. Positional args: <S3_INPUT_DIR> <S3_OUTPUT_DIR>
#   3. JSON from SQS message via SQS_MESSAGE env var

echo "=== Genomics Pipeline Starting at $(date) ==="

# Parse input from SQS message JSON if provided
if [ -n "${SQS_MESSAGE:-}" ]; then
    echo "Parsing SQS message..."
    S3_INPUT_DIR=$(echo "$SQS_MESSAGE" | python3 -c "import sys,json; msg=json.load(sys.stdin); print(msg['s3_input_dir'])")
    S3_OUTPUT_DIR=$(echo "$SQS_MESSAGE" | python3 -c "import sys,json; msg=json.load(sys.stdin); print(msg.get('s3_output_dir', msg['s3_input_dir'].rstrip('/') + '/results/'))")
    SAMPLE_ID=$(echo "$SQS_MESSAGE" | python3 -c "import sys,json; msg=json.load(sys.stdin); print(msg.get('sample_id', 'sample'))")
    export S3_INPUT_DIR S3_OUTPUT_DIR SAMPLE_ID
fi

# Positional args override
S3_INPUT_DIR="${1:-${S3_INPUT_DIR:-}}"
S3_OUTPUT_DIR="${2:-${S3_OUTPUT_DIR:-}}"
SAMPLE_ID="${SAMPLE_ID:-sample_$(date +%Y%m%d_%H%M%S)}"

if [ -z "$S3_INPUT_DIR" ]; then
    echo "ERROR: No input directory specified."
    echo "Usage: docker run <image> <S3_INPUT_DIR> [S3_OUTPUT_DIR]"
    echo "   or: set S3_INPUT_DIR and S3_OUTPUT_DIR env vars"
    echo "   or: set SQS_MESSAGE env var with JSON: {\"s3_input_dir\": \"s3://bucket/path/\"}"
    exit 1
fi

# Default output to input_dir/results/
if [ -z "$S3_OUTPUT_DIR" ]; then
    S3_OUTPUT_DIR="${S3_INPUT_DIR%/}/results/"
fi

echo "Input:  $S3_INPUT_DIR"
echo "Output: $S3_OUTPUT_DIR"
echo "Sample: $SAMPLE_ID"

# Run the main pipeline
exec /bin/bash /app/scripts/run_pipeline.sh \
    "$S3_INPUT_DIR" \
    "$S3_OUTPUT_DIR" \
    "$SAMPLE_ID"
