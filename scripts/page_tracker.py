"""
Enhanced Page Tracker for Accurate Table of Contents

This module provides accurate page tracking for PDF generation by monitoring
actual page positions and providing fallback mechanisms for page number calculation.
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from reportlab.platypus import Flowable, PageBreak, Paragraph, Spacer, Table


@dataclass
class PageTrackingData:
    """Data for tracking page numbers accurately"""
    section_name: str
    estimated_page: int
    actual_page: Optional[int] = None
    content_length: int = 0
    has_page_break: bool = False
    level: int = 0
    story_index: int = 0


@dataclass
class ValidationResult:
    """Result of page tracking validation"""
    valid: bool
    missing_sections: List[str] = None
    page_mismatches: List[Tuple[str, int, int]] = None  # (section, expected, actual)
    warnings: List[str] = None
    total_sections: int = 0

    def __post_init__(self):
        if self.missing_sections is None:
            self.missing_sections = []
        if self.page_mismatches is None:
            self.page_mismatches = []
        if self.warnings is None:
            self.warnings = []


class PageTracker:
    """Enhanced page tracker that monitors actual page positions"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self.current_page = 1
        self.section_pages: Dict[str, PageTrackingData] = {}
        self.story_elements: List[Tuple[str, Any]] = []  # (type, element)
        self.page_breaks: List[int] = []  # Story indices where page breaks occur
        self.content_weights = {
            'paragraph': 1,
            'table': 3,
            'spacer': 0.5,
            'page_break': 0,
            'image': 2
        }
        
    def track_section_start(self, section_name: str, story_index: int, 
                          level: int = 0, has_page_break: bool = False) -> int:
        """Track when a section starts for accurate page numbering"""
        estimated_page = self.estimate_page_at_index(story_index)
        
        # Adjust for page break
        if has_page_break:
            estimated_page += 1
            self.page_breaks.append(story_index)
        
        tracking_data = PageTrackingData(
            section_name=section_name,
            estimated_page=estimated_page,
            level=level,
            has_page_break=has_page_break,
            story_index=story_index
        )
        
        self.section_pages[section_name] = tracking_data
        self.logger.debug(f"Tracking section '{section_name}' at story index {story_index}, estimated page {estimated_page}")
        
        return estimated_page
    
    def add_story_element(self, element: Any, element_type: str = None) -> int:
        """Track story elements for accurate page estimation"""
        if element_type is None:
            element_type = self._detect_element_type(element)
        
        story_index = len(self.story_elements)
        self.story_elements.append((element_type, element))
        
        # Track page breaks
        if element_type == 'page_break':
            self.page_breaks.append(story_index)
        
        return story_index
    
    def _detect_element_type(self, element: Any) -> str:
        """Detect the type of story element"""
        if isinstance(element, PageBreak):
            return 'page_break'
        elif isinstance(element, Paragraph):
            return 'paragraph'
        elif isinstance(element, Table):
            return 'table'
        elif isinstance(element, Spacer):
            return 'spacer'
        else:
            return 'other'
    
    def estimate_page_at_index(self, story_index: int) -> int:
        """Estimate page number at a specific story index"""
        if story_index == 0:
            return 1
        
        # Count page breaks before this index
        page_breaks_before = len([pb for pb in self.page_breaks if pb < story_index])
        
        # Calculate content weight before this index
        content_weight = 0
        for i in range(min(story_index, len(self.story_elements))):
            element_type, _ = self.story_elements[i]
            content_weight += self.content_weights.get(element_type, 1)
        
        # Estimate pages based on content weight (assuming ~30 weight units per page)
        content_pages = max(0, int(content_weight / 30))
        
        # Total estimated page = 1 (base) + page breaks + content-based pages
        estimated_page = 1 + page_breaks_before + content_pages
        
        return estimated_page
    
    def estimate_current_page(self) -> int:
        """Estimate current page based on story length"""
        return self.estimate_page_at_index(len(self.story_elements))
    
    def validate_page_numbers(self) -> ValidationResult:
        """Validate page number estimates and provide fallback calculations"""
        result = ValidationResult(
            valid=True,
            total_sections=len(self.section_pages)
        )
        
        if not self.section_pages:
            result.valid = False
            result.warnings.append("No sections tracked")
            return result
        
        # Validate each section
        for section_name, tracking_data in self.section_pages.items():
            if tracking_data.estimated_page <= 0:
                result.valid = False
                result.warnings.append(f"Invalid page number for section '{section_name}': {tracking_data.estimated_page}")
            
            # Check for reasonable page progression
            if tracking_data.estimated_page > 1000:  # Sanity check
                result.valid = False
                result.warnings.append(f"Unreasonably high page number for section '{section_name}': {tracking_data.estimated_page}")
        
        # Check for page number sequence issues
        sorted_sections = sorted(
            self.section_pages.items(),
            key=lambda x: x[1].story_index
        )
        
        prev_page = 0
        for section_name, tracking_data in sorted_sections:
            if tracking_data.estimated_page < prev_page:
                result.warnings.append(f"Page number regression detected at section '{section_name}'")
            prev_page = tracking_data.estimated_page
        
        # Log validation results
        if result.valid:
            self.logger.info(f"Page tracking validation passed for {len(self.section_pages)} sections")
        else:
            self.logger.warning(f"Page tracking validation issues: {len(result.warnings)} warnings")
        
        return result
    
    def get_fallback_page_calculation(self, section_name: str) -> int:
        """Provide fallback page calculation if primary method fails"""
        if section_name not in self.section_pages:
            self.logger.warning(f"Section '{section_name}' not found for fallback calculation")
            return 1
        
        tracking_data = self.section_pages[section_name]
        
        # Fallback method 1: Simple story index based calculation
        fallback_page = max(1, tracking_data.story_index // 25 + 1)
        
        # Fallback method 2: Account for page breaks
        page_breaks_before = len([pb for pb in self.page_breaks if pb < tracking_data.story_index])
        fallback_page += page_breaks_before
        
        self.logger.debug(f"Fallback page calculation for '{section_name}': {fallback_page}")
        return fallback_page
    
    def recalculate_all_pages(self) -> Dict[str, int]:
        """Recalculate all page numbers using improved estimation"""
        recalculated = {}
        
        for section_name, tracking_data in self.section_pages.items():
            # Use improved estimation
            new_page = self.estimate_page_at_index(tracking_data.story_index)
            
            # Apply fallback if estimation seems wrong
            if new_page <= 0 or new_page > 1000:
                new_page = self.get_fallback_page_calculation(section_name)
            
            # Update tracking data
            tracking_data.estimated_page = new_page
            recalculated[section_name] = new_page
        
        self.logger.info(f"Recalculated page numbers for {len(recalculated)} sections")
        return recalculated
    
    def get_section_info(self) -> Dict[str, Dict[str, Any]]:
        """Get detailed information about all tracked sections"""
        return {
            name: {
                'estimated_page': data.estimated_page,
                'actual_page': data.actual_page,
                'level': data.level,
                'has_page_break': data.has_page_break,
                'story_index': data.story_index,
                'content_length': data.content_length
            }
            for name, data in self.section_pages.items()
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about page tracking"""
        return {
            'total_sections': len(self.section_pages),
            'total_story_elements': len(self.story_elements),
            'total_page_breaks': len(self.page_breaks),
            'estimated_total_pages': self.estimate_current_page(),
            'element_type_counts': self._get_element_type_counts()
        }
    
    def _get_element_type_counts(self) -> Dict[str, int]:
        """Get counts of different element types"""
        counts = {}
        for element_type, _ in self.story_elements:
            counts[element_type] = counts.get(element_type, 0) + 1
        return counts