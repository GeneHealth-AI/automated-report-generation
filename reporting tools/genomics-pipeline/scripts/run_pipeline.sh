#!/bin/bash
set -euo pipefail

# Main pipeline: FASTQ -> VCF (GPU) -> Annotate (rsIDs) -> Enterprise/EnterpriseX scoring
# Arguments: <S3_INPUT_DIR> <S3_OUTPUT_DIR> <SAMPLE_ID>

S3_INPUT_DIR="$1"
S3_OUTPUT_DIR="$2"
SAMPLE_ID="$3"

# Directories
DATA_DIR="/data"
REF_DIR="$DATA_DIR/data/ref"
SNPEFF_DIR="$DATA_DIR/data"
# Use /scratch if available (host-mounted volume), otherwise fall back to /tmp
if [ -d "/scratch" ] && [ -w "/scratch" ]; then
    WORK_DIR=$(mktemp -d /scratch/pipeline.XXXXXX)
else
    WORK_DIR=$(mktemp -d)
fi
ENTPRISE_DIR="/home/ec2-user/entprise"
ENTPRISEX_DIR="/home/ec2-user/entpriseX"
STR_DIR="/home/ec2-user/str"

REF_FILE="$REF_DIR/Homo_sapiens.GRCh38.dna.primary_assembly.fa"
LOG_FILE="$WORK_DIR/pipeline_timing.log"

# S3 URIs for large data (override via env vars)
REF_S3_URI="${REF_S3_URI:-s3://entprises/ref/}"
STR_S3_URI="${STR_S3_URI:-s3://exomeinputbucket/str_entprise.tar.gz}"
DBSNP_S3_URI="${DBSNP_S3_URI:-}"

echo "Working directory: $WORK_DIR"
cd "$WORK_DIR"

START_TIME=$(date +%s)
LAST_STEP_TIME=$START_TIME

log_time() {
    local now=$(date +%s)
    local step_elapsed=$((now - LAST_STEP_TIME))
    local total_elapsed=$((now - START_TIME))
    echo "[TIME] $1 completed at $(date). Step: ${step_elapsed}s. Total: ${total_elapsed}s" | tee -a "$LOG_FILE"
    LAST_STEP_TIME=$now
}

# ============================================================
# STEP 1: Discover and download FASTQ files from S3 directory
# ============================================================
echo "=== Step 1: Downloading FASTQ files ==="

# List files in the S3 input directory
S3_FILES=$(aws s3 ls "${S3_INPUT_DIR%/}/" | awk '{print $4}' | grep -iE '\.(fastq|fq)(\.gz)?$' || true)

if [ -z "$S3_FILES" ]; then
    echo "ERROR: No FASTQ files found in $S3_INPUT_DIR"
    exit 1
fi

echo "Found FASTQ files:"
echo "$S3_FILES"

# Identify R1 and R2 (look for _R1/_R2, _1/_2, or paired naming)
R1_FILE=$(echo "$S3_FILES" | grep -iE '(_R1[_.]|_1\.(fastq|fq))' | head -1)
R2_FILE=$(echo "$S3_FILES" | grep -iE '(_R2[_.]|_2\.(fastq|fq))' | head -1)

# Fallback: if only two files, assume first is R1, second is R2
if [ -z "$R1_FILE" ] || [ -z "$R2_FILE" ]; then
    FILE_COUNT=$(echo "$S3_FILES" | wc -l)
    if [ "$FILE_COUNT" -eq 2 ]; then
        R1_FILE=$(echo "$S3_FILES" | head -1)
        R2_FILE=$(echo "$S3_FILES" | tail -1)
        echo "Using file order: R1=$R1_FILE, R2=$R2_FILE"
    else
        echo "ERROR: Cannot identify paired reads. Found: $S3_FILES"
        exit 1
    fi
fi

echo "R1: $R1_FILE"
echo "R2: $R2_FILE"

LOCAL_R1="$WORK_DIR/R1.fq.gz"
LOCAL_R2="$WORK_DIR/R2.fq.gz"

aws s3 cp "${S3_INPUT_DIR%/}/$R1_FILE" "$LOCAL_R1"
log_time "Download R1"

aws s3 cp "${S3_INPUT_DIR%/}/$R2_FILE" "$LOCAL_R2"
log_time "Download R2"

# Decompress if not gzipped (Parabricks handles .gz natively)
if [[ "$R1_FILE" != *.gz ]]; then
    echo "Compressing R1 for Parabricks compatibility..."
    pigz "$LOCAL_R1" && LOCAL_R1="${LOCAL_R1}.gz"
fi
if [[ "$R2_FILE" != *.gz ]]; then
    echo "Compressing R2 for Parabricks compatibility..."
    pigz "$LOCAL_R2" && LOCAL_R2="${LOCAL_R2}.gz"
fi

# ============================================================
# STEP 2: Download reference genome (if not already present)
# ============================================================
echo "=== Step 2: Preparing reference genome ==="
mkdir -p "$REF_DIR"

