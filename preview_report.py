"""
Quick preview script: Re-renders an existing JSON report into HTML
using the updated templates, without calling the LLM.

Usage:
    python preview_report.py                          # uses latest ec2 report
    python preview_report.py reports_json/my_report.json
"""

import sys
import json
import os

# Ensure we can import from project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from report_blocks import BlockType, ReportBlock
from scripts.visual_html_generator import generate_visual_html


def load_blocks_from_json(json_path: str) -> tuple[list[ReportBlock], dict]:
    """Load ReportBlock objects from a saved JSON report."""
    with open(json_path, "r") as f:
        report_data = json.load(f)

    metadata = report_data.get("report_metadata", {})
    blocks_data = report_data.get("blocks", {})

    blocks = []
    for block_key, block_info in blocks_data.items():
        try:
            block_type = BlockType(block_key)
        except ValueError:
            print(f"  Skipping unknown block type: {block_key}")
            continue

        block = ReportBlock(
            block_type=block_type,
            title=block_info.get("title", block_key.replace("_", " ").title()),
            content=block_info.get("content", {}),
            template=block_info.get("template", f"{block_key}_block.html"),
            order=block_info.get("order", 99),
            is_required=block_info.get("is_required", True),
            user_customizable=block_info.get("user_customizable", True),
        )
        blocks.append(block)

    report_info = {
        "patient_name": metadata.get("patient_name", "Preview Patient"),
        "member_id": metadata.get("patient_id", "PREVIEW-001"),
        "provider_name": metadata.get("provider_name", "Preview Provider"),
        "focus": metadata.get("focus", "Genetic Risk Report"),
        "title": metadata.get("focus", "Genetic Risk Report"),
    }

    return blocks, report_info


def main():
    # Default to the most recent ec2 report
    json_path = sys.argv[1] if len(sys.argv) > 1 else "reports_json/ec2_complete_report.json"

    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found")
        print("Available reports:")
        for f in sorted(os.listdir("reports_json")):
            if f.endswith(".json"):
                print(f"  reports_json/{f}")
        return

    print(f"Loading report from: {json_path}")
    blocks, report_info = load_blocks_from_json(json_path)
    print(f"Loaded {len(blocks)} blocks: {[b.block_type.value for b in blocks]}")

    print("Generating HTML with updated templates...")
    html_content = generate_visual_html(blocks, report_info)

    output_path = "preview_report.html"
    with open(output_path, "w") as f:
        f.write(html_content)

    print(f"\nReport preview saved to: {output_path}")
    print(f"Open it with: open {output_path}")


if __name__ == "__main__":
    main()
