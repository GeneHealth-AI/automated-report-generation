# Genomics Pipeline - Complete Guide

## Overview

GPU-accelerated genomics pipeline that processes raw DNA sequencing data (paired-end FASTQ files) into disease risk scores. The pipeline runs on AWS using SQS for job queuing, Lambda for orchestration, and EC2 GPU instances for compute.

**Pipeline flow:**
```
FASTQ (paired-end reads) → BAM → VCF → Annotated VCF → Disease Scores → Final Report
```

---

## Architecture

```
Scientist uploads FASTQ to S3
        │
        ▼
S3 Bucket (s3://exomeinputbucket/sample_001/)
        │
        ▼
User sends SQS message
        │
        ▼
Lambda (genomics-pipeline-sqs-consumer)
        ├── Generates EC2 user data script
        └── Launches EC2 g4dn.xlarge GPU instance
                │
                ▼
EC2 Instance Bootstrap
        ├── Waits for Docker
        ├── Authenticates to ECR
        ├── Pulls genomics-pipeline Docker image
        └── Runs container with --gpus all
                │
                ▼
Container (8-Step Pipeline)
        ├── Step 1: Download FASTQ from S3
        ├── Step 2: Prepare reference genome (GRCh38)
        ├── Step 3: Download structure files for scoring
        ├── Step 4: GPU alignment (fq2bam) + variant calling (HaplotypeCaller)
        ├── Step 5: SnpEff annotation + dbSNP rsID lookup
        ├── Step 6: Enterprise/EnterpriseX disease scoring
        ├── Step 7: Consolidate final report
        └── Step 8: Upload results to S3
                │
                ▼
Results in S3 (s3://exomeinputbucket/sample_001/results/)
        │
        ▼
EC2 instance self-terminates
```

---

## AWS Resources

| Resource | Name/ID | Purpose |
|----------|---------|---------|
| ECR Image | `339712911975.dkr.ecr.us-east-2.amazonaws.com/genomics-pipeline:latest` | Docker image with pipeline + tools |
| SQS Queue | `genomics-pipeline-jobs` | Job queue (15min visibility, 24h retention) |
| Lambda | `genomics-pipeline-sqs-consumer` | Reads SQS, launches EC2 GPU instances |
| EC2 IAM Role | `genomics-pipeline-ec2-role` | S3, ECR, CloudWatch access for pipeline instances |
| Lambda IAM Role | `genomics-pipeline-lambda-role` | EC2 launch, SQS read, PassRole |
| EC2 Instance Profile | `genomics-pipeline-ec2-profile` | Attached to launched GPU instances |
| Security Group | `sg-0a57fa3416f3f8c0a` | Outbound only (no inbound needed) |
| GPU AMI | `ami-0c77fbc339c52e09b` | Deep Learning Base GPU AMI (Amazon Linux 2023) |
| Region | `us-east-2` (Ohio) | All resources deployed here |

---

## How to Submit a Job

### Single sample

```bash
aws sqs send-message \
  --queue-url https://sqs.us-east-2.amazonaws.com/339712911975/genomics-pipeline-jobs \
  --message-body '{
    "s3_input_dir": "s3://exomeinputbucket/sample_001/",
    "s3_output_dir": "s3://exomeinputbucket/sample_001/results/",
    "sample_id": "sample_001"
  }'
```

### Batch submission (multiple samples in parallel)

```bash
QUEUE_URL="https://sqs.us-east-2.amazonaws.com/339712911975/genomics-pipeline-jobs"

for dir in sample_001 sample_002 sample_003; do
  aws sqs send-message \
    --queue-url "$QUEUE_URL" \
    --message-body "{\"s3_input_dir\": \"s3://exomeinputbucket/${dir}/\", \"sample_id\": \"${dir}\"}"
done
```

Each message launches its own GPU instance, so jobs run in parallel.

### SQS message format

