
import logging
import os
from ReportGenerator import Report

# Set up logging
logging.basicConfig(level=logging.INFO)

def test_mapping():
    r = Report()
    r._ensure_metadata_loaded()
    
    protein = "NP_002760.1"
    gene = r._extract_gene_name_from_protein(protein)
    print(f"Protein: {protein} -> Gene: {gene}")
    
    uniprot_acc = r._refseq_to_uniprot.get(protein)
    print(f"UniProt Acc: {uniprot_acc}")
    
    if uniprot_acc:
        info = r._uniprot_to_info.get(uniprot_acc)
        print(f"Info: {info}")

if __name__ == "__main__":
    test_mapping()
