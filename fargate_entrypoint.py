#!/usr/bin/env python3
"""
Fargate entrypoint for report generation called by Lambda function.
Expects environment variables: ANNOTATED_VCF_PATH, VCF_PATH, TEMPLATE, NAME, ID, PROVIDER

This entrypoint now uses the Clean Professional PDF Generator for creating
high-quality medical reports with:
- No CSV formatting issues or artifacts
- Clean, professional medical report styling
- Proper JSON parsing without raw text output
- Readable tables without overlapping content
- Optimized file sizes with complete information
Falls back to basic PDF generation if needed.
"""

import os
import boto3
import json
import time
import logging
import traceback
from urllib.parse import urlparse
from ReportGenerator import Report
from json_report_writer import save_report_json
from finalpdfgen import PDFReportGenerator
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("FargateReportGeneration")

# Default output S3 bucket
DEFAULT_OUTPUT_BUCKET = "ghcompletedreports"

# GeneHealth API configuration
GENEHEALTH_API_BASE = "https://www.genehealth.ai/api/amazon"
GENEHEALTH_AUTH_HEADER = {
    "Content-Type": "application/json",
    "x-auth-amazon": "Ax1AAlZCCEdON7WXxZOkUDdGbC-0zuXnCGF6dwl7lor5l+Nukd2yh3HWtoNbo"
}

import requests as _requests

def notify_report_ready(report_s3_key: str) -> bool:
    """Notify the GeneHealth web app that a report is ready for viewing."""
    url = f"{GENEHEALTH_API_BASE}/report-ready"
    payload = {"path": report_s3_key}
    try:
        response = _requests.post(url, headers=GENEHEALTH_AUTH_HEADER, json=payload, timeout=15)
        if response.ok:
            logger.info(f"Report-ready notification sent successfully for: {report_s3_key}")
            return True
        else:
            logger.warning(f"Report-ready notification returned {response.status_code}: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Failed to send report-ready notification: {e}")
        return False

def download_s3_file(s3_uri, local_path):
    """Download a file from S3 to local disk, or copy if it's a local file."""
    try:
        parsed = urlparse(s3_uri)
        
        # Handle local files for testing
        if parsed.scheme == 'file':
            import shutil
            source_path = parsed.path
            shutil.copy2(source_path, local_path)
            logger.info(f"Copied local file {source_path} → {local_path}")
            return True
        
        # Handle S3 files
        elif parsed.scheme == 's3':
            bucket = parsed.netloc
            key = parsed.path.lstrip("/")
            
            s3 = boto3.client("s3")
            s3.download_file(bucket, key, local_path)
            logger.info(f"Downloaded {s3_uri} → {local_path}")
            return True
        
        else:
            logger.error(f"Unsupported URI scheme: {parsed.scheme}")
            return False
            
    except Exception as e:
        logger.error(f"Failed to download {s3_uri}: {str(e)}")
        return False

def upload_s3_file(local_path, bucket, key):
    """Upload a local file to S3."""
    try:
        s3 = boto3.client("s3")
        s3.upload_file(local_path, bucket, key)
        logger.info(f"Uploaded {local_path} → s3://{bucket}/{key}")
        return True
    except Exception as e:
        logger.error(f"Failed to upload {local_path} to s3://{bucket}/{key}: {str(e)}")
        return False

