#!/usr/bin/env python3
"""
Comprehensive Test Runner for Risk-Protective Variant Reporting System

This script runs all test suites for the risk-protective variant reporting system,
providing comprehensive coverage as specified in task 10.

Requirements covered: 1.1, 1.2, 1.3, 1.4
"""

import sys
import os
import time
import unittest
import logging
from typing import Dict, List, Tuple
import argparse

# Add current directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import test modules
try:
    from test_comprehensive_risk_protective_suite import main as run_comprehensive_suite
    from test_section_manager_integration import main as run_section_integration_tests
    from test_performance_classification_scale import run_performance_suite
    from test_end_to_end_report_generation import main as run_end_to_end_tests
except ImportError as e:
    print(f"Error importing test modules: {e}")
    print("Make sure all test files are in the current directory")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TestSuiteRunner:
    """Manages execution of multiple test suites"""
    
    def __init__(self):
        self.results = {}
        self.start_time = None
        self.end_time = None
    
    def run_test_suite(self, suite_name: str, test_function) -> Dict:
        """Run a single test suite and capture results"""
        logger.info(f"Starting test suite: {suite_name}")
        print(f"\n{'='*70}")
        print(f"RUNNING: {suite_name}")
        print(f"{'='*70}")
        
        start_time = time.time()
        
        try:
            success = test_function()
            end_time = time.time()
            duration = end_time - start_time
            
            result = {
                'success': success,
                'duration': duration,
                'error': None
            }
            
            logger.info(f"Completed {suite_name}: {'PASSED' if success else 'FAILED'} ({duration:.2f}s)")
            
        except Exception as e:
            end_time = time.time()
            duration = end_time - start_time
            
            result = {
                'success': False,
                'duration': duration,
                'error': str(e)
            }
            
            logger.error(f"Failed {suite_name}: {e} ({duration:.2f}s)")
        
        self.results[suite_name] = result
        return result
    
    def run_all_suites(self, suites_to_run: List[str] = None) -> bool:
        """Run all test suites"""
        self.start_time = time.time()
        
        # Define all available test suites
        available_suites = {
            'comprehensive': {
                'name': 'Comprehensive Unit Tests',
                'function': run_comprehensive_suite,
                'description': 'Unit tests for VariantClassifier with various variant types'
            },
            'integration': {
                'name': 'Section Manager Integration Tests',
                'function': run_section_integration_tests,
                'description': 'Integration tests for section management logic'
            },
            'end_to_end': {
                'name': 'End-to-End Report Generation Tests',
                'function': run_end_to_end_tests,
                'description': 'End-to-end tests for complete report generation'
            },
            'performance': {
                'name': 'Performance Tests',
                'function': run_performance_suite,
                'description': 'Performance tests for classification at scale'
            }
        }
        
        # Determine which suites to run
        if suites_to_run is None:
            suites_to_run = list(available_suites.keys())
        
        print("Risk-Protective Variant Reporting System - Comprehensive Test Suite")
        print("="*80)
        print(f"Running {len(suites_to_run)} test suite(s): {', '.join(suites_to_run)}")
        print("="*80)
        
        # Run each selected suite
        for suite_key in suites_to_run:
            if suite_key not in available_suites:
                logger.warning(f"Unknown test suite: {suite_key}")
                continue
            
            suite_info = available_suites[suite_key]
            print(f"\n{suite_info['description']}")
            
            self.run_test_suite(suite_info['name'], suite_info['function'])
        
        self.end_time = time.time()
        
        # Generate summary
        return self.generate_summary()
    
    def generate_summary(self) -> bool:
        """Generate and display test summary"""
        total_duration = self.end_time - self.start_time if self.end_time and self.start_time else 0
        
        print(f"\n{'='*80}")
        print("COMPREHENSIVE TEST SUITE SUMMARY")
        print(f"{'='*80}")
        
        # Overall statistics
        total_suites = len(self.results)
        passed_suites = sum(1 for r in self.results.values() if r['success'])
        failed_suites = total_suites - passed_suites
        
        print(f"Total test suites run: {total_suites}")
        print(f"Passed: {passed_suites}")
        print(f"Failed: {failed_suites}")
        print(f"Total execution time: {total_duration:.2f} seconds")
        print(f"Success rate: {(passed_suites/total_suites*100):.1f}%")
        
        # Detailed results
        print(f"\n{'Suite Name':<40} {'Status':<10} {'Duration':<12} {'Notes'}")
        print("-" * 80)
        
        for suite_name, result in self.results.items():
            status = "PASSED" if result['success'] else "FAILED"
            duration = f"{result['duration']:.2f}s"
            notes = result['error'][:30] + "..." if result['error'] and len(result['error']) > 30 else (result['error'] or "")
            
            print(f"{suite_name:<40} {status:<10} {duration:<12} {notes}")
        
        # Requirements coverage summary
        print(f"\n{'='*80}")
        print("REQUIREMENTS COVERAGE SUMMARY")
        print(f"{'='*80}")
        
        requirements_coverage = {
            '1.1': 'Unit tests for VariantClassifier with various variant types',
            '1.2': 'Integration tests for section management logic', 
            '1.3': 'End-to-end tests for complete report generation',
            '1.4': 'Performance tests for classification at scale'
        }
        
        for req_id, description in requirements_coverage.items():
            # Determine if requirement is covered based on suite results
            covered = self._is_requirement_covered(req_id)
            status = "✓ COVERED" if covered else "✗ NOT COVERED"
            print(f"Requirement {req_id}: {status}")
            print(f"  {description}")
        
        # Failure details
        if failed_suites > 0:
            print(f"\n{'='*80}")
            print("FAILURE DETAILS")
            print(f"{'='*80}")
            
            for suite_name, result in self.results.items():
                if not result['success']:
                    print(f"\n{suite_name}:")
                    if result['error']:
                        print(f"  Error: {result['error']}")
                    else:
                        print("  Test failures occurred (see detailed output above)")
        
        # Recommendations
        print(f"\n{'='*80}")
        print("RECOMMENDATIONS")
        print(f"{'='*80}")
        
        if failed_suites == 0:
            print("✓ All test suites passed successfully!")
            print("✓ The risk-protective variant reporting system is ready for deployment.")
            print("✓ All requirements (1.1, 1.2, 1.3, 1.4) have been satisfied.")
        else:
            print("⚠ Some test suites failed. Please review the failure details above.")
            print("⚠ Address failing tests before proceeding with deployment.")
            
            if 'Performance Tests' in [name for name, result in self.results.items() if not result['success']]:
                print("⚠ Performance issues detected. Consider optimization before production use.")
        
        # Performance insights
        if 'Performance Tests' in self.results and self.results['Performance Tests']['success']:
            print("\n✓ Performance tests passed - system is ready for production scale.")
        
        print(f"\n{'='*80}")
        
        return failed_suites == 0
    
    def _is_requirement_covered(self, req_id: str) -> bool:
        """Check if a specific requirement is covered by successful tests"""
        requirement_mapping = {
            '1.1': ['Comprehensive Unit Tests'],
            '1.2': ['Section Manager Integration Tests'],
            '1.3': ['End-to-End Report Generation Tests'],
            '1.4': ['Performance Tests']
        }
        
        required_suites = requirement_mapping.get(req_id, [])
        
        for suite_name in required_suites:
            if suite_name not in self.results or not self.results[suite_name]['success']:
                return False
        
        return True


def main():
    """Main entry point for comprehensive test runner"""
    parser = argparse.ArgumentParser(
        description='Run comprehensive tests for risk-protective variant reporting system'
    )
    
    parser.add_argument(
        '--suites',
        nargs='+',
        choices=['comprehensive', 'integration', 'end_to_end', 'performance'],
        help='Specific test suites to run (default: all)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    parser.add_argument(
        '--quick',
        action='store_true',
        help='Run quick tests only (excludes performance tests)'
    )
    
    args = parser.parse_args()
    
    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Determine suites to run
    suites_to_run = args.suites
    
    if args.quick and not suites_to_run:
        suites_to_run = ['comprehensive', 'integration', 'end_to_end']
        print("Quick mode: Excluding performance tests")
    
    # Run tests
    runner = TestSuiteRunner()
    success = runner.run_all_suites(suites_to_run)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()