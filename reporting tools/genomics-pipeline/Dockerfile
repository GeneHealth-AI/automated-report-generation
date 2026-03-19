# GPU Genomics Pipeline: FASTQ -> VCF -> Enterprise/EnterpriseX Disease Scoring
# Base: NVIDIA Clara Parabricks (GPU-accelerated alignment & variant calling)
FROM nvcr.io/nvidia/clara/clara-parabricks:4.4.0-1

ENV DEBIAN_FRONTEND=noninteractive
ENV BASE_DIR="/app"
ENV ENTPRISE_DIR="/home/ec2-user/entprise"
ENV ENTPRISEX_DIR="/home/ec2-user/entpriseX"
ENV STR_DIR="/home/ec2-user/str"
ENV DATA_DIR="/data"

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y \
        python3 python3-pip \
        openjdk-21-jre-headless \
        wget unzip curl \
        tcsh \
        bwa samtools bcftools \
        pigz \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Python packages (no hardcoded credentials - use IAM roles)
RUN pip3 install --no-cache-dir boto3 awscli

# Install SnpEff + SnpSift for annotation and rsID lookup
RUN wget -q https://snpeff-public.s3.amazonaws.com/versions/snpEff_latest_core.zip && \
    unzip -q snpEff_latest_core.zip && \
    rm snpEff_latest_core.zip && \
    echo '#!/bin/bash\njava -Xmx8g -jar /app/snpEff/snpEff.jar "$@"' > /usr/local/bin/snpEff && \
    chmod +x /usr/local/bin/snpEff && \
    echo '#!/bin/bash\njava -Xmx8g -jar /app/snpEff/SnpSift.jar "$@"' > /usr/local/bin/SnpSift && \
    chmod +x /usr/local/bin/SnpSift
ENV PATH="/app/snpEff:${PATH}"

# Copy pipeline scripts
COPY scripts/ /app/scripts/
RUN chmod +x /app/scripts/*.sh

# Copy Enterprise and EnterpriseX binaries (baked into image for reliability)
# These are the scoring tools - relatively small (~1.5GB total)
COPY entprise/ /home/ec2-user/entprise/
COPY entpriseX/ /home/ec2-user/entpriseX/
RUN chmod +x /home/ec2-user/entprise/scan_genfea3_pred.job \
              /home/ec2-user/entprise/genfea_cnt_v3_bcnt2_ent \
              /home/ec2-user/entprise/treebind_rn_ca_n8 \
              /home/ec2-user/entpriseX/scan_pred.job \
              /home/ec2-user/entpriseX/genfea_cnt_v3_bcnt2_nocomp_ns \
              /home/ec2-user/entpriseX/treebind_rn_ca_n8 \
              /home/ec2-user/entpriseX/genfea.job 2>/dev/null || true

# Create runtime directories
RUN mkdir -p /data/data/ref /home/ec2-user/str

ENTRYPOINT ["/bin/bash", "/app/scripts/entrypoint.sh"]
