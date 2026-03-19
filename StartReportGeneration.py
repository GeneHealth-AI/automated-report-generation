# makes report generator, loads template, generates report and uploads it to appropriate S3 bucket
# takes in command line arguments

#!/usr/bin/env python3
import os
import boto3
import requests
import time
import json
import shutil
import logging
import datetime
from urllib.parse import urlparse
from ReportGenerator import Report
from json_report_writer import save_report_json

# Load environment variables from .env if present
if os.path.exists('.env'):
    with open('.env') as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                os.environ[key] = value

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("report_generation.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("ReportGeneration")

# Configuration: environment variable names
REPORT_TEMPLATE = "REPORT_TEMPLATE"
PURE_VCF = "PURE_VCF"
ANNOTATED_PATH = "ANNOTATED_PATH"
OUTPUT_PREFIX = "OUTPUT_PREFIX"
PATIENT_NAME = "PATIENT_NAME"
PATIENT_ID = "PATIENT_ID"
PROVIDER_NAME = "PROVIDER_NAME"

# Hard‑coded output destination
OUTPUT_BUCKET = "ghcompletedreports"

# GeneHealth API configuration
GENEHEALTH_API_BASE = "https://www.genehealth.ai/api/amazon"
GENEHEALTH_AUTH_HEADER = {
    "Content-Type": "application/json",
    "x-auth-amazon": "Ax1AAlZCCEdON7WXxZOkUDdGbC-0zuXnCGF6dwl7lor5l+Nukd2yh3HWtoNbo"
}


def notify_report_ready(report_s3_key: str) -> bool:
    """
    Notify the GeneHealth web app that a report is ready for viewing.
    Sends email to provider/member via the report-ready webhook.

    Args:
        report_s3_key: The S3 object key within the ghcompletedreports bucket
                       (e.g. "report-i-abc123-1710000000.html")
    Returns:
        True if notification succeeded, False otherwise.
    """
    url = f"{GENEHEALTH_API_BASE}/report-ready"
    payload = {"path": report_s3_key}
    try:
        response = requests.post(url, headers=GENEHEALTH_AUTH_HEADER, json=payload, timeout=15)
        if response.ok:
            logger.info(f"Report-ready notification sent successfully for: {report_s3_key}")
            return True
        else:
            logger.warning(f"Report-ready notification returned {response.status_code}: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Failed to send report-ready notification: {e}")
        return False


def notify_conversion_complete(vcf_s3_path: str) -> bool:
    """
    Notify the GeneHealth web app that a DNA conversion is complete.
    Sets the conversion flag in the database and emails provider/member.

    Args:
        vcf_s3_path: Path to the VCF file within the bucket
                     (e.g. "provider-uploads/sample.vcf")
    Returns:
        True if notification succeeded, False otherwise.
    """
    url = f"{GENEHEALTH_API_BASE}/conversion-complete"
    payload = {"path": vcf_s3_path}
    try:
        response = requests.post(url, headers=GENEHEALTH_AUTH_HEADER, json=payload, timeout=15)
        if response.ok:
            logger.info(f"Conversion-complete notification sent for: {vcf_s3_path}")
            return True
        else:
            logger.warning(f"Conversion-complete notification returned {response.status_code}: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Failed to send conversion-complete notification: {e}")
        return False


# AWS region (fallback to instance metadata if unset)
AWS_REGION = os.environ.get("AWS_REGION", None)

def download_s3(s3_uri, local_path):
    """Download a file from S3 to local disk."""
    parsed = urlparse(s3_uri)
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    s3 = boto3.client("s3", region_name=AWS_REGION)
    s3.download_file(bucket, key, local_path)
    print(f"Downloaded {s3_uri} → {local_path}")

def upload_s3(local_path, bucket, key):
    """Upload a local file to S3."""
    s3 = boto3.client("s3", region_name=AWS_REGION)
    s3.upload_file(local_path, bucket, key)
    print(f"Uploaded {local_path} → s3://{bucket}/{key}")

def get_instance_id():
    """Grab this EC2’s instance ID via IMDSv2."""
    try:
        token = requests.put(
            "http://169.254.169.254/latest/api/token",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"},
            timeout=2
        ).text
        return requests.get(
            "http://169.254.169.254/latest/meta-data/instance-id",
            headers={"X-aws-ec2-metadata-token": token},
            timeout=2
        ).text
    except Exception:
        logger.info("Failed to get EC2 instance ID, using 'local-instance'")
        return "local-instance"

def terminate_self(instance_id):
    """Tell EC2 to terminate itself."""
    if instance_id == "local-instance":
        logger.info("Local environment detected, skipping termination.")
        return
    try:
        ec2 = boto3.client("ec2", region_name=AWS_REGION)
        ec2.terminate_instances(InstanceIds=[instance_id])
        print(f"Termination requested for {instance_id}")
    except Exception as e:
        logger.error(f"Failed to terminate instance {instance_id}: {str(e)}")

def process_files(template, vcf_path, annotated_path, patient_name="EC2 Generated Patient", member_id="EC2-AUTO-001", provider_name="Automated System", gender="Unknown"):
    """
    Load template and run custom report generation with complete JSON output
    """
    start_time = time.time()
    try:
        # Load template from JSON file
        with open(template, 'r') as f:
            template_data = json.load(f)
        
        # Create report from template
        report = Report(template_data=template_data)
        
        # Set up report info
        report_title = template_data.get('name', template_data.get('focus', 'GeneHealth Report'))
        report_info = {
            "patient_name": patient_name,
            "member_id": member_id, 
            "provider_name": provider_name,
            "gender": gender,
            "title": report_title,
            "focus": template_data.get('focus', report_title)
        }
        
        logger.info(f"Starting report generation for patient: {report_info['patient_name']}, ID: {report_info['member_id']}")
        
        # Use split processing for large reports instead of truncation
        os.environ['USE_SPLIT_PROCESSING'] = 'TRUE'
        os.environ['LIMIT_PROTEIN_DATA'] = 'FALSE'  # Don't truncate proteins
        
        # Generate the report blocks with split processing for large blocks
        try:
            blocks = report.generate_report(
                annotated_path=annotated_path,
                vcf_path=vcf_path,
                family_history="",
                report_info=report_info,
                name="ec2_generated_report",
                output_format='json'  # This will generate JSON output
            )
        except Exception as e:
            error_msg = str(e)
            
            # Check if it's a token limit error
            if "too many total text bytes" in error_msg:
                logger.warning(f"Token limit exceeded. Attempting split processing approach.")
                
                # Set environment variable to use the split processing approach
                os.environ['FORCE_SPLIT_PROCESSING'] = 'TRUE'
                
                # Try again with split processing
                blocks = report.generate_report(
                    annotated_path=annotated_path,
                    vcf_path=vcf_path,
                    family_history="",
                    report_info=report_info,
                    name="ec2_generated_report",
                    output_format='json'
                )
            else:
                # If it's not a token limit error, re-raise
                logger.error(f"Error in report generation: {error_msg}")
                raise
        
        # Save the complete JSON report to /tmp
        json_output_path = "/tmp/complete_report.json"
        success_path = save_report_json(
            blocks=blocks,
            report_name="ec2_complete_report",
            report_info=report_info,
            output_format="single"
        )
        
        if success_path and os.path.exists(success_path):
            # Copy the JSON file to our expected output location
            shutil.copy(success_path, json_output_path)
            
            # GENERATE VISUAL HTML REPORT
            try:
                from scripts.visual_html_generator import generate_visual_html
                html_content = generate_visual_html(blocks, report_info)
                html_output_path = "/tmp/complete_report.html"
                with open(html_output_path, "w") as html_f:
                    html_f.write(html_content)
                logger.info(f"Visual HTML report generated at {html_output_path}")
            except Exception as html_err:
                logger.error(f"Failed to generate visual HTML report: {html_err}")
                html_output_path = None

            # RUN REVIEW AGENT (non-blocking — errors do not prevent report output)
            try:
                from review_agent import ReviewAgent
                reviewer = ReviewAgent(temperature=0.3)
                review_results = reviewer.run_full_review(blocks, html_content if html_output_path else "", report_info)

                if review_results["overall_passed"]:
                    logger.info("Report review PASSED")
                else:
                    logger.warning(f"Report review found issues: {len(review_results['critical_issues'])} critical, {review_results['total_issues']} total")
                    for issue in review_results["critical_issues"]:
                        logger.warning(f"  Critical issue: {issue}")

                # Save review results alongside the report
                review_output_path = "/tmp/report_review.json"
                with open(review_output_path, "w") as review_f:
                    json.dump(review_results, review_f, indent=2, default=str)
                logger.info(f"Review results saved to {review_output_path}")
            except Exception as review_err:
                logger.error(f"Review agent failed (non-blocking): {review_err}")

            elapsed_time = time.time() - start_time
            logger.info(f"Report generation successful for {report_info['member_id']}. Time taken: {elapsed_time:.2f} seconds")
            return json_output_path, html_output_path
        else:
            raise Exception("Failed to generate JSON report")
            
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(f"Error in report generation: {str(e)}. Time taken before error: {elapsed_time:.2f} seconds")
        
        # Fallback to basic text output with error info
        out_path = "./testing/output.txt"
        os.makedirs("./testing", exist_ok=True)
        with open(out_path, "w") as out_f:
            out_f.write(f"Report Generation Error: {str(e)}\n\n")
            out_f.write(f"Template: {template}\n")
            out_f.write(f"VCF: {vcf_path}\n")
            out_f.write(f"Annotated: {annotated_path}\n\n")
            
            # Try to include file contents for debugging
            for label, path in [("Template", template), ("VCF", vcf_path), ("Annotated", annotated_path)]:
                try:
                    with open(path, "r") as in_f:
                        content = in_f.read()
                        out_f.write(f"=== {label} Content ===\n")
                        out_f.write(content[:1000])  # First 1000 chars
                        if len(content) > 1000:
                            out_f.write(f"\n... (truncated, total length: {len(content)} chars)")
                        out_f.write("\n\n")
                except Exception as read_error:
                    out_f.write(f"Error reading {label} file {path}: {str(read_error)}\n\n")
        
        logger.error(f"Error output written to: {out_path}")
        return out_path

def test_report_generation(path=None, local=False, gender="Unknown"):
    pure_vcf = "s3://exomeinputbucket/SyntheticGenomesForSampleGeneration/synthetic_genome.vcf"
    report_template = "s3://gh-templates/cancer_template.json"
    output_prefix = "report-"
    
    rt_path, pvcf_path, anno_vcfpath = "./testing/input1", "./testing/input2", "./testing/input3"
    os.makedirs("./testing", exist_ok=True)
    
    if local:
        if not path:
            logger.error("Local mode requires a path to the annotated VCF file")
            return
        logger.info(f"Local mode enabled. Using file at: {path}")
        anno_vcfpath = path
        
        # Use our new pancreatic template for local testing
        pancreatic_template = "./testing/pancreatic_disease_template.json"
        if os.path.exists(pancreatic_template):
            logger.info(f"Loading local pancreatic template: {pancreatic_template}")
            rt_path = pancreatic_template
        else:
            logger.warning(f"Pancreatic template not found at {pancreatic_template}, falling back to default rt_path")
        
        # pvcf_path is assumed to exist in ./testing/ from previous runs
    else:
        # AWS mode
        annotated_vcf = path if path else "s3://exomeinputbucket/SyntheticGenomesForSampleGeneration/synthetic_genome_annotated.vcf"
        logger.info(f"AWS mode: Template={report_template}, VCF={pure_vcf}, Annotated={annotated_vcf}")
        
        # Download them
        download_start = time.time()
        download_s3(report_template, rt_path)
        download_s3(pure_vcf, pvcf_path)
        download_s3(annotated_vcf, anno_vcfpath)
        logger.info(f"Downloaded all input files in {time.time() - download_start:.2f} seconds")

    # 3) Process & write output (this will generate complete JSON)
    process_start = time.time()
    # Get dynamic info for test if available in environment, otherwise use defaults
    p_name = os.environ.get(PATIENT_NAME, "Karin Maberry")
    p_id = os.environ.get(PATIENT_ID, "GHID32226g115")
    provider = os.environ.get(PROVIDER_NAME, "Test Provider")
    patient_gender = os.environ.get("PATIENT_GENDER", 'Female')
    
    # Run processing
    pvcf_path = '/Users/samuelskolnick/Downloads/MaberryGenome.vcf'
    # Run processing
    results = process_files(rt_path, pvcf_path, '/Users/samuelskolnick/Downloads/Jan2026output.txt', patient_name=p_name, member_id=p_id, provider_name=provider, gender=patient_gender)
    
    if isinstance(results, tuple) and len(results) == 2:
        json_output, html_output = results
    else:
        # If it returned a single path (error case), handle it
        json_output = results
        html_output = None
        logger.warning(f"Report generation returned fallback output: {json_output}")
    
    logger.info(f"Report processing completed in {time.time() - process_start:.2f} seconds")

    # 4) Upload results
    upload_start = time.time()
    inst_id = get_instance_id()
    timestamp = int(time.time())
    
    # Upload JSON
    json_s3_key = f"{output_prefix}{inst_id}-{timestamp}.json"
    upload_s3(json_output, OUTPUT_BUCKET, json_s3_key)
    logger.info(f"JSON report uploaded to s3://{OUTPUT_BUCKET}/{json_s3_key}")

    # Upload HTML if it was generated
    html_s3_key = None
    if html_output and os.path.exists(html_output):
        html_s3_key = f"{output_prefix}{inst_id}-{timestamp}.html"
        upload_s3(html_output, OUTPUT_BUCKET, html_s3_key)
        logger.info(f"Visual HTML report uploaded to s3://{OUTPUT_BUCKET}/{html_s3_key}")

    logger.info(f"All reports uploaded in {time.time() - upload_start:.2f} seconds")

    # Notify GeneHealth web app that the report is ready
    if html_s3_key:
        notify_report_ready(html_s3_key)


def main():
    overall_start_time = time.time()
    logger.info("Starting report generation process")
    
    try:
        # 1) Read input S3 URIs
        report_template = os.environ.get(REPORT_TEMPLATE)
        pure_vcf = os.environ.get(PURE_VCF)
        annotated_vcf = os.environ.get(ANNOTATED_PATH)
        output_prefix = os.environ.get(OUTPUT_PREFIX, "report-")
        
        logger.info(f"Input parameters: Template={report_template}, VCF={pure_vcf}, Annotated={annotated_vcf}")
        
        if not all([report_template, pure_vcf, annotated_vcf]):
            error_msg = "Need REPORT_TEMPLATE, PURE_VCF, and ANNOTATED_PATH in environment variables"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        # 2) Download them
        download_start = time.time()
        rt_path, pvcf_path, anno_vcfpath = "/tmp/input1", "/tmp/input2", "/tmp/input3"
        download_s3(report_template, rt_path)
        download_s3(pure_vcf, pvcf_path)
        download_s3(annotated_vcf, anno_vcfpath)
        logger.info(f"Downloaded all input files in {time.time() - download_start:.2f} seconds")

        # 3) Process & write output (this will generate complete JSON and HTML)
        process_start = time.time()
        # Get dynamic info from environment
        p_name = os.environ.get(PATIENT_NAME, "EC2 Generated Patient")
        p_id = os.environ.get(PATIENT_ID, "EC2-AUTO-001")
        provider = os.environ.get(PROVIDER_NAME, "Automated System")
        patient_gender = os.environ.get("PATIENT_GENDER", "Female")
        
        json_output, html_output = process_files(rt_path, pvcf_path, anno_vcfpath, patient_name=p_name, member_id=p_id, provider_name=provider, gender=patient_gender)
        logger.info(f"Report processing completed in {time.time() - process_start:.2f} seconds")

        # 4) Upload results
        upload_start = time.time()
        inst_id = get_instance_id()
        timestamp = int(time.time())
        
        # Upload JSON
        json_s3_key = f"{output_prefix}{inst_id}-{timestamp}.json"
        upload_s3(json_output, OUTPUT_BUCKET, json_s3_key)
        logger.info(f"JSON report uploaded to s3://{OUTPUT_BUCKET}/{json_s3_key}")

        # Upload HTML if it was generated
        html_s3_key = None
        if html_output and os.path.exists(html_output):
            html_s3_key = f"{output_prefix}{inst_id}-{timestamp}.html"
            upload_s3(html_output, OUTPUT_BUCKET, html_s3_key)
            logger.info(f"Visual HTML report uploaded to s3://{OUTPUT_BUCKET}/{html_s3_key}")

        logger.info(f"All reports uploaded in {time.time() - upload_start:.2f} seconds")

        # 5) Notify GeneHealth web app that the report is ready
        if html_s3_key:
            notify_report_ready(html_s3_key)

        # Log overall completion time
        total_time = time.time() - overall_start_time
        logger.info(f"Total report generation process completed in {total_time:.2f} seconds")

        # 6) Terminate the instance
        logger.info(f"Requesting termination for instance {inst_id}")
        terminate_self(inst_id)
        
    except Exception as e:
        total_time = time.time() - overall_start_time
        logger.error(f"Fatal error in report generation process: {str(e)}")
        logger.error(f"Process failed after {total_time:.2f} seconds")
        raise

if __name__ == "__main__":
    test_report_generation(path='/Users/samuelskolnick/Downloads/Jan2026output.txt',local=True)
