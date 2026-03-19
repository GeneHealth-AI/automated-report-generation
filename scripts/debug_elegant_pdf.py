#!/usr/bin/env python3
"""
Debug script for the Elegant PDF Generator
"""

import json
import os
import traceback
from elegant_pdf_generator import ElegantPDFGenerator

def debug_json_structure():
    """Debug the JSON structure to understand the data format"""
    
    json_file = "reports_json/UpdatedErvinReport5.json"
    if os.path.exists(json_file):
        with open(json_file, 'r') as f:
            data = json.load(f)
        
        print("Debugging JSON Structure:")
        print("=" * 50)
        
        # Check blocks structure
        blocks = data.get('blocks', {})
        for block_name, block_data in blocks.items():
            print(f"\nBlock: {block_name}")
            print(f"  Title: {block_data.get('title', 'N/A')}")
            print(f"  Order: {block_data.get('order', 'N/A')}")
            
            content = block_data.get('content', '')
            print(f"  Content type: {type(content)}")
            print(f"  Content length: {len(str(content))}")
            
            # Try to parse the content
            if isinstance(content, str) and content.strip().startswith('```json'):
                print("  Content format: JSON in markdown")
                try:
                    import re
                    json_match = re.search(r'```json\s*\n(.*?)\n```', content, re.DOTALL)
                    if json_match:
                        parsed = json.loads(json_match.group(1))
                        print(f"  Parsed JSON keys: {list(parsed.keys())}")
                        
                        # Check for nested content
                        if 'content' in parsed and isinstance(parsed['content'], str):
                            print("  Has nested content string")
                except Exception as e:
                    print(f"  JSON parsing error: {e}")
            
            if block_name == 'executive_summary':
                print("  Detailed executive summary analysis:")
                try:
                    import re
                    json_match = re.search(r'```json\s*\n(.*?)\n```', content, re.DOTALL)
                    if json_match:
                        parsed = json.loads(json_match.group(1))
                        exec_summary = parsed.get('executive_summary', {})
                        print(f"    Executive summary keys: {list(exec_summary.keys())}")
                        
                        recs = exec_summary.get('primary_recommendations', [])
                        print(f"    Recommendations count: {len(recs)}")
                        if recs:
                            print(f"    First recommendation type: {type(recs[0])}")
                            if isinstance(recs[0], dict):
                                print(f"    First recommendation keys: {list(recs[0].keys())}")
                except Exception as e:
                    print(f"    Error analyzing executive summary: {e}")

def test_simple_pdf():
    """Test with a simplified approach"""
    
    json_file = "reports_json/UpdatedErvinReport5.json"
    if os.path.exists(json_file):
        with open(json_file, 'r') as f:
            data = json.load(f)
        
        try:
            print("Attempting to generate PDF...")
            generator = ElegantPDFGenerator("debug_test.pdf", data)
            generator.generate_pdf()
            print("✓ PDF generated successfully!")
            
        except Exception as e:
            print(f"✗ Error: {e}")
            print("Full traceback:")
            traceback.print_exc()

if __name__ == "__main__":
    debug_json_structure()
    print("\n" + "=" * 50)
    test_simple_pdf()