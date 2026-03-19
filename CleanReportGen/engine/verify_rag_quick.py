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
logger = logging.getLogger("VerifyRAGQuick")

def verify():
    engine = BlockGenerationEngine()
    
    # Test data
    data = {
        "category": "Pancreatic Cancer",
        "mutations_summary": "PRSS1 p.Arg122His mutation",
        "patient_genes": ["PRSS1"],
        "mutations_data": "PRSS1 Arg122His mutation context.",
    }
    
    # Mocking search to return only 3 PMIDs for speed
    original_search = engine.rag.search_pmids
    engine.rag.search_pmids = lambda q, retmax=15: original_search(q, retmax=3)
    
    logger.info("Generating LITERATURE_EVIDENCE block (Quick Mode)...")
    try:
        block = engine.generate_block(BlockType.LITERATURE_EVIDENCE, data)
        print("\n--- GENERATED BLOCK ---")
        print(f"Title: {block.title}")
        print("Content:")
        print(json.dumps(block.content, indent=2))
        
    except Exception as e:
        logger.error(f"Verification failed: {e}")

if __name__ == "__main__":
    verify()
