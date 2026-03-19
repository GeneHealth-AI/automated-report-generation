import os
import logging
from pubmed_searcher import PubMedSearcher

# Setup logging
logging.basicConfig(level=logging.INFO)

def test_pubmed_searcher():
    # Use a dummy email as required by NCBI
    searcher = PubMedSearcher(email="test@example.com")
    
    query = "BRCA1 breast cancer clinical significance"
    print(f"Testing search for: {query}")
    
    # Test getting evidence
    evidence = searcher.get_evidence(query, retmax=2)
    
    print("\n--- Evidence Result ---")
    print(evidence)
    print("--- End Evidence ---")
    
    if "PMID:" in evidence and "TITLE:" in evidence:
        print("\n✅ PubMedSearcher verification successful!")
    else:
        print("\n❌ PubMedSearcher verification failed or no results found.")

if __name__ == "__main__":
    test_pubmed_searcher()
