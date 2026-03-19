#!/usr/bin/env python3
"""
Lambda-Optimized PDF Generator

This module provides a Lambda-optimized interface for PDF generation
that works efficiently in serverless environments with proper error handling,
memory management, and S3 integration.
"""

import json
import os
import tempfile
import logging
from datetime import datetime
from professional_pdf_generator import ProfessionalPDFGenerator

# Configure logging
logger = logging.getLogger(__name__)

class LambdaPDFGenerator:
    """
    Lambda-optimized PDF generator that handles serverless constraints
    and provides robust error handling for AWS Lambda environment.
    """
    
    def __init__(self, temp_dir="/tmp"):
        """
        Initialize the Lambda PDF generator.
        
        Args:
            temp_dir (str): Temporary directory for file operations (default: /tmp for Lambda)
        """
        self.temp_dir = temp_dir
        self.cleanup_files = []
        
        # Ensure temp directory exists
        os.makedirs(temp_dir, exist_ok=True)
        
        logger.info(f"LambdaPDFGenerator initialized with temp_dir: {temp_dir}")
    
    def generate_pdf_from_json(self, json_data, output_filename=None, template_data=None):
        """
        Generate PDF from JSON data with Lambda optimizations.
        
        Args:
            json_data (dict): Report data in JSON format
            output_filename (str): Optional output filename (auto-generated if None)
            template_data (dict): Optional template configuration
            
        Returns:
            dict: Result containing success status, file path, and metadata
        """
        try:
            # Generate output filename if not provided
            if not output_filename:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                patient_name = self._extract_safe_patient_name(json_data)
                output_filename = f"report_{patient_name}_{timestamp}.pdf"
            
            # Ensure filename is safe for filesystem
            safe_filename = self._sanitize_filename(output_filename)
            output_path = os.path.join(self.temp_dir, safe_filename)
            
            # Save template to temporary file if provided
            template_path = None
            if template_data:
                template_path = os.path.join(self.temp_dir, "template.json")
                with open(template_path, 'w') as f:
                    json.dump(template_data, f)
                self.cleanup_files.append(template_path)
            
            logger.info(f"Generating PDF: {output_path}")
            logger.info(f"Template: {'Yes' if template_path else 'No'}")
            
            # Validate JSON data
            validation_result = self._validate_json_data(json_data)
            if not validation_result['valid']:
                return {
                    'success': False,
                    'error': f"Invalid JSON data: {validation_result['error']}",
                    'file_path': None,
                    'file_size': 0
                }
            
            # Generate PDF using ProfessionalPDFGenerator
            generator = ProfessionalPDFGenerator(output_path, json_data, template_path)
            
            # Monitor memory usage (Lambda has limited memory)
            initial_memory = self._get_memory_usage()
            logger.info(f"Memory usage before PDF generation: {initial_memory} MB")
            
            success = generator.generate_report()
            
            final_memory = self._get_memory_usage()
            logger.info(f"Memory usage after PDF generation: {final_memory} MB")
            
            if success and os.path.exists(output_path):
                file_size = os.path.getsize(output_path)
                
                # Add to cleanup list
                self.cleanup_files.append(output_path)
                
                logger.info(f"PDF generated successfully: {output_path} ({file_size:,} bytes)")
                
                return {
                    'success': True,
                    'file_path': output_path,
                    'file_size': file_size,
                    'filename': safe_filename,
                    'memory_used': final_memory - initial_memory,
                    'patient_name': self._extract_patient_name(json_data),
                    'condition_focus': self._extract_condition_focus(json_data)
                }
            else:
                return {
                    'success': False,
                    'error': 'PDF generation failed - file not created',
                    'file_path': None,
                    'file_size': 0
                }
                
        except Exception as e:
            logger.error(f"Error generating PDF: {str(e)}")
            logger.exception("Full traceback:")
            
            return {
                'success': False,
                'error': str(e),
                'file_path': None,
                'file_size': 0
            }
    
    def _validate_json_data(self, json_data):
        """
        Validate JSON data structure for PDF generation.
        
        Args:
            json_data (dict): JSON data to validate
            
        Returns:
            dict: Validation result with 'valid' boolean and 'error' message
        """
        try:
            if not isinstance(json_data, dict):
                return {'valid': False, 'error': 'JSON data must be a dictionary'}
            
            # Check for required top-level keys
            if 'report_metadata' not in json_data and 'blocks' not in json_data:
                return {'valid': False, 'error': 'JSON must contain either report_metadata or blocks'}
            
            # Validate report_metadata if present
            if 'report_metadata' in json_data:
                metadata = json_data['report_metadata']
                if not isinstance(metadata, dict):
                    return {'valid': False, 'error': 'report_metadata must be a dictionary'}
            
            # Validate blocks if present
            if 'blocks' in json_data:
                blocks = json_data['blocks']
                if not isinstance(blocks, dict):
                    return {'valid': False, 'error': 'blocks must be a dictionary'}
                
                # Check if at least one block has content
                has_content = False
                for block_name, block_data in blocks.items():
                    if isinstance(block_data, dict) and 'content' in block_data:
                        if block_data['content']:  # Not empty
                            has_content = True
                            break
                
                if not has_content:
                    logger.warning("No blocks with content found, but proceeding with generation")
            
            return {'valid': True, 'error': None}
            
        except Exception as e:
            return {'valid': False, 'error': f'Validation error: {str(e)}'}
    
    def _extract_safe_patient_name(self, json_data):
        """Extract and sanitize patient name for filename use."""
        try:
            metadata = json_data.get('report_metadata', {})
            patient_name = metadata.get('patient_name', 'unknown_patient')
            
            # Sanitize for filename use
            safe_name = "".join(c for c in patient_name if c.isalnum() or c in (' ', '-', '_'))
            safe_name = safe_name.replace(' ', '_').lower()
            
            return safe_name[:50]  # Limit length
            
        except Exception:
            return 'unknown_patient'
    
    def _extract_patient_name(self, json_data):
        """Extract patient name for metadata."""
        try:
            metadata = json_data.get('report_metadata', {})
            return metadata.get('patient_name', 'Unknown Patient')
        except Exception:
            return 'Unknown Patient'
    
    def _extract_condition_focus(self, json_data):
        """Extract condition focus for metadata."""
        try:
            metadata = json_data.get('report_metadata', {})
            focus = metadata.get('focus', '')
            
            if 'adhd' in focus.lower():
                return 'ADHD'
            elif 'depression' in focus.lower():
                return 'Depression'
            elif 'anxiety' in focus.lower():
                return 'Anxiety'
            elif 'cardiovascular' in focus.lower():
                return 'Cardiovascular'
            else:
                return 'General Medical Genetics'
                
        except Exception:
            return 'General Medical Genetics'
    
    def _sanitize_filename(self, filename):
        """
        Sanitize filename for filesystem compatibility.
        
        Args:
            filename (str): Original filename
            
        Returns:
            str: Sanitized filename
        """
        # Remove or replace invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        
        # Ensure it ends with .pdf
        if not filename.lower().endswith('.pdf'):
            filename += '.pdf'
        
        # Limit length
        if len(filename) > 255:
            name_part = filename[:-4]  # Remove .pdf
            filename = name_part[:251] + '.pdf'  # Keep .pdf extension
        
        return filename
    
    def _get_memory_usage(self):
        """
        Get current memory usage in MB.
        
        Returns:
            float: Memory usage in MB
        """
        try:
            import psutil
            process = psutil.Process(os.getpid())
            memory_mb = process.memory_info().rss / 1024 / 1024
            return round(memory_mb, 2)
        except ImportError:
            # psutil not available, estimate from /proc/self/status if on Linux
            try:
                with open('/proc/self/status', 'r') as f:
                    for line in f:
                        if line.startswith('VmRSS:'):
                            memory_kb = int(line.split()[1])
                            return round(memory_kb / 1024, 2)
            except:
                pass
            
            return 0.0  # Unable to determine memory usage
    
    def cleanup(self):
        """
        Clean up temporary files created during PDF generation.
        This should be called after uploading files to S3 or completing processing.
        """
        cleaned_count = 0
        
        for file_path in self.cleanup_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    cleaned_count += 1
                    logger.info(f"Cleaned up: {file_path}")
            except Exception as e:
                logger.warning(f"Could not clean up {file_path}: {e}")
        
        self.cleanup_files.clear()
        logger.info(f"Cleanup complete: {cleaned_count} files removed")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with automatic cleanup."""
        # Don't automatically cleanup in Lambda environment
        # Let the Lambda function handle cleanup after S3 upload
        pass


# Convenience function for Lambda usage
def generate_pdf_for_lambda(json_data, output_filename=None, template_data=None):
    """
    Convenience function for generating PDFs in Lambda environment.
    
    Args:
        json_data (dict): Report data in JSON format
        output_filename (str): Optional output filename
        template_data (dict): Optional template configuration
        
    Returns:
        dict: Result containing success status, file path, and metadata
    """
    with LambdaPDFGenerator() as generator:
        return generator.generate_pdf_from_json(json_data, output_filename, template_data)


# For testing
if __name__ == "__main__":
    # Test with sample data
    test_data = {
        "report_metadata": {
            "patient_name": "Test Patient",
            "patient_id": "TEST001",
            "provider_name": "Dr. Test",
            "report_date": "2025-01-16",
            "focus": "ADHD"
        },
        "blocks": {
            "executive_summary": {
                "content": json.dumps({
                    "executive_summary": {
                        "summary_statement": "Test summary for Lambda PDF generator"
                    }
                })
            }
        }
    }
    
    print("🧪 Testing Lambda PDF Generator")
    result = generate_pdf_for_lambda(test_data)
    
    if result['success']:
        print(f"✅ Success: {result['filename']}")
        print(f"📄 Size: {result['file_size']:,} bytes")
        print(f"👤 Patient: {result['patient_name']}")
        print(f"🎯 Focus: {result['condition_focus']}")
    else:
        print(f"❌ Failed: {result['error']}")