#!/usr/bin/env python3
"""
JSON Report Writer for Precision Medicine Reports

This module handles joining report blocks and writing complete JSON output to files.
"""

import json
import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from report_blocks import ReportBlock, BlockType

# Configure logger
logger = logging.getLogger(__name__)

def blocks_to_json(blocks: List[ReportBlock], report_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Convert a list of ReportBlock objects to a complete JSON structure.
    
    Args:
        blocks: List of ReportBlock objects
        report_info: Optional dictionary containing report metadata
        
    Returns:
        Dictionary containing the complete report in JSON format
    """
    # Initialize the report structure
    report_json = {
        "report_metadata": {
            "generated_at": datetime.now().isoformat(),
            "version": "1.0.0",
            "total_blocks": len(blocks)
        },
        "blocks": {}
    }
    
    # Add report info if provided
    if report_info:
        report_json["report_metadata"].update({
            "patient_name": report_info.get("patient_name", ""),
            "patient_id": report_info.get("member_id", ""),
            "provider_name": report_info.get("provider_name", ""),
            "focus": report_info.get("focus", ""),
            "template_name": report_info.get("template_name", ""),
            "report_name": report_info.get("report_name", "")
        })
        
        # Add GWAS associations to metadata for PDF generation
        gwas_data = report_info.get("gwas_associations", [])
        if gwas_data:
            report_json["gwas_associations"] = gwas_data
        
        # Add prot2mut data for PDF generation
        prot2mut_data = report_info.get("mutations", {})
        if prot2mut_data:
            report_json["prot2mut"] = prot2mut_data
    
    # Process each block
    for block in blocks:
        block_data = {
            "title": block.title,
            "order": block.order,
            "template": block.template,
            "is_required": block.is_required,
            "user_customizable": block.user_customizable,
            "modifications": block.modifications,
            "feedback": block.feedback
        }
        
        # Handle content - try to parse as JSON if it's a string
        content = block.content
        if isinstance(content, str):
            # Try to parse as JSON first
            try:
                # Look for JSON-like content (starts with { and ends with })
                content = content.strip()
                if content.startswith('{') and content.endswith('}'):
                    content = json.loads(content)
                else:
                    # Keep as string if not JSON
                    pass
            except json.JSONDecodeError:
                # Keep as string if JSON parsing fails
                pass
        
        block_data["content"] = content
        
        # Use block type as key
        block_key = block.block_type.value if hasattr(block.block_type, 'value') else str(block.block_type)
        report_json["blocks"][block_key] = block_data
    
    return report_json

def write_json_report(blocks: List[ReportBlock], output_path: str, report_info: Optional[Dict[str, Any]] = None) -> bool:
    """
    Write a complete JSON report to a file.
    
    Args:
        blocks: List of ReportBlock objects
        output_path: Path where the JSON file should be written
        report_info: Optional dictionary containing report metadata
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Convert blocks to JSON
        report_json = blocks_to_json(blocks, report_info)
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report_json, f, indent=2, ensure_ascii=False)
        
        logger.info(f"JSON report successfully written to: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error writing JSON report to {output_path}: {str(e)}")
        return False

def write_blocks_as_separate_json(blocks: List[ReportBlock], output_dir: str, report_info: Optional[Dict[str, Any]] = None) -> bool:
    """
    Write each block as a separate JSON file.
    
    Args:
        blocks: List of ReportBlock objects
        output_dir: Directory where JSON files should be written
        report_info: Optional dictionary containing report metadata
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        
        # Write metadata file
        metadata = {
            "generated_at": datetime.now().isoformat(),
            "version": "1.0.0",
            "total_blocks": len(blocks),
            "block_files": []
        }
        
        if report_info:
            metadata.update({
                "patient_name": report_info.get("patient_name", ""),
                "patient_id": report_info.get("member_id", ""),
                "provider_name": report_info.get("provider_name", ""),
                "focus": report_info.get("focus", "")
            })
            
            # Add GWAS and prot2mut data to metadata
            gwas_data = report_info.get("gwas_associations", [])
            if gwas_data:
                metadata["gwas_associations"] = gwas_data
                
            prot2mut_data = report_info.get("mutations", {})
            if prot2mut_data:
                metadata["prot2mut"] = prot2mut_data
        
        # Write each block to a separate file
        for block in blocks:
            block_key = block.block_type.value if hasattr(block.block_type, 'value') else str(block.block_type)
            filename = f"{block_key}.json"
            filepath = os.path.join(output_dir, filename)
            
            block_data = {
                "block_type": block_key,
                "title": block.title,
                "order": block.order,
                "template": block.template,
                "is_required": block.is_required,
                "user_customizable": block.user_customizable,
                "modifications": block.modifications,
                "feedback": block.feedback,
                "content": block.content
            }
            
            # Handle content parsing
            if isinstance(block.content, str):
                try:
                    content = block.content.strip()
                    if content.startswith('{') and content.endswith('}'):
                        block_data["content"] = json.loads(content)
                except json.JSONDecodeError:
                    pass
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(block_data, f, indent=2, ensure_ascii=False)
            
            metadata["block_files"].append(filename)
            logger.info(f"Block {block_key} written to: {filepath}")
        
        # Write metadata file
        metadata_path = os.path.join(output_dir, "report_metadata.json")
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Report metadata written to: {metadata_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error writing separate JSON blocks to {output_dir}: {str(e)}")
        return False

def combine_json_blocks(blocks_dir: str) -> Dict[str, Any]:
    """
    Combine separate JSON block files back into a single report structure.
    
    Args:
        blocks_dir: Directory containing the JSON block files
        
    Returns:
        Dictionary containing the complete report
    """
    try:
        # Read metadata
        metadata_path = os.path.join(blocks_dir, "report_metadata.json")
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        # Initialize report structure
        report_json = {
            "report_metadata": metadata,
            "blocks": {}
        }
        
        # Read each block file
        for filename in metadata.get("block_files", []):
            filepath = os.path.join(blocks_dir, filename)
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    block_data = json.load(f)
                
                block_key = block_data.get("block_type", filename.replace('.json', ''))
                report_json["blocks"][block_key] = block_data
        
        return report_json
        
    except Exception as e:
        logger.error(f"Error combining JSON blocks from {blocks_dir}: {str(e)}")
        return {}

# Convenience function for easy integration
def save_report_json(blocks: List[ReportBlock], report_name: str, report_info: Optional[Dict[str, Any]] = None, 
                    output_format: str = "single") -> str:
    """
    Save report blocks as JSON with automatic file naming.
    
    Args:
        blocks: List of ReportBlock objects
        report_name: Base name for the report
        report_info: Optional dictionary containing report metadata
        output_format: "single" for one file, "separate" for multiple files
        
    Returns:
        Path to the output file or directory
    """
    # Create reports_json directory if it doesn't exist
    base_dir = "reports_json"
    os.makedirs(base_dir, exist_ok=True)
    
    if output_format == "single":
        output_path = os.path.join(base_dir, f"{report_name}.json")
        success = write_json_report(blocks, output_path, report_info)
        return output_path if success else ""
    else:
        output_dir = os.path.join(base_dir, report_name)
        success = write_blocks_as_separate_json(blocks, output_dir, report_info)
        return output_dir if success else ""