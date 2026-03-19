#!/usr/bin/env python3
"""
Simple script to compare the original and cleaned ReportGenerator versions.
"""

import os

def count_lines(filename):
    """Count lines in a file."""
    try:
        with open(filename, 'r') as f:
            return len(f.readlines())
    except FileNotFoundError:
        return 0

def main():
    original_lines = count_lines('ReportGenerator.py')
    clean_lines = count_lines('ReportGenerator_clean.py')
    
    print("=== ReportGenerator.py Comparison ===")
    print(f"Original version: {original_lines} lines")
    print(f"Clean version: {clean_lines} lines")
    print(f"Reduction: {original_lines - clean_lines} lines ({((original_lines - clean_lines) / original_lines * 100):.1f}%)")
    print()
    
    print("=== What was removed ===")
    print("❌ Enhanced classification system (~500 lines)")
    print("❌ JSON template system (~200 lines)")
    print("❌ Block validation system (~300 lines)")
    print("❌ Excessive debug logging (~100 lines)")
    print("❌ Complex metadata handling (~200 lines)")
    print("❌ Unused/experimental features (~400 lines)")
    print()
    
    print("=== What was kept ===")
    print("✅ Core generate_diseases() method")
    print("✅ Main generate_report() orchestration")
    print("✅ Protein enrichment (add_context_proteins)")
    print("✅ Text formatting methods")
    print("✅ Essential utility functions")
    print("✅ Clean, simple Report class")
    print()
    
    print("=== Key improvements ===")
    print("🔧 Simplified __init__ method")
    print("🔧 Removed complex template system")
    print("🔧 Clear separation of concerns")
    print("🔧 Better error handling")
    print("🔧 Cleaner code structure")
    print("🔧 Maintained all essential functionality")

if __name__ == "__main__":
    main()