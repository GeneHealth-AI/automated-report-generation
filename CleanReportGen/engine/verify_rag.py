import os
import sys
import logging
import json

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from engine.generator import BlockGenerationEngine
from data.models import BlockType

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VerifyRAG")

def verify():
    engine = BlockGenerationEngine()
    
    # Test data
    data = {
        "category": "Pancreatic Cancer",
        "mutations_summary": "PRSS1 p.Arg122His mutation",
        "patient_genes": ["PRSS1"],
        "mutations_data": "PRSS1 Arg122His is a well-known gain-of-function mutation associated with hereditary pancreatitis.",
    }
    
    logger.info("Generating LITERATURE_EVIDENCE block...")
    try:
        block = engine.generate_block(BlockType.LITERATURE_EVIDENCE, data)
        print("\n--- GENERATED BLOCK ---")
        print(f"Title: {block.title}")
        print(f"Order: {block.order}")
        print("Content:")
        print(json.dumps(block.content, indent=2))
        
        if "gene_specific_findings" in block.content:
             print("\n✅ Successfully generated structured evidence.")
        else:
             print("\n⚠️ Block content might not be as expected.")
             
    except Exception as e:
        logger.error(f"Verification failed: {e}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    verify()