```json
{
  "s3_input_dir": "s3://bucket/path/to/fastq/",
  "s3_output_dir": "s3://bucket/path/to/output/",
  "sample_id": "patient_001",
  "instance_type": "g4dn.xlarge"
}
```

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `s3_input_dir` | Yes | - | S3 directory containing paired FASTQ files |
| `s3_output_dir` | No | `{s3_input_dir}/results/` | Where to upload results |
| `sample_id` | No | `sample` | Identifier for tagging and logging |
| `instance_type` | No | `g4dn.xlarge` | EC2 instance type (must have NVIDIA GPU) |

### Input requirements

The `s3_input_dir` must contain exactly 2 FASTQ files (paired-end reads):
- Naming: `*_R1*.fq.gz` / `*_R2*.fq.gz`, or `*_1.fq.gz` / `*_2.fq.gz`
- If naming is ambiguous, the two files are assigned R1/R2 by alphabetical order
- Supported formats: `.fq.gz`, `.fastq.gz`, `.fq`, `.fastq` (uncompressed files are auto-compressed)

---

## Output Files

Results are uploaded to `s3_output_dir`:

| File | Description |
|------|-------------|
| `final_report.txt` | TSV with disease scores: rsID, allele, protein ID, position, ref/alt amino acids, score, gene |
| `annotated.vcf` | VCF with SnpEff functional annotations + dbSNP rsIDs |
| `enterprise_scores.txt` | Raw Enterprise/EnterpriseX disease scores |
| `raw_variants.vcf` | Unannotated VCF from Parabricks HaplotypeCaller |
| `pipeline_timing.log` | Step-by-step performance timing |
| `ec2_bootstrap.log` | EC2 instance bootstrap log (when run via SQS/Lambda) |

### Final report format

```
# rsID	Allele	Protein_ID	Position	Ref_AA	Alt_AA	Disease_Score	Gene
('rs3130453','T')	NP_001099033.1	78	TRP	TRPTER	0.297016	HLA-B
('rs2272757','A')	NP_056473.2	615	LEU	LEU	.	NOC2L
```

- `Disease_Score`: numeric value from Enterprise/EnterpriseX (`.` if no structure data available)
- Scores closer to 1.0 indicate higher disease risk

---

## Pipeline Steps in Detail

### Step 1: Download FASTQ files
Downloads paired-end FASTQ files from the S3 input directory. Auto-detects R1/R2 pairing. Compresses with pigz if not already gzipped.

### Step 2: Reference genome (GRCh38)
Downloads and indexes the GRCh38 primary assembly reference genome. Cached between runs to avoid re-downloading (~3.2GB uncompressed). BWA index files are generated if not present.

Sources (in order of preference):
1. `REF_S3_URI` env var (default: `s3://entprises/ref/`)
2. Ensembl FTP (fallback)

### Step 3: Structure files
Downloads protein structure files required for Enterprise disease scoring. Extracted from `s3://exomeinputbucket/str_entprise.tar.gz` to `/home/ec2-user/str/`. Contains 327 PDB-derived structure files.

### Step 4: GPU-accelerated alignment and variant calling (Parabricks)
- **fq2bam**: Aligns paired reads to reference genome using GPU-accelerated BWA-MEM. Produces sorted BAM.
- **HaplotypeCaller**: Calls germline variants from BAM. Produces raw VCF.
- Uses NVIDIA Parabricks (50-100x faster than CPU-based tools).
- BAM is deleted after variant calling to free disk space.

### Step 5: Variant annotation
- **SnpEff**: Annotates variants with functional impact (missense, frameshift, stop gained, etc.), gene symbols, transcript IDs, HGVS notation. Uses GRCh38.mane.1.0.refseq database.
- **SnpSift + dbSNP**: Adds rsID identifiers for known variants from dbSNP common variants VCF.

### Step 6: Enterprise/EnterpriseX disease scoring
Extracts protein mutations from the annotated VCF and scores them:
- **Enterprise**: Scores missense variants (single amino acid substitutions) using protein structure-based features.
- **EnterpriseX**: Scores frameshift and nonsense variants (stop gained, stop lost).
- Gene names from SnpEff annotations are mapped to NP_ protein accessions via `list_ref_gene.lst`.
- Only mutations in proteins with available 3D structure data can be scored (~327 proteins).

### Step 7: Final report consolidation
Merges VCF annotations, rsIDs, and disease scores into a single TSV report.