if [ ! -f "$REF_FILE" ]; then
    if [ -n "$REF_S3_URI" ]; then
        if [[ "$REF_S3_URI" == */ ]]; then
            echo "Syncing reference from $REF_S3_URI..."
            aws s3 sync "$REF_S3_URI" "$REF_DIR/"
        else
            echo "Downloading reference from $REF_S3_URI..."
            aws s3 cp "$REF_S3_URI" "$REF_FILE"
            if [[ "$REF_S3_URI" == *.gz ]]; then
                gunzip -k "$REF_FILE"
                REF_FILE="${REF_FILE%.gz}"
            fi
        fi
    else
        echo "Downloading reference from Ensembl (fallback)..."
        wget -c "ftp://ftp.ensembl.org/pub/release-110/fasta/homo_sapiens/dna/Homo_sapiens.GRCh38.dna.primary_assembly.fa.gz" \
            -O "${REF_FILE}.gz"
        gunzip "${REF_FILE}.gz"
    fi
    log_time "Reference Download"
fi

# Index reference if needed
if [ ! -f "${REF_FILE}.amb" ]; then
    echo "Indexing reference with BWA..."
    bwa index "$REF_FILE"
    log_time "Reference Indexing"
fi

# ============================================================
# STEP 3: Download structure files for Enterprise (if needed)
# ============================================================
echo "=== Step 3: Preparing structure files ==="

if [ ! -d "$STR_DIR" ] || [ -z "$(ls -A $STR_DIR 2>/dev/null)" ]; then
    if [ -n "$STR_S3_URI" ]; then
        if [[ "$STR_S3_URI" == *.tar.gz ]]; then
            echo "Downloading and extracting structure files from $STR_S3_URI..."
            aws s3 cp "$STR_S3_URI" "$WORK_DIR/str_entprise.tar.gz"
            tar -xzf "$WORK_DIR/str_entprise.tar.gz" -C /home/ec2-user/
            rm "$WORK_DIR/str_entprise.tar.gz"
        else
            echo "Syncing structure files from $STR_S3_URI..."
            mkdir -p "$STR_DIR"
            aws s3 sync "${STR_S3_URI%/}/" "$STR_DIR/"
        fi
        log_time "Structure Files Download"
    else
        echo "WARNING: No structure files available. Enterprise scoring may fail."
    fi
fi

# ============================================================
# STEP 4: GPU-accelerated FASTQ -> BAM -> VCF (Parabricks)
# ============================================================
echo "=== Step 4: Running Parabricks fq2bam (GPU) ==="

SORTED_BAM="$WORK_DIR/sorted.bam"
OUTPUT_VCF="$WORK_DIR/raw_variants.vcf"

pbrun fq2bam \
    --ref "$REF_FILE" \
    --in-fq "$LOCAL_R1" "$LOCAL_R2" \
    --out-bam "$SORTED_BAM" \
    --low-memory

log_time "Parabricks fq2bam"

echo "=== Step 4b: Running Parabricks HaplotypeCaller (GPU) ==="

pbrun haplotypecaller \
    --ref "$REF_FILE" \
    --in-bam "$SORTED_BAM" \
    --out-variants "$OUTPUT_VCF"

log_time "Parabricks HaplotypeCaller"

# Free BAM to save disk
rm -f "$SORTED_BAM"

# ============================================================
# STEP 5: Annotation (SnpEff) + rsID lookup (SnpSift + dbSNP)
# ============================================================
echo "=== Step 5: Annotating variants ==="

RAW_ANNOTATED_VCF="$WORK_DIR/raw_annotated.vcf"
ANNOTATED_VCF="$WORK_DIR/annotated.vcf"

# Download SnpEff databases if needed
snpEff download -v GRCh38.mane.1.0.refseq -dataDir "$SNPEFF_DIR" 2>/dev/null || echo "SnpEff MANE DB already present"

# Functional annotation
snpEff -v -noStats -dataDir "$SNPEFF_DIR" GRCh38.mane.1.0.refseq "$OUTPUT_VCF" > "$RAW_ANNOTATED_VCF"
log_time "SnpEff Annotation"

# rsID annotation using SnpSift + dbSNP
echo "Adding rsIDs with SnpSift..."
DBSNP_VCF="$REF_DIR/dbsnp_common.vcf.gz"

if [ ! -f "$DBSNP_VCF" ]; then
    if [ -n "$DBSNP_S3_URI" ]; then
        aws s3 cp "$DBSNP_S3_URI" "$DBSNP_VCF"
        aws s3 cp "${DBSNP_S3_URI}.tbi" "${DBSNP_VCF}.tbi" 2>/dev/null || true
    else
        echo "Downloading dbSNP common VCF..."
        wget -q -c "https://ftp.ncbi.nlm.nih.gov/snp/latest_release/VCF/00-common_all.vcf.gz" -O "$DBSNP_VCF" || \
        wget -q -c "https://ftp.ncbi.nlm.nih.gov/snp/organisms/human_9606_b151_GRCh38p7/VCF/00-common_all.vcf.gz" -O "$DBSNP_VCF"
        wget -q -c "${DBSNP_VCF}.tbi" -O "${DBSNP_VCF}.tbi" 2>/dev/null || true
    fi