def generate_report(template, vcf_path, annotated_vcf_path, name, patient_id, provider):
    """Generate the genetic report using the provided inputs."""
    try:
        logger.info("🔧 DEBUG: Starting generate_report function")
        
        logger.info("🔧 DEBUG: Loading template from JSON file")
        # Load template from JSON file
        template_data = json.loads(template)
        logger.info("✅ DEBUG: Template loaded successfully")
        
        logger.info("🔧 DEBUG: Creating Report instance")
        # Create report from template
        try:
            report = Report(template_data=template_data)
            logger.info("✅ DEBUG: Report instance created successfully")
        except Exception as e:
            logger.error(f"❌ DEBUG: Error creating Report instance: {str(e)}")
            logger.error(f"❌ DEBUG: Report creation traceback: {traceback.format_exc()}")
            raise
        
        # Set up report info from Lambda parameters
        gender = os.environ.get('PATIENT_GENDER', 'Unknown')
        report_info = {
            "patient_name": name,
            "member_id": patient_id,
            "provider_name": provider,
            "gender": gender
        }
        
        logger.info(f"Starting report generation for patient: {name}, ID: {patient_id}, Provider: {provider}")
        
        # Configure for optimal processing
        os.environ['USE_SPLIT_PROCESSING'] = 'TRUE'
        os.environ['LIMIT_PROTEIN_DATA'] = 'FALSE'
        
        logger.info("🔧 DEBUG: About to call report.generate_report()")
        # Generate the report blocks
        try:
            blocks = report.generate_report(
                annotated_path=annotated_vcf_path,
                vcf_path=vcf_path,
                report_info=report_info,
                name=f"report_{patient_id}",
                output_format='json',
                family_history=''
            )
    
            logger.info("✅ DEBUG: report.generate_report() completed successfully")
        except Exception as e:
            logger.error(f"❌ DEBUG: Error in report.generate_report(): {str(e)}")
            logger.error(f"❌ DEBUG: generate_report traceback: {traceback.format_exc()}")
            raise
        
        # Save JSON report
        json_output_path = f"/tmp/report_{patient_id}.json"
        logger.info("Generating JSON report...")
        json_success = save_report_json(
            blocks=blocks,
            report_name=f"report_{patient_id}",
            report_info=report_info,
            output_format="single"
        )
        
        if json_success:
            logger.info(f"JSON report saved successfully: {json_success}")
            # Update json_output_path to the actual path returned
            json_output_path = json_success
        else:
            logger.error("Failed to generate JSON report")
            # Try to continue with PDF generation anyway if we have blocks
        
        
        
        # Generate PDF using finalpdfgen.py (PDFReportGenerator)
        pdf_file_path = f'/tmp/{patient_id}_Report.pdf'
        logger.info(f"Starting PDF generation using finalpdfgen.PDFReportGenerator...")
        logger.info(f"Input JSON: {json_output_path}")
        logger.info(f"Output PDF: {pdf_file_path}")

        pdf_success = False
        try:
            # Load the JSON report data
            with open(json_output_path, 'r', encoding='utf-8') as f:
                report_data = json.load(f)
            
            logger.info("JSON data loaded successfully, creating PDFReportGenerator...")
            
            # Create PDF generator from finalpdfgen.py
            generator = PDFReportGenerator(pdf_file_path, report_data)
            
            # Generate the PDF with enhanced JSON output
            logger.info("Generating PDF report with enhanced JSON output...")
            generator.generate_report(save_enhanced_json=True)
            
            # Verify PDF was created successfully
            if os.path.exists(pdf_file_path) and os.path.getsize(pdf_file_path) > 0:
                pdf_success = True
                file_size = os.path.getsize(pdf_file_path)
                logger.info(f"✅ PDF generated successfully using finalpdfgen.py: {pdf_file_path} ({file_size:,} bytes)")
                
                # Check if enhanced JSON was also created
                enhanced_json_path = pdf_file_path.replace('.pdf', '_enhanced.json')
                if os.path.exists(enhanced_json_path):
                    logger.info(f"✅ Enhanced JSON also created: {enhanced_json_path}")
            else:
                logger.error("❌ PDF file was not created or is empty")
                
        except json.JSONDecodeError as e:
            logger.error(f"❌ Error: Could not decode JSON from the file {json_output_path}. Details: {e}")
        except Exception as e:
            logger.error(f"❌ An unexpected error occurred during PDF generation: {e}")
            logger.error(f"❌ PDF generation traceback: {traceback.format_exc()}")
        
        # Return list of successfully generated files (prioritizing PDF from finalpdfgen.py)
        generated_files = []
        
        # Add PDF first (primary output from finalpdfgen.py)
        if pdf_success and os.path.exists(pdf_file_path):
            generated_files.append(pdf_file_path)
            logger.info(f"✅ Primary output: PDF from finalpdfgen.py - {pdf_file_path}")
        
        # Add JSON as secondary output
        if json_success and os.path.exists(json_success):
            generated_files.append(json_success)
            logger.info(f"✅ Secondary output: JSON report - {json_success}")
        
        # Check for enhanced JSON from finalpdfgen.py
        enhanced_json_path = pdf_file_path.replace('.pdf', '_enhanced.json')
        if os.path.exists(enhanced_json_path):
            generated_files.append(enhanced_json_path)
            logger.info(f"✅ Additional output: Enhanced JSON from finalpdfgen.py - {enhanced_json_path}")
            
        # NEW: GENERATE VISUAL HTML REPORT
        try:
            try:
                from visual_html_generator import generate_visual_html
            except ImportError:
                from scripts.visual_html_generator import generate_visual_html
            logger.info("Generating Visual HTML report...")
            report_info["focus"] = report_info.get("focus", "Precision Genetics")
            html_content = generate_visual_html(blocks, report_info)
            html_file_path = f'/tmp/{patient_id}_Report.html'
            with open(html_file_path, "w") as html_f:
                html_f.write(html_content)
            
            if os.path.exists(html_file_path) and os.path.getsize(html_file_path) > 0:
                generated_files.append(html_file_path)
                logger.info(f"✅ Additional output: Visual HTML report - {html_file_path}")

                # Run review agent on the generated report (non-blocking)
                try:
                    from review_agent import ReviewAgent
                    reviewer = ReviewAgent(temperature=0.3)
                    review_results = reviewer.run_full_review(blocks, html_content, report_info)
                    if review_results["overall_passed"]:
                        logger.info("Report review PASSED")
                    else:
                        logger.warning(f"Report review found {len(review_results['critical_issues'])} critical issues")
                    # Save review results
                    review_path = f'/tmp/{patient_id}_review.json'
                    with open(review_path, 'w') as rf:
                        json.dump(review_results, rf, indent=2, default=str)
                    generated_files.append(review_path)
                    logger.info(f"✅ Review results saved: {review_path}")
                except Exception as review_err:
                    logger.error(f"Review agent failed (non-blocking): {review_err}")

        except Exception as html_err:
            logger.error(f"❌ Failed to generate visual HTML report: {html_err}")
            logger.error(traceback.format_exc())
            
        if not generated_files:
            logger.error("❌ No reports were generated successfully")
            return []  # Return empty list instead of None
            
        logger.info(f"🎉 Report generation completed successfully!")
        logger.info(f"📄 Generated {len(generated_files)} file(s) using finalpdfgen.py:")
        for i, file_path in enumerate(generated_files, 1):
            file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
            logger.info(f"   {i}. {file_path} ({file_size:,} bytes)")
        
        return generated_files
        
    except Exception as e:
        logger.error(f"Error in report generation: {str(e)}")
        logger.error(f"❌ DEBUG: Exception type in generate_report: {type(e).__name__}")
        logger.error(f"❌ DEBUG: Full traceback in generate_report: {traceback.format_exc()}")
        
        # Check if this is the proxies error
        if "proxies" in str(e):
            logger.error("🚨 DEBUG: FOUND THE PROXIES ERROR! It's coming from generate_report function")
            logger.error(f"🚨 DEBUG: Proxies error in generate_report: {str(e)}")
        
        raise

