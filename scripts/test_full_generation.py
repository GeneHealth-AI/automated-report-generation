import os
import json
import logging
from ReportGenerator import Report, BlockType
from scripts.visual_html_generator import generate_visual_html

logging.basicConfig(level=logging.INFO)

def test_generation():
    print("Testing Report Generation Logic...")
    
    # 1. Test template loading with 'sections'
    template_data = {
        "focus": "Type 1 Diabetes and Pancreatic Health",
        "sections": [
            {"type": "introduction"},
            {"type": "executive_summary"},
            {"type": "literature_evidence"},
            {"type": "conclusion"}
        ]
    }
    
    print("Creating Report instance with template...")
    report = Report(template_data=template_data)
    
    print(f"Blocks loaded: {[b.value for b in report.blocks]}")
    
    # Verify GWAS is not there
    if BlockType.GWAS_ANALYSIS in report.blocks:
        print("FAIL: GWAS_ANALYSIS still present in blocks!")
    else:
        print("PASS: GWAS_ANALYSIS excluded as expected.")
        
    # Verify Conclusion is there
    if BlockType.CONCLUSION in report.blocks:
        print("PASS: CONCLUSION present in blocks.")
    else:
        print("FAIL: CONCLUSION missing from blocks!")

    # 2. Mock some data and generate
    mock_data = {
        "patient_name": "Test Patient",
        "patient_id": "P123",
        "provider_name": "GeneHealth",
        "VARIANTS": "BRCA2 mutations",
        "risk_variants": [],
        "protective_variants": []
    }
    
    # We can't easily call generate_report without AWS/Gemini environment setup
    # But we already fixed the logic. Let's just mock the ReportBlock output
    # to test the visual_html_generator with the new conclusion block.
    
    from report_blocks import ReportBlock
    
    blocks = [
        ReportBlock(
            block_type=BlockType.INTRODUCTION,
            title="Introduction",
            content="This is a test introduction.",
            template="introduction_block.html",
            order=1
        ),
        ReportBlock(
            block_type=BlockType.CONCLUSION,
            title="Conclusion",
            content={
                "summary": "Overall synthesis of findings.",
                "next_steps": [
                    {"action": "Genetic Counseling", "rationale": "Recommended for high-risk variants.", "priority": "High"},
                    {"action": "Follow-up MRI", "rationale": "Standard protocol.", "priority": "Medium"}
                ]
            },
            template="conclusion_block.html",
            order=10
        )
    ]
    
    report_info = {
        "patient_name": "Test Patient",
        "patient_id": "P123",
        "provider_name": "GeneHealth"
    }
    
    print("Generating visual HTML to test templates...")
    html = generate_visual_html(blocks, report_info)
    
    output_path = "reports_html/test_full_gen.html"
    os.makedirs("reports_html", exist_ok=True)
    with open(output_path, "w") as f:
        f.write(html)
    
    print(f"Test HTML saved to {output_path}")
    print("Please verify the Conclusion block appears at the end of the report.")

if __name__ == "__main__":
    test_generation()
