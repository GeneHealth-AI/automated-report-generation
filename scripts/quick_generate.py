import json
from scripts.visual_html_generator import generate_visual_html
from report_blocks import BlockType, ReportBlock

def blocks_from_json(json_data):
    blocks = []
    for key, data in json_data.items():
        if key in ["metadata", "mutations"]:
            continue
            
        try:
            # Map the JSON key to the Enum type
            block_type_mapped_name = key.upper()
            if block_type_mapped_name == "PROTECTIVE_FACTORS":
                block_type = BlockType.RISK_ASSESSMENT
            elif block_type_mapped_name == "CLINICAL_SYNTHESIS":
                block_type = BlockType.EXECUTIVE_SUMMARY
            else:
                block_type = getattr(BlockType, block_type_mapped_name)
                
            block = ReportBlock(
                block_type=block_type,
                title=block_type.value.replace("_", " ").title(),
                content=data,
                template=f"{block_type.value}_block.html",
                order=0 # visually generated order later
            )
            blocks.append(block)
        except AttributeError:
            continue
    return blocks

with open('/tmp/complete_report.json', 'r') as f:
    data = json.load(f)

blocks = blocks_from_json(data)
html = generate_visual_html(blocks, {"patient_name": "Testing", "member_id": "123", "focus": "Pancreatic Cancer"})

with open('report-styling-test.html', 'w') as f:
    f.write(html)
print("Saved report-styling-test.html")