### Step 8: Upload results
Uploads all output files to the S3 output directory.

---

## Docker Image

**Base image:** `nvcr.io/nvidia/clara/clara-parabricks:4.4.0-1`

**Installed tools:**
- Parabricks (pbrun fq2bam, pbrun haplotypecaller)
- BWA, SAMtools, BCFtools
- SnpEff, SnpSift (Java-based, OpenJDK 21)
- Python 3, boto3, awscli
- pigz (parallel gzip)
- Enterprise/EnterpriseX scoring binaries

**Size:** ~3.9GB

### Rebuilding the image

```bash
cd ~/genomics-pipeline
./build_and_push.sh --tag latest --region us-east-2
```

This script:
1. Copies Enterprise/EnterpriseX binaries from `/home/ec2-user/entprise/` and `/home/ec2-user/entpriseX/`
2. Builds the Docker image
3. Logs in to ECR
4. Creates the ECR repo if needed
5. Pushes to ECR
6. Cleans up build context copies

### Running locally (for testing)

```bash
docker run --gpus all \
  -v /home/ec2-user/data:/data/data \
  -v /home/ec2-user/str:/home/ec2-user/str \
  genomics-pipeline:latest \
  "s3://exomeinputbucket/your-sample/" \
  "s3://exomeinputbucket/your-sample/results/" \
  "sample_id"
```

Mount `-v /home/ec2-user/data:/data/data` to use cached reference genome and dbSNP files.

---

## EC2 Instance Configuration

Launched automatically by Lambda when SQS messages arrive.

| Setting | Value |
|---------|-------|
| Instance type | g4dn.xlarge (1 NVIDIA T4 GPU, 4 vCPU, 16 GB RAM) |
| AMI | Deep Learning Base GPU AMI (Amazon Linux 2023) |
| Storage | 500 GB gp3 EBS (deleted on termination) |
| Shutdown behavior | Terminate (auto-cleanup) |
| Tags | `Pipeline=genomics-fastq-to-disease-score`, `AutoTerminate=true` |

Typical runtime: **17-20 minutes** for a whole exome sample (~2.8GB per FASTQ file).

---

## Key Files

```
genomics-pipeline/
├── Dockerfile                    # Container build definition
├── build_and_push.sh            # Build image and push to ECR
├── scripts/
│   ├── entrypoint.sh            # Container entry point (parses SQS/env/args)
│   ├── run_pipeline.sh          # Main 8-step pipeline orchestrator
│   ├── run_enterprise.py        # Enterprise/EnterpriseX scoring wrapper
│   └── consolidate_results.py   # Final report generation
├── lambda/
│   └── sqs_consumer.py          # SQS -> EC2 launcher
└── infra/
    └── setup_aws.sh             # Creates all AWS infrastructure
```

### Supporting data (on the build instance)

```
/home/ec2-user/
├── entprise/                    # Enterprise scoring binaries + data
│   ├── scan_genfea3_pred.job    # Main scoring script
│   ├── genfea_cnt_v3_bcnt2_ent  # Feature extractor
│   ├── treebind_rn_ca_n8        # Structure binding tool
│   ├── list_ref_gene.lst        # Gene -> NP_ protein mapping (19,234 entries)
│   └── result_code.lst          # Protein structure codes (32,584 entries)
├── entpriseX/                   # EnterpriseX binaries (frameshift/nonsense)
│   ├── scan_pred.job
│   ├── genfea_cnt_v3_bcnt2_nocomp_ns
│   ├── treebind_rn_ca_n8
│   └── genfea.job
├── str/                         # Protein structure files (327 PDB structures)
├── data/ref/                    # Cached reference genome + indices
│   ├── Homo_sapiens.GRCh38.dna.primary_assembly.fa    (3.15 GB)
│   ├── Homo_sapiens.GRCh38.dna.primary_assembly.fa.*  (BWA index files)
│   └── dbsnp_common.vcf.gz                            (1.59 GB)
├── A_ALPHA_1.fq.gz              # Test FASTQ R1 (2.8 GB)
└── A_ALPHA_2.fq.gz              # Test FASTQ R2 (2.9 GB)
```

