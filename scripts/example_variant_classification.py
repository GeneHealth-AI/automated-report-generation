#!/usr/bin/env python3
"""
Example script demonstrating the variant classification system in ReportGenerator_clean.py

This script shows how to:
1. Initialize the report generator with variant classification
2. Add/remove protective variants
3. Classify variants based on the protective list and pathogenicity scores
4. Generate reports with variant classifications
"""

from ReportGenerator_clean import Report, VariantClassification
import json

def main():
    print("=== Variant Classification System Demo ===\n")
    
    # Initialize report generator
    report = Report()
    
    # Show current protective variants
    print("1. Current Protective Variants:")
    print(report.get_protective_variants_summary())
    
    # Add a new protective variant
    print("2. Adding a new protective variant...")
    success = report.add_protective_variant(
        rsid="rs1800562",
        gene="HFE",
        description="HFE C282Y - protective against iron deficiency when heterozygous",
        condition="Iron deficiency protection",
        evidence="Heterozygous carriers have better iron absorption"
    )
    print(f"Added successfully: {success}\n")
    
    # Show updated list
    print("3. Updated Protective Variants List:")
    print(report.get_protective_variants_summary())
    
    # Example variant classification
    print("4. Example Variant Classifications:")
    
    # Test pathogenic variant (high score)
    pathogenic_variant = report.classify_variant(
        rsid="rs123456789",
        gene="BRCA1",
        score=0.95,
        position="185",
        ref_aa="C",
        alt_aa="T",
        mutation_description="C185T"
    )
    print(f"High score variant: {pathogenic_variant.classification.value} - {pathogenic_variant.reasoning}")
    
    # Test protective variant (in list)
    protective_variant = report.classify_variant(
        rsid="rs334",  # This is in our protective list
        gene="HBB",
        score=0.3,
        position="6",
        ref_aa="E",
        alt_aa="V",
        mutation_description="E6V"
    )
    print(f"Listed protective variant: {protective_variant.classification.value} - {protective_variant.reasoning}")
    
    # Test neutral variant (low score, not in protective list)
    neutral_variant = report.classify_variant(
        rsid="rs987654321",
        gene="APOE",
        score=0.2,
        position="112",
        ref_aa="C",
        alt_aa="R",
        mutation_description="C112R"
    )
    print(f"Low score variant: {neutral_variant.classification.value} - {neutral_variant.reasoning}")
    
    # Test benign variant that becomes neutral (not in protective list)
    benign_neutral_variant = report.classify_variant(
        rsid="rs111111111",
        gene="LDLR",
        score=0.1,
        position="50",
        ref_aa="A",
        alt_aa="G",
        mutation_description="A50G"
    )
    print(f"Benign variant (not protective): {benign_neutral_variant.classification.value} - {benign_neutral_variant.reasoning}")
    
    print("\n5. Classification Summary:")
    print("- Pathogenic: High pathogenicity scores (≥0.65)")
    print("- Protective: Only variants explicitly listed in protective_variants_list.json")
    print("- Neutral: All other variants (including benign variants not in protective list)")
    
    print(f"\n6. Protective variants file location: ./protective_variants_list.json")
    print("You can edit this file to add your own protective variants.")
    
    # Show how to remove a protective variant
    print(f"\n7. Removing the added protective variant...")
    removed = report.remove_protective_variant("rs1800562")
    print(f"Removed successfully: {removed}")

if __name__ == "__main__":
    main()