fi

SnpSift annotate "$DBSNP_VCF" "$RAW_ANNOTATED_VCF" > "$ANNOTATED_VCF" 2>/dev/null || {
    echo "WARNING: SnpSift rsID annotation failed, continuing with raw annotation."
    cp "$RAW_ANNOTATED_VCF" "$ANNOTATED_VCF"
}
log_time "rsID Annotation"

# ============================================================
# STEP 6: Enterprise + EnterpriseX Disease Scoring
# ============================================================
echo "=== Step 6: Running Enterprise/EnterpriseX scoring ==="

ENTERPRISE_OUTPUT="$WORK_DIR/enterprise_scores.txt"

# Ensure binaries are executable
chmod +x "$ENTPRISE_DIR"/scan_genfea3_pred.job "$ENTPRISE_DIR"/genfea_cnt_v3_bcnt2_ent "$ENTPRISE_DIR"/treebind_rn_ca_n8 2>/dev/null || true
chmod +x "$ENTPRISEX_DIR"/scan_pred.job "$ENTPRISEX_DIR"/genfea_cnt_v3_bcnt2_nocomp_ns "$ENTPRISEX_DIR"/treebind_rn_ca_n8 "$ENTPRISEX_DIR"/genfea.job 2>/dev/null || true

if [ -d "$ENTPRISE_DIR" ] && [ -f "$ENTPRISE_DIR/scan_genfea3_pred.job" ]; then
    python3 /app/scripts/run_enterprise.py "$ANNOTATED_VCF" "$ENTERPRISE_OUTPUT"
    log_time "Enterprise Scoring"
else
    echo "WARNING: Enterprise binaries not found. Skipping scoring."
    touch "$ENTERPRISE_OUTPUT"
fi

# ============================================================
# STEP 7: Consolidate final report (rsIDs + scores + mutations)
# ============================================================
echo "=== Step 7: Generating final report ==="

FINAL_REPORT="$WORK_DIR/final_report.txt"

python3 /app/scripts/consolidate_results.py \
    --vcf "$ANNOTATED_VCF" \
    --scores "$ENTERPRISE_OUTPUT" \
    --mapping "$ENTPRISE_DIR/list_ref_gene.lst" \
    --output "$FINAL_REPORT"

log_time "Final Consolidation"

# ============================================================
# STEP 8: Upload results to S3
# ============================================================
echo "=== Step 8: Uploading results to $S3_OUTPUT_DIR ==="

aws s3 cp "$FINAL_REPORT"       "${S3_OUTPUT_DIR%/}/final_report.txt"
aws s3 cp "$ANNOTATED_VCF"      "${S3_OUTPUT_DIR%/}/annotated.vcf"
aws s3 cp "$ENTERPRISE_OUTPUT"  "${S3_OUTPUT_DIR%/}/enterprise_scores.txt"
aws s3 cp "$OUTPUT_VCF"         "${S3_OUTPUT_DIR%/}/raw_variants.vcf"
aws s3 cp "$LOG_FILE"           "${S3_OUTPUT_DIR%/}/pipeline_timing.log"

log_time "Upload Results"

# ============================================================
# STEP 9: Notify website that conversion is complete
# ============================================================
echo "=== Step 9: Sending conversion-complete webhook ==="

VCF_PATH="provider-uploads/${SAMPLE_ID}.vcf"

WEBHOOK_HTTP_CODE=$(curl -s -o /tmp/webhook_response.txt -w "%{http_code}" \
    -X POST https://www.genehealth.ai/api/amazon/conversion-complete \
    -H "Content-Type: application/json" \
    -H "x-auth-amazon: Ax1AAlZCCEdON7WXxZOkUDdGbC-0zuXnCGF6dwl7lor5l+Nukd2yh3HWtoNbo" \
    -d "{\"path\": \"${VCF_PATH}\"}" \
) || true

if [ "$WEBHOOK_HTTP_CODE" -ge 200 ] 2>/dev/null && [ "$WEBHOOK_HTTP_CODE" -lt 300 ] 2>/dev/null; then
    echo "Webhook succeeded (HTTP $WEBHOOK_HTTP_CODE)"
else
    echo "WARNING: Webhook failed (HTTP $WEBHOOK_HTTP_CODE). Response: $(cat /tmp/webhook_response.txt 2>/dev/null)"
    echo "Pipeline results were uploaded successfully — webhook failure is non-blocking."
fi

log_time "Webhook Notification"

# Summary
TOTAL_TIME=$(($(date +%s) - START_TIME))
echo ""
echo "========================================"
echo "Pipeline Complete!"
echo "Total time: ${TOTAL_TIME}s ($(( TOTAL_TIME / 60 ))m $(( TOTAL_TIME % 60 ))s)"
echo "Results at: $S3_OUTPUT_DIR"
echo "========================================"
