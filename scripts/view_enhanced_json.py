#!/usr/bin/env python3
"""
Utility to view the protein mutations added to enhanced JSON files.
"""

import json
import sys

def view_protein_mutations(json_file):
    """View protein mutations in an enhanced JSON file."""
    
    try:
        with open(json_file, 'r') as f:
            data = json.load(f)
        
        # Check if protein_mutations block exists
        if 'protein_mutations' not in data.get('blocks', {}):
            print(f"No protein_mutations block found in {json_file}")
            return
        
        # Parse the protein mutations content
        mutations_content = json.loads(data['blocks']['protein_mutations']['content'])
        protein_mutations = mutations_content.get('protein_mutations', {})
        
        print(f"Protein mutations in {json_file}:")
        print(f"Total proteins: {len(protein_mutations)}")
        print("-" * 80)
        
        for protein, mutation in sorted(protein_mutations.items()):
            print(f"{protein:<15} : {mutation}")
            
    except Exception as e:
        print(f"Error reading {json_file}: {e}")

def main():
    if len(sys.argv) > 1:
        json_file = sys.argv[1]
    else:
        json_file = 'ADHD_Report2_enhanced.json'
    
    view_protein_mutations(json_file)

if __name__ == '__main__':
    main()