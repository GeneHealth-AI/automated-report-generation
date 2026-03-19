# Build stage: install dependencies
FROM --platform=linux/amd64 python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Final stage
FROM --platform=linux/amd64 python:3.11-slim

WORKDIR /app

# Copy python packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy application files (Verified existing files)
COPY fargate_entrypoint.py .
COPY ReportGenerator.py .
COPY json_report_writer.py .
COPY EnrichPositions.py .
COPY block_generator.py .
COPY report_blocks.py .
COPY token_counter.py .
COPY variant_classifier.py .
COPY enhanced_data_models.py .
COPY section_manager.py .
COPY mutation_cache_manager.py .
COPY mutation_description_generator.py .
COPY review_agent.py .
COPY pubmed_searcher.py .
COPY allproteins2knowgene .
COPY gwas_catalog_v1.0.2-associations_e114_r2025-07-10.tsv .

# Copy scripts and blocks directories
COPY blocks/ ./blocks/
COPY scripts/ ./scripts/

# Copy key scripts to root for easier imports if needed by entrypoint
COPY scripts/finalpdfgen.py .
COPY scripts/protein_enrichment_service.py .
COPY scripts/validation_monitor.py .
COPY scripts/visual_html_generator.py .

# Create directories for output
RUN mkdir -p /tmp/reports_json /tmp/reports_pdf

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV BLOCKS_PATH="./blocks"
ENV KNOWGENE_PATH="./allproteins2knowgene"

# Disable proxy settings to prevent the proxies error
ENV HTTP_PROXY=""
ENV HTTPS_PROXY=""
ENV http_proxy=""
ENV https_proxy=""
ENV NO_PROXY="*"
ENV no_proxy="*"

# Entry point
ENTRYPOINT ["python", "fargate_entrypoint.py"]