def main():
    """Main entrypoint for Fargate container."""
    start_time = time.time()
    logger.info("Starting Fargate report generation process CHECKME")
    
    try:
        # Get environment variables from Lambda
        annotated_vcf_path = os.environ.get('ANNOTATED_VCF_PATH')
        vcf_path = os.environ.get('VCF_PATH')
        template = os.environ.get('TEMPLATE')
        template_path = os.environ.get('TEMPLATE_PATH')
        name = os.environ.get('NAME')
        patient_id = os.environ.get('ID')
        provider = os.environ.get('PROVIDER')
        output_bucket = os.environ.get('OUTPUT_S3_BUCKET')
        output_filename = os.environ.get('OUTPUT_FILENAME')
        
        # Validate required parameters
        # Either TEMPLATE or TEMPLATE_PATH must be provided
        if not template and not template_path:
            raise ValueError("Missing required environment variables: TEMPLATE or TEMPLATE_PATH")
            
        required_params = {
            'ANNOTATED_VCF_PATH': annotated_vcf_path,
            'VCF_PATH': vcf_path,
            'NAME': name,
            'ID': patient_id,
            'PROVIDER': provider,
            'OUTPUT_S3_BUCKET': output_bucket
        }
        
        missing_params = [k for k, v in required_params.items() if not v]
        if missing_params:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_params)}")

        # Download template if only path is provided
        if not template and template_path:
            local_template_path = "/tmp/template.json"
            logger.info(f"Downloading template from {template_path}...")
            if download_s3_file(template_path, local_template_path):
                with open(local_template_path, 'r') as f:
                    template = f.read()
            else:
                raise Exception(f"Failed to download template from {template_path}")
        
        logger.info(f"Processing report for {name} (ID: {patient_id}) from {provider}")
        
        # Download input files from S3
        local_vcf = "/tmp/input.vcf"
        local_annotated = "/tmp/annotated.vcf"

        downloads = [
            (vcf_path, local_vcf),
            (annotated_vcf_path, local_annotated)
        ]

        for s3_uri, local_path in downloads:
            if not download_s3_file(s3_uri, local_path):
                raise Exception(f"Failed to download {s3_uri}")

        # Check if the annotated file has usable scores (not all '.')
        # If not, try to find enterprise_scores.txt in the same S3 directory
        try:
            has_scores = False
            with open(local_annotated, 'r') as f:
                for i, line in enumerate(f):
                    if i > 100:
                        break
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split('\t')
                    if len(parts) >= 6 and parts[5].strip() not in ('.', '', 'Disease_Score'):
                        try:
                            float(parts[5].strip())
                            has_scores = True
                            break
                        except ValueError:
                            pass
            if not has_scores:
                # Try enterprise_scores.txt from the same directory
                from urllib.parse import urlparse
                parsed = urlparse(annotated_vcf_path)
                if parsed.scheme == 's3':
                    s3_dir = '/'.join(parsed.path.lstrip('/').split('/')[:-1])
                    scores_uri = f"s3://{parsed.netloc}/{s3_dir}/enterprise_scores.txt"
                    local_scores = "/tmp/enterprise_scores.txt"
                    logger.info(f"No scores found in {annotated_vcf_path}, trying {scores_uri}")
                    if download_s3_file(scores_uri, local_scores):
                        # Merge: use enterprise_scores.txt as the annotated input
                        local_annotated = local_scores
                        logger.info(f"Using enterprise_scores.txt as annotated input (has actual disease scores)")
                    else:
                        logger.warning("enterprise_scores.txt not found either — report will have limited genetic data")
        except Exception as score_check_err:
            logger.warning(f"Score check failed (non-blocking): {score_check_err}")
        
        # Generate reports
        logger.info("Starting report generation...")
        report_files = generate_report(
            template, local_vcf, local_annotated,
            name, patient_id, provider
        )
        
        # Check if report generation was successful
        if not report_files:
            raise Exception("No report files were generated")
        
        # Upload results to S3
        timestamp = int(time.time())
        uploaded_files = []
        
        for file_path in report_files:
            if os.path.exists(file_path):
                # Determine file type for S3 key
                if file_path.endswith('.pdf'):
                    file_extension = 'pdf'
                elif file_path.endswith('.json'):
                    file_extension = 'json'
                elif file_path.endswith('.html'):
                    file_extension = 'html'
                else:
                    file_extension = os.path.splitext(file_path)[1].lstrip('.') or 'unknown'
                
                # Generate proper S3 key based on file type and patient info
                # If output_filename looks like a variable name, generate a proper filename
                if output_filename == 'output_filename' or not output_filename or output_filename.startswith('${'):
                    # Generate a proper filename
                    base_name = f"{patient_id}_{name.replace(' ', '_')}_report_{timestamp}"
                    s3_key = f"{base_name}.{file_extension}"
                else:
                    # Use provided filename, but ensure it has the right extension
                    if not output_filename.endswith(f'.{file_extension}'):
                        s3_key = f"{output_filename}.{file_extension}"
                    else:
                        s3_key = output_filename
                if upload_s3_file(file_path, output_bucket, s3_key):
                    uploaded_files.append(f"s3://{output_bucket}/{s3_key}")
                    logger.info(f"Successfully uploaded {file_path} to s3://{output_bucket}/{s3_key}")
                else:
                    logger.error(f"Failed to upload {file_path} to S3")
            else:
                logger.warning(f"Generated file does not exist: {file_path}")
        
        # Notify GeneHealth web app that the HTML report is ready
        html_s3_keys = [f for f in uploaded_files if f.endswith('.html')]
        for html_uri in html_s3_keys:
            # Extract just the S3 key (filename) from the full URI
            html_key = html_uri.split(f"s3://{output_bucket}/")[-1]
            notify_report_ready(html_key)

        total_time = time.time() - start_time
        logger.info(f"Report generation completed successfully in {total_time:.2f} seconds")
        logger.info(f"Generated files: {', '.join(uploaded_files)}")

        # Return success status
        return {
            'statusCode': 200,
            'body': {
                'message': 'Report generation completed successfully',
                'patient_id': patient_id,
                'files_generated': uploaded_files,
                'processing_time': total_time
            }
        }
        
    except Exception as e:
        total_time = time.time() - start_time
        logger.error(f"Fatal error in report generation: {str(e)}")
        logger.error(f"❌ DEBUG: Exception type: {type(e).__name__}")
        logger.error(f"❌ DEBUG: Full traceback: {traceback.format_exc()}")
        
        # Check if this is the proxies error we're looking for
        if "proxies" in str(e):
            logger.error("🚨 DEBUG: FOUND THE PROXIES ERROR! It's coming from the main process")
            logger.error(f"🚨 DEBUG: Proxies error details: {str(e)}")
            
            # Log environment variables that might be causing this
            proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'NO_PROXY', 'no_proxy']
            for var in proxy_vars:
                value = os.environ.get(var)
                if value:
                    logger.error(f"🚨 DEBUG: Found proxy env var {var}={value}")
        
        logger.error(f"Process failed after {total_time:.2f} seconds")
        
        # Return error status
        return {
            'statusCode': 500,
            'body': {
                'error': str(e),
                'patient_id': patient_id if 'patient_id' in locals() else 'unknown',
                'processing_time': total_time
            }
        }

if __name__ == "__main__":
    result = main()
    # Exit with appropriate code
    exit(0 if result['statusCode'] == 200 else 1)