---

## Monitoring

### Check running pipeline instances

```bash
aws ec2 describe-instances \
  --filters "Name=tag:Pipeline,Values=genomics-fastq-to-disease-score" \
            "Name=instance-state-name,Values=running" \
  --query 'Reservations[].Instances[].[InstanceId,LaunchTime,Tags[?Key==`SampleId`].Value|[0]]' \
  --output table --region us-east-2
```

### Check Lambda logs

```bash
aws logs tail /aws/lambda/genomics-pipeline-sqs-consumer --region us-east-2 --follow
```

### Check SQS queue depth

```bash
aws sqs get-queue-attributes \
  --queue-url https://sqs.us-east-2.amazonaws.com/339712911975/genomics-pipeline-jobs \
  --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible \
  --region us-east-2
```

### Check results in S3

```bash
aws s3 ls s3://exomeinputbucket/sample_001/results/
```

---

## Troubleshooting

### Pipeline instance not launching
- Check Lambda CloudWatch logs for errors
- Verify the GPU AMI ID is valid: `aws ec2 describe-images --image-ids ami-0c77fbc339c52e09b --region us-east-2`
- Verify instance profile exists: `aws iam get-instance-profile --instance-profile-name genomics-pipeline-ec2-profile`

### Pipeline fails inside container
- Check bootstrap log: `aws s3 cp s3://bucket/sample/results/ec2_bootstrap.log -`
- Check pipeline timing log: `aws s3 cp s3://bucket/sample/results/pipeline_timing.log -`
- SSH into instance (if KEY_NAME was set) and check Docker logs

### Enterprise scores are all "."
- Normal for most variants — Enterprise can only score mutations in proteins with 3D structure data (327 structures in the database)
- Verify structure files downloaded: check Step 3 in pipeline_timing.log

### Out of disk space
- Default is 500 GB gp3. For very large FASTQ files, increase `VolumeSize` in `sqs_consumer.py` line 126
- BAM files are automatically deleted after variant calling to free space

### GPU not detected
- Verify the AMI has NVIDIA drivers pre-installed
- The Docker container requires `--gpus all` flag (set in the user data script)

---

## Cost Optimization

- **On-demand g4dn.xlarge**: ~$0.526/hr. A 20-minute run costs ~$0.18 per sample
- **Spot instances**: Modify `sqs_consumer.py` to add `InstanceMarketOptions` for ~60-70% savings
- **Auto-terminate**: Instances shut down after pipeline completion (no idle costs)
- **Lambda**: Essentially free at low volume (1M free requests/month)
- **SQS**: Essentially free at low volume (1M free requests/month)
- **S3 storage**: Main cost for large FASTQ files and results

---

## Updating the Pipeline

1. Make changes to scripts in `~/genomics-pipeline/scripts/`
2. Rebuild and push:
   ```bash
   cd ~/genomics-pipeline
   ./build_and_push.sh --tag latest --region us-east-2
   ```
3. New jobs will automatically use the updated image (EC2 instances pull `latest` on launch)

To update the Lambda function:
```bash
cd ~/genomics-pipeline/lambda
zip -j /tmp/lambda_sqs_consumer.zip sqs_consumer.py
aws lambda update-function-code \
  --function-name genomics-pipeline-sqs-consumer \
  --zip-file fileb:///tmp/lambda_sqs_consumer.zip \
  --region us-east-2
```

---

## Infrastructure Setup (from scratch)

If you need to recreate everything:

```bash
# 1. Push Docker image to ECR
cd ~/genomics-pipeline
./build_and_push.sh --tag latest --region us-east-2

# 2. Create all AWS resources (SQS, Lambda, IAM, Security Group)
cd ~/genomics-pipeline/infra
AWS_REGION=us-east-2 ./setup_aws.sh
```

The setup script requires IAM permissions for: SQS, Lambda, IAM, EC2, VPC.

Note: `setup_aws.sh` references `AWS_REGION` as a Lambda environment variable, which is reserved by AWS. If creating the Lambda fails, use `PIPELINE_AWS_REGION` instead and update `sqs_consumer.py` line 31 accordingly (this has already been done in the current code).
