#!/usr/bin/env python3
import argparse
import logging
import json
import os
from core.coordinator import ReportCoordinator

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("CleanReportGen")

def main():
    parser = argparse.ArgumentParser(description="GeneHealth CleanReportGen - Modular Reporting System")
    parser.add_argument("--vcf",default='/Users/samuelskolnick/Downloads/MaberryGenome.vcf', help="Path to input VCF file")
    parser.add_argument("--template", default='/Users/samuelskolnick/CompleteGHReporting/GenerateAutomaticReport copy/CleanReportGen/ui/templates/default_template.json', help="Path to report template JSON")
    parser.add_argument("--patient-name", default="Karin Maberry", help="Patient name")
    parser.add_argument("--patient-id", default="GHID34526462", help="Patient ID")
    parser.add_argument("--output", default="final_report.json", help="Output path for JSON report")
    
    args = parser.parse_args()

    # 1. Setup Coordinator
    config = {
        "aws_region": os.environ.get("AWS_REGION", "us-east-1"),
        "model": "gemini-3-flash-preview"
    }
    coordinator = ReportCoordinator(config)

    # 2. Run Generation
    patient_info = {
        "patient_name": args.patient_name,
        "patient_id": args.patient_id
    }
    
    try:
        report_data = coordinator.run(args.vcf, args.template, patient_info)
        
        # 3. Save Output
        with open(args.output, 'w') as f:
            json.dump(report_data, f, indent=2)
            
        logger.info(f"✅ Report successfully generated and saved to {args.output}")
        
    except Exception as e:
        logger.error(f"❌ Report generation failed: {e}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    main()
