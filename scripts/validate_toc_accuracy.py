#!/usr/bin/env python3
"""
TOC Accuracy Validation Script

This script validates that the table of contents entries match the actual
document structure and page numbers in generated PDFs.
"""

import json
import logging
import sys
import os
from pdf_generator import PDFReportGenerator
from page_tracker import PageTracker, ValidationResult

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def validate_toc_structure(generator):
    """Validate TOC structure and page number accuracy."""
    logger.info("Validating TOC structure...")
    
    # Get page tracker information
    section_info = generator.page_tracker.get_section_info()
    toc_entries = generator.toc_entries
    
    validation_issues = []
    
    # Check that all TOC entries have corresponding sections
    toc_titles = {entry['title'] for entry in toc_entries}
    tracked_sections = set(section_info.keys())
    
    # Find missing sections
    missing_in_tracker = toc_titles - tracked_sections
    missing_in_toc = tracked_sections - toc_titles
    
    if missing_in_tracker:
        validation_issues.append(f"TOC entries not tracked: {missing_in_tracker}")
    
    if missing_in_toc:
        validation_issues.append(f"Tracked sections not in TOC: {missing_in_toc}")
    
    # Validate page number progression
    sorted_toc = sorted(toc_entries, key=lambda x: x.get('page', 0))
    prev_page = 0
    
    for entry in sorted_toc:
        current_page = entry.get('page', 0)
        if current_page <= prev_page and prev_page > 0:
            validation_issues.append(f"Page regression in TOC: {entry['title']} at page {current_page} after page {prev_page}")
        prev_page = current_page
    
    # Check for reasonable page numbers
    for entry in toc_entries:
        page = entry.get('page', 0)
        if page <= 0:
            validation_issues.append(f"Invalid page number for {entry['title']}: {page}")
        elif page > 100:  # Sanity check for very large page numbers
            validation_issues.append(f"Unusually high page number for {entry['title']}: {page}")
    
    return validation_issues

def compare_estimation_methods(generator):
    """Compare different page estimation methods."""
    logger.info("Comparing page estimation methods...")
    
    section_info = generator.page_tracker.get_section_info()
    comparison_results = {}
    
    for section_name, info in section_info.items():
        estimated_page = info['estimated_page']
        fallback_page = generator.page_tracker.get_fallback_page_calculation(section_name)
        
        comparison_results[section_name] = {
            'estimated': estimated_page,
            'fallback': fallback_page,
            'difference': abs(estimated_page - fallback_page),
            'story_index': info['story_index']
        }
    
    return comparison_results

def test_toc_validation_comprehensive():
    """Comprehensive test of TOC validation with multiple report types."""
    logger.info("Running comprehensive TOC validation...")
    
    test_files = [
        'reports_json/Aug12Report.json',
        'reports_json/ErvinReport.json',
        'reports_json/UpdatedErvinReport5.json'
    ]
    
    results = {}
    
    for test_file in test_files:
        if not os.path.exists(test_file):
            logger.warning(f"Test file not found: {test_file}")
            continue
        
        logger.info(f"Testing with {test_file}...")
        
        try:
            # Load test data
            with open(test_file, 'r') as f:
                data = json.load(f)
            
            # Generate PDF
            output_file = f"validation_test_{os.path.basename(test_file).replace('.json', '.pdf')}"
            generator = PDFReportGenerator(output_file, data)
            generator.generate_report()
            
            # Validate TOC structure
            validation_issues = validate_toc_structure(generator)
            
            # Compare estimation methods
            comparison = compare_estimation_methods(generator)
            
            # Get statistics
            stats = generator.page_tracker.get_statistics()
            
            results[test_file] = {
                'validation_issues': validation_issues,
                'comparison': comparison,
                'statistics': stats,
                'output_file': output_file,
                'success': len(validation_issues) == 0
            }
            
            logger.info(f"Validation for {test_file}: {'PASSED' if len(validation_issues) == 0 else 'ISSUES FOUND'}")
            if validation_issues:
                for issue in validation_issues:
                    logger.warning(f"  - {issue}")
            
        except Exception as e:
            logger.error(f"Error testing {test_file}: {e}")
            results[test_file] = {
                'error': str(e),
                'success': False
            }
    
    return results

def analyze_page_tracking_accuracy(results):
    """Analyze the accuracy of page tracking across different reports."""
    logger.info("Analyzing page tracking accuracy...")
    
    total_sections = 0
    total_differences = 0
    max_difference = 0
    
    for test_file, result in results.items():
        if not result.get('success', False) or 'comparison' not in result:
            continue
        
        comparison = result['comparison']
        for section_name, comp_data in comparison.items():
            total_sections += 1
            diff = comp_data['difference']
            total_differences += diff
            max_difference = max(max_difference, diff)
    
    if total_sections > 0:
        avg_difference = total_differences / total_sections
        logger.info(f"Page tracking accuracy analysis:")
        logger.info(f"  Total sections analyzed: {total_sections}")
        logger.info(f"  Average page difference: {avg_difference:.2f}")
        logger.info(f"  Maximum page difference: {max_difference}")
        logger.info(f"  Accuracy rating: {'EXCELLENT' if avg_difference < 1 else 'GOOD' if avg_difference < 2 else 'NEEDS IMPROVEMENT'}")
    else:
        logger.warning("No sections available for accuracy analysis")

def main():
    """Run comprehensive TOC validation."""
    logger.info("Starting comprehensive TOC validation...")
    
    # Run comprehensive validation
    results = test_toc_validation_comprehensive()
    
    # Analyze results
    logger.info(f"\n{'='*60}")
    logger.info("VALIDATION SUMMARY")
    logger.info(f"{'='*60}")
    
    successful_tests = 0
    total_tests = len(results)
    
    for test_file, result in results.items():
        status = "PASSED" if result.get('success', False) else "FAILED"
        logger.info(f"{os.path.basename(test_file)}: {status}")
        
        if result.get('success', False):
            successful_tests += 1
            stats = result.get('statistics', {})
            logger.info(f"  Sections: {stats.get('total_sections', 0)}, "
                       f"Elements: {stats.get('total_story_elements', 0)}, "
                       f"Pages: {stats.get('estimated_total_pages', 0)}")
        else:
            if 'error' in result:
                logger.error(f"  Error: {result['error']}")
            if 'validation_issues' in result:
                for issue in result['validation_issues']:
                    logger.warning(f"  Issue: {issue}")
    
    # Analyze accuracy
    analyze_page_tracking_accuracy(results)
    
    logger.info(f"\nOverall: {successful_tests}/{total_tests} tests passed")
    
    if successful_tests == total_tests:
        logger.info("All TOC validation tests passed!")
        return 0
    else:
        logger.error("Some TOC validation tests failed.")
        return 1

if __name__ == "__main__":
    sys.exit(main())