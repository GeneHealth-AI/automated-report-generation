#!/usr/bin/env python3
import os
import json
import shutil
import logging
import time
import argparse
from dotenv import load_dotenv
from ReportGenerator import Report
from json_report_writer import save_report_json

# Load environment variables (like GEMINI_API_KEY)
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("LocalReportGeneration")

def process_local_files(template_path, annotated_path, vcf_path=None, patient_name="Local Patient", patient_id="LOCAL-001", provider_name="Local System"):
    """
    Load template and run report generation with local files.
    """
    start_time = time.time()
    try:
        # Load template from JSON file
        with open(template_path, 'r') as f:
            template_data = json.load(f)
        
        # Create report from template
        report = Report(template_data=template_data)
        
        # Set up report info
        report_info = {
            "patient_name": patient_name,
            "patient_id": patient_id, 
            "provider_name": provider_name
        }
        
        logger.info(f"Starting report generation for patient: {patient_name}, ID: {patient_id}")
        
        # Use split processing for large reports
        os.environ['USE_SPLIT_PROCESSING'] = 'TRUE'
        os.environ['LIMIT_PROTEIN_DATA'] = 'FALSE'
        
        # Generate the report blocks
        # If vcf_path is None, we'll try to use annotated_path as fallback or an empty vcf
        if not vcf_path or not os.path.exists(vcf_path):
            logger.warning("VCF path not provided or doesn't exist. Creating a dummy VCF.")
            vcf_path = "/tmp/dummy.vcf"
            with open(vcf_path, 'w') as f:
                f.write("#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n")

        blocks = report.generate_report(
            annotated_path=annotated_path,
            vcf_path=vcf_path,
            family_history="",
            report_info=report_info,
            name="local_generated_report",
            output_format='json'
        )
        
        # Save the complete JSON report
        json_output_path = "reports_json/local_complete_report.json"
        os.makedirs("reports_json", exist_ok=True)
        
        success_path = save_report_json(
            blocks=blocks,
            report_name="local_complete_report",
            report_info=report_info,
            output_format="single"
        )
        
        if success_path and os.path.exists(success_path):
            if os.path.abspath(success_path) != os.path.abspath(json_output_path):
                shutil.copy(success_path, json_output_path)
            else:
                logger.info(f"JSON report already at {json_output_path}")
            
            # GENERATE VISUAL HTML REPORT
            try:
                from scripts.visual_html_generator import generate_visual_html
                html_content = generate_visual_html(blocks, report_info)
                html_output_path = "reports_html/local_complete_report.html"
                os.makedirs("reports_html", exist_ok=True)
                with open(html_output_path, "w") as html_f:
                    html_f.write(html_content)
                logger.info(f"Visual HTML report generated at {html_output_path}")
            except Exception as html_err:
                logger.error(f"Failed to generate visual HTML report: {html_err}")
                html_output_path = None

            elapsed_time = time.time() - start_time
            logger.info(f"Report generation successful. Total time: {elapsed_time:.2f} seconds")
            return json_output_path, html_output_path
        else:
            raise Exception("Failed to generate JSON report")
            
    except Exception as e:
        logger.error(f"Error in report generation: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return None, None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a GeneHealth report from local files.")
    parser.add_argument("--template", required=True, help="Path to the report template JSON")
    parser.add_argument("--annotated", required=True, help="Path to the annotated variants file (e.g. Jan2026output.txt)")
    parser.add_argument("--vcf", help="Path to the raw VCF file (optional)")
    parser.add_argument("--name", default="Karin Maberry", help="Patient name")
    parser.add_argument("--id", default="JAN-2026-001", help="Patient ID")
    parser.add_argument("--provider", default="N/A", help="Provider name")
    
    args = parser.parse_args()
    
    json_out, html_out = process_local_files(
        args.template, 
        args.annotated, 
        vcf_path=args.vcf, 
        patient_name=args.name, 
        patient_id=args.id, 
        provider_name=args.provider
    )
    
    if html_out:
        print(f"\nSUCCESS! HTML report available at: {os.path.abspath(html_out)}")
        # Also copy to /tmp/complete_report.html for consistency with user's previous requests
        shutil.copy(html_out, "/tmp/complete_report.html")
        print(f"Copied to: /tmp/complete_report.html")
    else:
        print("\nFailed to generate report.")
