FROM continuumio/miniconda3:latest

# Install basic tools
RUN apt-get update && apt-get install -y wget curl build-essential && apt-get clean

# Set working directory
WORKDIR /app
ENV BASE_DIR="/app"

# Copy pipeline scripts
COPY pipeline/ /app/pipeline/

# Create Conda Environment
# We can reuse the logic or just run commands.
# Let's create the environment first to cache it.
RUN conda create -y -n bio_pipeline -c bioconda -c conda-forge \
    bwa samtools bcftools snpeff python=3.9 && \
    conda clean -a -y

# Download Logic
# The user wants to download databases at BUILD TIME for the image
# So we run the download steps here.
# NOTE: This makes the image LARGE.
RUN /bin/bash -c "source /opt/conda/bin/activate bio_pipeline && \
    mkdir -p /app/data/ref && \
    wget -c ftp://ftp.ensembl.org/pub/release-110/fasta/homo_sapiens/dna/Homo_sapiens.GRCh38.dna.primary_assembly.fa.gz -O /app/data/ref/Homo_sapiens.GRCh38.dna.primary_assembly.fa.gz && \
    gunzip -k /app/data/ref/Homo_sapiens.GRCh38.dna.primary_assembly.fa.gz && \
    bwa index /app/data/ref/Homo_sapiens.GRCh38.dna.primary_assembly.fa && \
    snpEff download -v GRCh38.mane.1.0.refseq -dataDir /app/data"

# Ensure scripts are executable
RUN chmod +x /app/pipeline/*.sh

# Entrypoint
ENTRYPOINT ["/bin/bash", "/app/pipeline/run_pipeline.sh"]
