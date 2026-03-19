"""
Section Management System for Risk/Protective Variant Reporting

This module provides the SectionManager class for determining which report sections
should be displayed based on the presence and types of variants for each condition.
It implements intelligent section visibility logic and priority ordering.
"""

from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass
import logging
from datetime import datetime

# Import the enhanced data models and enums
from enhanced_data_models import (
    EnhancedVariant, SectionConfig, SectionType, SectionPriority,
    ReportSection, create_section_config_for_condition
)
from variant_classifier import EffectDirection, ConfidenceLevel

logger = logging.getLogger(__name__)


@dataclass
class ConditionSectionAnalysis:
    """Analysis result for a specific condition's section requirements."""
    condition: str
    risk_variants: List[EnhancedVariant]
    protective_variants: List[EnhancedVariant]
    neutral_variants: List[EnhancedVariant]
    total_variants: int
    has_high_confidence_variants: bool
    recommended_priority: SectionPriority
    required_sections: Set[SectionType]


class SectionManager:
    """
    Main class for determining required sections based on variant analysis.
    
    This class implements the core logic for evaluating which report sections
    should be displayed for each condition based on the presence and types
    of genetic variants.
    """
    
    def __init__(self, min_confidence_level: ConfidenceLevel = ConfidenceLevel.MODERATE):
        """
        Initialize the section manager.
        
        Args:
            min_confidence_level: Minimum confidence level for variants to be considered
        """
        self.min_confidence_level = min_confidence_level
        self.logger = logging.getLogger(__name__)
        
        # Default section ordering by priority
        self.default_section_order = [
            SectionType.RISK_ASSESSMENT,
            SectionType.PROTECTIVE_FACTORS,
            SectionType.CLINICAL_IMPLICATIONS,
            SectionType.MUTATION_PROFILE,
            SectionType.LITERATURE_EVIDENCE,
            SectionType.LIFESTYLE_RECOMMENDATIONS
        ]
    
    def determine_required_sections(self, variants: List[EnhancedVariant], 
                                  condition: str) -> SectionConfig:
        """
        Determine which sections are required for a specific condition with enhanced error handling.
        
        This method analyzes the provided variants and determines which report
        sections should be displayed based on the presence of risk-increasing
        and protective variants.
        
        Args:
            variants: List of enhanced variants for the condition
            condition: Name of the condition being analyzed
            
        Returns:
            SectionConfig object specifying which sections to display
            
        Requirements: 2.1, 2.2, 2.3, 2.4
        """
        # Enhanced input validation
        if not condition or not condition.strip():
            self.logger.warning("Empty or invalid condition name provided")
            condition = "Unknown Condition"
        
        try:
            # Handle None or empty variants with fallback behavior
            if variants is None:
                self.logger.info(f"No variants provided for condition {condition}")
                variants = []
            elif not isinstance(variants, list):
                self.logger.error(f"Invalid variants type for condition {condition}: {type(variants)}")
                variants = []
            
            # Validate variant objects
            valid_variants = self._validate_variant_objects(variants, condition)
            
            # Filter variants by minimum confidence level
            filtered_variants = self._filter_variants_by_confidence(valid_variants)
            
            # Log filtering results
            if len(valid_variants) != len(variants):
                self.logger.warning(
                    f"Filtered out {len(variants) - len(valid_variants)} invalid variants for {condition}"
                )
            
            if len(filtered_variants) != len(valid_variants):
                self.logger.info(
                    f"Filtered out {len(valid_variants) - len(filtered_variants)} low-confidence variants for {condition}"
                )
            
            # Separate variants by effect direction with error handling
            risk_variants = []
            protective_variants = []
            
            for variant in filtered_variants:
                try:
                    if variant.is_risk_variant():
                        risk_variants.append(variant)
                    elif variant.is_protective_variant():
                        protective_variants.append(variant)
                except Exception as e:
                    self.logger.warning(f"Error checking variant {variant.rsid} effect direction: {e}")
            
            # Determine section visibility with fallback behavior
            show_risk_section = self.has_risk_variants(filtered_variants, condition)
            show_protective_section = self.has_protective_variants(filtered_variants, condition)
            
            # Handle edge case where no variants of any type exist
            if not show_risk_section and not show_protective_section and filtered_variants:
                self.logger.info(f"No risk or protective variants found for {condition}, but variants exist")
                # This might indicate classification issues - log for investigation
                unknown_variants = [v for v in filtered_variants 
                                  if v.effect_direction in [EffectDirection.UNKNOWN, EffectDirection.NEUTRAL]]
                if unknown_variants:
                    self.logger.info(f"Found {len(unknown_variants)} unknown/neutral variants for {condition}")
            
            # Calculate priority based on variant characteristics
            priority = self._calculate_section_priority(risk_variants, protective_variants)
            
            # Create section configuration with validation
            section_config = SectionConfig(
                show_risk_section=show_risk_section,
                show_protective_section=show_protective_section,
                risk_variant_count=len(risk_variants),
                protective_variant_count=len(protective_variants),
                section_priority=priority,
                condition_name=condition
            )
            
            # Set display order based on priority and content
            section_config.display_order = self._determine_section_order(
                risk_variants, protective_variants, priority
            )
            
            # Validate section configuration consistency
            validation_result = self._validate_section_config(section_config, filtered_variants)
            if not validation_result['is_valid']:
                self.logger.warning(f"Section configuration validation failed for {condition}: {validation_result['errors']}")
            
            # Validate variant inclusion completeness
            displayed_variants = risk_variants + protective_variants
            inclusion_validation = self._validate_variant_inclusion_completeness(
                valid_variants, displayed_variants, condition
            )
            
            if not inclusion_validation['is_complete']:
                self.logger.warning(
                    f"Variant inclusion validation failed for {condition}: "
                    f"{len(inclusion_validation['missing_variants'])} variants missing, "
                    f"inclusion rate: {inclusion_validation['inclusion_rate']:.1%}"
                )
                
                # Log details about unexpected exclusions
                if inclusion_validation['unexpected_exclusions']:
                    for exclusion in inclusion_validation['unexpected_exclusions']:
                        self.logger.error(
                            f"Unexpected exclusion for {condition}: {exclusion['rsid']} "
                            f"({exclusion['exclusion_reason']})"
                        )
            
            self.logger.info(
                f"Section analysis for {condition}: "
                f"Risk variants: {len(risk_variants)}, "
                f"Protective variants: {len(protective_variants)}, "
                f"Priority: {priority.value}, "
                f"Inclusion rate: {inclusion_validation['inclusion_rate']:.1%}"
            )
            
            return section_config
            
        except Exception as e:
            self.logger.error(f"Error determining sections for condition {condition}: {str(e)}", exc_info=True)
            # Return minimal configuration on error with fallback behavior
            return self._create_fallback_section_config(condition)
    
    def has_risk_variants(self, variants: List[EnhancedVariant], condition: str) -> bool:
        """
        Check if there are risk-increasing variants for a specific condition with enhanced error handling.
        
        This method evaluates whether the condition has any variants that
        increase disease risk and should trigger the display of risk sections.
        
        Args:
            variants: List of enhanced variants to analyze
            condition: Name of the condition being evaluated
            
        Returns:
            True if risk-increasing variants are present
            
        Requirements: 2.1, 2.3
        """
        # Handle edge cases with fallback behavior
        if not variants:
            self.logger.debug(f"No variants provided for risk check in condition {condition}")
            return False
        
        if not condition or not condition.strip():
            self.logger.warning("Empty condition name provided for risk variant check")
            return False
        
        try:
            # Filter by confidence level first with error handling
            filtered_variants = self._filter_variants_by_confidence(variants)
            
            if not filtered_variants:
                self.logger.debug(f"No variants passed confidence filter for condition {condition}")
                return False
            
            # Check for risk-increasing variants associated with this condition
            risk_variants = []
            
            for variant in filtered_variants:
                try:
                    if (variant.is_risk_variant() and 
                        self._variant_associated_with_condition(variant, condition)):
                        risk_variants.append(variant)
                except Exception as e:
                    self.logger.warning(f"Error checking variant {variant.rsid} for risk association with {condition}: {e}")
                    continue
            
            has_risk = len(risk_variants) > 0
            
            self.logger.debug(
                f"Risk variant check for {condition}: "
                f"Found {len(risk_variants)} risk variants out of {len(filtered_variants)} filtered variants (has_risk: {has_risk})"
            )
            
            return has_risk
            
        except Exception as e:
            self.logger.error(f"Error checking risk variants for {condition}: {str(e)}", exc_info=True)
            # Fallback behavior: return False to avoid showing empty sections
            return False
    
    def has_protective_variants(self, variants: List[EnhancedVariant], condition: str) -> bool:
        """
        Check if there are protective variants for a specific condition with enhanced error handling.
        
        This method evaluates whether the condition has any variants that
        provide protection against disease and should trigger the display
        of protective sections.
        
        Args:
            variants: List of enhanced variants to analyze
            condition: Name of the condition being evaluated
            
        Returns:
            True if protective variants are present
            
        Requirements: 2.2, 2.3
        """
        # Handle edge cases with fallback behavior
        if not variants:
            self.logger.debug(f"No variants provided for protective check in condition {condition}")
            return False
        
        if not condition or not condition.strip():
            self.logger.warning("Empty condition name provided for protective variant check")
            return False
        
        try:
            # Filter by confidence level first with error handling
            filtered_variants = self._filter_variants_by_confidence(variants)
            
            if not filtered_variants:
                self.logger.debug(f"No variants passed confidence filter for condition {condition}")
                return False
            
            # Check for protective variants associated with this condition
            protective_variants = []
            
            for variant in filtered_variants:
                try:
                    if (variant.is_protective_variant() and 
                        self._variant_associated_with_condition(variant, condition)):
                        protective_variants.append(variant)
                except Exception as e:
                    self.logger.warning(f"Error checking variant {variant.rsid} for protective association with {condition}: {e}")
                    continue
            
            has_protective = len(protective_variants) > 0
            
            self.logger.debug(
                f"Protective variant check for {condition}: "
                f"Found {len(protective_variants)} protective variants out of {len(filtered_variants)} filtered variants (has_protective: {has_protective})"
            )
            
            return has_protective
            
        except Exception as e:
            self.logger.error(f"Error checking protective variants for {condition}: {str(e)}", exc_info=True)
            # Fallback behavior: return False to avoid showing empty sections
            return False
    
    def evaluate_section_necessity_per_condition(self, 
                                               variants_by_condition: Dict[str, List[EnhancedVariant]]) -> Dict[str, SectionConfig]:
        """
        Evaluate section necessity for multiple conditions independently with enhanced error handling.
        
        This method processes multiple conditions and determines the section
        requirements for each one independently, as specified in the requirements.
        
        Args:
            variants_by_condition: Dictionary mapping condition names to variant lists
            
        Returns:
            Dictionary mapping condition names to their SectionConfig
            
        Requirements: 2.5 (evaluate each condition independently)
        """
        # Handle edge cases with fallback behavior
        if not variants_by_condition:
            self.logger.warning("Empty variants_by_condition dictionary provided")
            return {}
        
        if not isinstance(variants_by_condition, dict):
            self.logger.error(f"Invalid variants_by_condition type: {type(variants_by_condition)}")
            return {}
        
        condition_configs = {}
        successful_conditions = 0
        failed_conditions = 0
        empty_conditions = 0
        
        self.logger.info(f"Evaluating section necessity for {len(variants_by_condition)} conditions")
        
        for condition, variants in variants_by_condition.items():
            try:
                # Validate condition name
                if not condition or not isinstance(condition, str):
                    self.logger.warning(f"Invalid condition name: {condition}")
                    condition = str(condition) if condition else "Unknown Condition"
                
                # Validate variants list
                if variants is None:
                    self.logger.info(f"No variants provided for condition {condition}")
                    variants = []
                    empty_conditions += 1
                elif not isinstance(variants, list):
                    self.logger.error(f"Invalid variants type for condition {condition}: {type(variants)}")
                    variants = []
                    failed_conditions += 1
                
                config = self.determine_required_sections(variants, condition)
                condition_configs[condition] = config
                
                self.logger.info(
                    f"Condition {condition}: "
                    f"Risk section: {config.show_risk_section}, "
                    f"Protective section: {config.show_protective_section}, "
                    f"Variants: {len(variants) if variants else 0}"
                )
                
                successful_conditions += 1
                
            except Exception as e:
                self.logger.error(f"Error evaluating condition {condition}: {str(e)}", exc_info=True)
                # Add minimal config for failed conditions with fallback behavior
                condition_configs[condition] = self._create_fallback_section_config(condition)
                failed_conditions += 1
        
        # Log summary statistics
        self.logger.info(
            f"Section evaluation completed: {successful_conditions} successful, "
            f"{empty_conditions} empty, {failed_conditions} failed out of {len(variants_by_condition)} total conditions"
        )
        
        # Warn if high failure rate
        if failed_conditions > 0:
            failure_rate = failed_conditions / len(variants_by_condition)
            if failure_rate > 0.1:  # More than 10% failures
                self.logger.warning(f"High failure rate in condition evaluation: {failure_rate:.1%}")
        
        return condition_configs
    
    def get_section_priority_ordering(self, 
                                    section_configs: Dict[str, SectionConfig]) -> List[Tuple[str, SectionConfig]]:
        """
        Implement section priority and ordering logic.
        
        This method takes multiple condition configurations and returns them
        ordered by priority for display in the final report.
        
        Args:
            section_configs: Dictionary of condition names to SectionConfig objects
            
        Returns:
            List of (condition_name, SectionConfig) tuples ordered by priority
            
        Requirements: 2.4 (section priority and ordering logic)
        """
        try:
            # Convert to list of tuples for sorting
            condition_configs = list(section_configs.items())
            
            # Sort by priority (HIGH -> MEDIUM -> LOW) and then by variant count
            def sort_key(item):
                condition, config = item
                
                # Priority order (lower number = higher priority)
                priority_order = {
                    SectionPriority.HIGH: 1,
                    SectionPriority.MEDIUM: 2,
                    SectionPriority.LOW: 3
                }
                
                # Total variant count for secondary sorting
                total_variants = config.risk_variant_count + config.protective_variant_count
                
                # Conditions with both risk and protective variants get higher priority
                has_both_types = config.show_risk_section and config.show_protective_section
                both_types_bonus = 0 if has_both_types else 1
                
                return (
                    priority_order[config.section_priority],  # Primary: priority level
                    both_types_bonus,                         # Secondary: both types present
                    -total_variants,                          # Tertiary: variant count (descending)
                    condition                                 # Quaternary: alphabetical
                )
            
            sorted_configs = sorted(condition_configs, key=sort_key)
            
            self.logger.info(
                f"Section ordering determined for {len(sorted_configs)} conditions: "
                f"{[condition for condition, _ in sorted_configs]}"
            )
            
            return sorted_configs
            
        except Exception as e:
            self.logger.error(f"Error ordering sections: {str(e)}")
            # Return original order on error
            return list(section_configs.items())
    
    def analyze_condition_sections(self, variants: List[EnhancedVariant], 
                                 condition: str) -> ConditionSectionAnalysis:
        """
        Perform comprehensive analysis of section requirements for a condition.
        
        This method provides detailed analysis including variant categorization,
        confidence assessment, and section recommendations.
        
        Args:
            variants: List of variants for the condition
            condition: Name of the condition
            
        Returns:
            ConditionSectionAnalysis with detailed breakdown
        """
        try:
            # Validate and repair variants first
            valid_variants = self._validate_variant_objects(variants, condition)
            
            # Filter variants by confidence
            filtered_variants = self._filter_variants_by_confidence(valid_variants)
            
            # Categorize variants by effect direction
            risk_variants = [v for v in filtered_variants if v.is_risk_variant()]
            protective_variants = [v for v in filtered_variants if v.is_protective_variant()]
            neutral_variants = [v for v in filtered_variants 
                              if v.effect_direction in [EffectDirection.NEUTRAL, EffectDirection.UNKNOWN]]
            
            # Check for high-confidence variants
            has_high_confidence = any(v.has_high_confidence() for v in filtered_variants)
            
            # Determine recommended priority
            priority = self._calculate_section_priority(risk_variants, protective_variants)
            
            # Determine required sections
            required_sections = self._determine_required_section_types(
                risk_variants, protective_variants, neutral_variants
            )
            
            # Create inclusion report for debugging
            inclusion_report = self._create_variant_inclusion_report(
                condition, valid_variants, risk_variants + protective_variants
            )
            
            # Log inclusion report if there are issues
            if inclusion_report.get('inclusion_analysis', {}).get('inclusion_rate', 1.0) < 0.9:
                self.logger.warning(f"Low variant inclusion rate for {condition}: {inclusion_report}")
            
            return ConditionSectionAnalysis(
                condition=condition,
                risk_variants=risk_variants,
                protective_variants=protective_variants,
                neutral_variants=neutral_variants,
                total_variants=len(filtered_variants),
                has_high_confidence_variants=has_high_confidence,
                recommended_priority=priority,
                required_sections=required_sections
            )
            
        except Exception as e:
            self.logger.error(f"Error analyzing condition {condition}: {str(e)}", exc_info=True)
            return ConditionSectionAnalysis(
                condition=condition,
                risk_variants=[],
                protective_variants=[],
                neutral_variants=[],
                total_variants=0,
                has_high_confidence_variants=False,
                recommended_priority=SectionPriority.LOW,
                required_sections=set()
            )
    
    def create_variant_processing_summary(self, variants_by_condition: Dict[str, List[EnhancedVariant]]) -> Dict[str, Any]:
        """
        Create a comprehensive summary of variant processing across all conditions.
        
        This method provides detailed statistics and validation results for
        variant filtering and inclusion across all conditions.
        
        Args:
            variants_by_condition: Dictionary mapping conditions to variant lists
            
        Returns:
            Dictionary with comprehensive processing summary
        """
        summary = {
            'processing_timestamp': datetime.now().isoformat(),
            'total_conditions': len(variants_by_condition),
            'condition_summaries': {},
            'overall_statistics': {
                'total_input_variants': 0,
                'total_displayed_variants': 0,
                'overall_inclusion_rate': 0.0,
                'conditions_with_issues': 0,
                'common_exclusion_reasons': {}
            },
            'validation_issues': [],
            'recommendations': []
        }
        
        try:
            total_input = 0
            total_displayed = 0
            conditions_with_issues = 0
            
            for condition, variants in variants_by_condition.items():
                try:
                    # Process variants for this condition
                    valid_variants = self._validate_variant_objects(variants, condition)
                    filtered_variants = self._filter_variants_by_confidence(valid_variants)
                    
                    # Categorize variants
                    risk_variants = [v for v in filtered_variants if v.is_risk_variant()]
                    protective_variants = [v for v in filtered_variants if v.is_protective_variant()]
                    displayed_variants = risk_variants + protective_variants
                    
                    # Create inclusion report
                    inclusion_report = self._create_variant_inclusion_report(
                        condition, valid_variants, displayed_variants
                    )
                    
                    # Update totals
                    total_input += len(variants)
                    total_displayed += len(displayed_variants)
                    
                    # Check for issues
                    inclusion_rate = inclusion_report.get('inclusion_analysis', {}).get('inclusion_rate', 1.0)
                    has_issues = inclusion_rate < 0.9 or inclusion_report.get('inclusion_analysis', {}).get('unexpected_exclusions', [])
                    
                    if has_issues:
                        conditions_with_issues += 1
                    
                    # Store condition summary
                    summary['condition_summaries'][condition] = {
                        'input_variants': len(variants),
                        'valid_variants': len(valid_variants),
                        'displayed_variants': len(displayed_variants),
                        'inclusion_rate': inclusion_rate,
                        'has_issues': has_issues,
                        'risk_variants': len(risk_variants),
                        'protective_variants': len(protective_variants),
                        'inclusion_report': inclusion_report
                    }
                    
                except Exception as e:
                    self.logger.error(f"Error processing condition {condition} in summary: {e}")
                    conditions_with_issues += 1
                    summary['validation_issues'].append(f"Processing error for {condition}: {str(e)}")
            
            # Calculate overall statistics
            summary['overall_statistics']['total_input_variants'] = total_input
            summary['overall_statistics']['total_displayed_variants'] = total_displayed
            summary['overall_statistics']['overall_inclusion_rate'] = total_displayed / total_input if total_input > 0 else 1.0
            summary['overall_statistics']['conditions_with_issues'] = conditions_with_issues
            
            # Generate recommendations
            if summary['overall_statistics']['overall_inclusion_rate'] < 0.8:
                summary['recommendations'].append("Overall inclusion rate is low - review filtering criteria")
            
            if conditions_with_issues > len(variants_by_condition) * 0.2:
                summary['recommendations'].append("High number of conditions with processing issues - investigate data quality")
            
            if total_displayed == 0 and total_input > 0:
                summary['recommendations'].append("No variants displayed despite input data - check classification pipeline")
            
        except Exception as e:
            summary['error'] = f"Error generating processing summary: {str(e)}"
            self.logger.error(f"Error generating variant processing summary: {e}")
        
        return summary
    
    # Private helper methods
    
    def _filter_variants_by_confidence(self, variants: List[EnhancedVariant]) -> List[EnhancedVariant]:
        """Filter variants by minimum confidence level with enhanced error handling."""
        if not variants:
            return []
        
        confidence_order = {
            ConfidenceLevel.LOW: 1,
            ConfidenceLevel.MODERATE: 2,
            ConfidenceLevel.HIGH: 3
        }
        
        min_level = confidence_order[self.min_confidence_level]
        filtered_variants = []
        
        for variant in variants:
            try:
                # Validate confidence level exists and is valid
                if not hasattr(variant, 'confidence_level') or variant.confidence_level is None:
                    self.logger.warning(f"Variant {variant.rsid} missing confidence level, using LOW as fallback")
                    variant.confidence_level = ConfidenceLevel.LOW
                
                # Check if confidence level is in our mapping
                if variant.confidence_level not in confidence_order:
                    self.logger.warning(f"Variant {variant.rsid} has unknown confidence level {variant.confidence_level}, using LOW as fallback")
                    variant.confidence_level = ConfidenceLevel.LOW
                
                variant_level = confidence_order[variant.confidence_level]
                
                if variant_level >= min_level:
                    filtered_variants.append(variant)
                else:
                    self.logger.debug(f"Variant {variant.rsid} filtered out due to low confidence: {variant.confidence_level.value} < {self.min_confidence_level.value}")
                    
            except Exception as e:
                self.logger.error(f"Error filtering variant {getattr(variant, 'rsid', 'unknown')}: {e}")
                # Include variant with fallback behavior to avoid losing data
                if hasattr(variant, 'rsid'):
                    self.logger.info(f"Including variant {variant.rsid} despite filtering error to prevent data loss")
                    filtered_variants.append(variant)
        
        return filtered_variants
    
    def _variant_associated_with_condition(self, variant: EnhancedVariant, condition: str) -> bool:
        """Enhanced check if a variant is associated with a specific condition with fallback logic."""
        # Handle empty condition name
        if not condition or not condition.strip():
            self.logger.warning("Empty condition name provided for variant association check")
            return False
        
        # Handle missing condition associations with fallback
        if not hasattr(variant, 'condition_associations') or not variant.condition_associations:
            self.logger.debug(f"Variant {variant.rsid} has no condition associations, applying inclusive fallback")
            # Fallback: if no associations are specified, assume it could be relevant
            # This prevents variants from being excluded due to missing association data
            return True
            
        # Case-insensitive matching for condition associations
        condition_lower = condition.lower().strip()
        
        # Enhanced matching with multiple strategies
        for association in variant.condition_associations:
            if not association:
                continue
                
            association_lower = association.lower().strip()
            
            # Exact match
            if association_lower == condition_lower:
                return True
            
            # Partial matches (bidirectional)
            if condition_lower in association_lower or association_lower in condition_lower:
                return True
            
            # Handle common condition name variations
            condition_variations = self._get_condition_variations(condition_lower)
            association_variations = self._get_condition_variations(association_lower)
            
            # Check if any variations match
            if any(var in association_variations for var in condition_variations):
                return True
        
        return False
    
    def _get_condition_variations(self, condition: str) -> List[str]:
        """Get common variations of a condition name for matching."""
        variations = [condition]
        
        # Common condition name mappings
        condition_mappings = {
            'adhd': ['attention deficit hyperactivity disorder', 'attention deficit', 'hyperactivity'],
            'attention deficit hyperactivity disorder': ['adhd'],
            'diabetes': ['diabetes mellitus', 'type 2 diabetes', 't2d', 'dm'],
            'type 2 diabetes': ['diabetes', 't2d', 'diabetes mellitus'],
            'cardiovascular disease': ['cvd', 'heart disease', 'coronary artery disease'],
            'coronary artery disease': ['cad', 'cardiovascular disease', 'heart disease'],
            'alzheimer': ['alzheimers disease', 'alzheimer disease', 'ad'],
            'depression': ['major depressive disorder', 'mdd', 'depressive disorder']
        }
        
        # Add mapped variations
        if condition in condition_mappings:
            variations.extend(condition_mappings[condition])
        
        # Add variations for compound conditions
        if ' ' in condition:
            # Add individual words for compound conditions
            words = condition.split()
            variations.extend(words)
        
        return variations
    
    def _calculate_section_priority(self, risk_variants: List[EnhancedVariant], 
                                  protective_variants: List[EnhancedVariant]) -> SectionPriority:
        """Calculate section priority based on variant characteristics."""
        total_variants = len(risk_variants) + len(protective_variants)
        
        # Count high-confidence variants
        high_conf_risk = sum(1 for v in risk_variants if v.has_high_confidence())
        high_conf_protective = sum(1 for v in protective_variants if v.has_high_confidence())
        high_conf_total = high_conf_risk + high_conf_protective
        
        # Check if we have both risk and protective variants
        has_both_types = len(risk_variants) > 0 and len(protective_variants) > 0
        
        # Priority determination logic - enhanced to consider both types
        if high_conf_total >= 2 and has_both_types:
            return SectionPriority.HIGH
        elif high_conf_total >= 3 or (total_variants >= 5 and high_conf_total >= 2):
            return SectionPriority.HIGH
        elif high_conf_total >= 1 or total_variants >= 3 or has_both_types:
            return SectionPriority.MEDIUM
        else:
            return SectionPriority.LOW
    
    def _determine_section_order(self, risk_variants: List[EnhancedVariant], 
                               protective_variants: List[EnhancedVariant],
                               priority: SectionPriority) -> List[SectionType]:
        """Determine the display order of sections based on content and priority."""
        section_order = []
        
        # Always start with risk assessment if risk variants present
        if risk_variants:
            section_order.append(SectionType.RISK_ASSESSMENT)
        
        # Add protective factors if protective variants present
        if protective_variants:
            section_order.append(SectionType.PROTECTIVE_FACTORS)
        
        # Add other sections based on priority and content
        if priority == SectionPriority.HIGH:
            # High priority gets all sections
            remaining_sections = [
                SectionType.CLINICAL_IMPLICATIONS,
                SectionType.MUTATION_PROFILE,
                SectionType.LITERATURE_EVIDENCE,
                SectionType.LIFESTYLE_RECOMMENDATIONS
            ]
        elif priority == SectionPriority.MEDIUM:
            # Medium priority gets core sections
            remaining_sections = [
                SectionType.CLINICAL_IMPLICATIONS,
                SectionType.MUTATION_PROFILE,
                SectionType.LITERATURE_EVIDENCE
            ]
        else:
            # Low priority gets minimal sections
            remaining_sections = [
                SectionType.CLINICAL_IMPLICATIONS,
                SectionType.MUTATION_PROFILE
            ]
        
        # Add remaining sections that aren't already included
        for section in remaining_sections:
            if section not in section_order:
                section_order.append(section)
        
        return section_order
    
    def _determine_required_section_types(self, risk_variants: List[EnhancedVariant],
                                        protective_variants: List[EnhancedVariant],
                                        neutral_variants: List[EnhancedVariant]) -> Set[SectionType]:
        """Determine which section types are required based on variant content."""
        required_sections = set()
        
        # Always include mutation profile if any variants present
        if risk_variants or protective_variants or neutral_variants:
            required_sections.add(SectionType.MUTATION_PROFILE)
        
        # Add risk assessment if risk variants present
        if risk_variants:
            required_sections.add(SectionType.RISK_ASSESSMENT)
            required_sections.add(SectionType.CLINICAL_IMPLICATIONS)
        
        # Add protective factors if protective variants present
        if protective_variants:
            required_sections.add(SectionType.PROTECTIVE_FACTORS)
            required_sections.add(SectionType.CLINICAL_IMPLICATIONS)
        
        # Add literature evidence if high-confidence variants present
        if any(v.has_high_confidence() for v in risk_variants + protective_variants):
            required_sections.add(SectionType.LITERATURE_EVIDENCE)
        
        # Add lifestyle recommendations for actionable variants
        total_variants = len(risk_variants) + len(protective_variants)
        if total_variants >= 2:
            required_sections.add(SectionType.LIFESTYLE_RECOMMENDATIONS)
        
        return required_sections


# Utility functions for working with the SectionManager

def create_section_manager_with_config(min_confidence: ConfidenceLevel = ConfidenceLevel.MODERATE) -> SectionManager:
    """
    Create a SectionManager with specified configuration.
    
    Args:
        min_confidence: Minimum confidence level for variant inclusion
        
    Returns:
        Configured SectionManager instance
    """
    return SectionManager(min_confidence_level=min_confidence)


def analyze_multiple_conditions(section_manager: SectionManager,
                              variants_by_condition: Dict[str, List[EnhancedVariant]]) -> Dict[str, ConditionSectionAnalysis]:
    """
    Analyze section requirements for multiple conditions using a SectionManager.
    
    Args:
        section_manager: SectionManager instance to use
        variants_by_condition: Dictionary mapping conditions to variant lists
        
    Returns:
        Dictionary mapping conditions to their analysis results
    """
    analyses = {}
    
    for condition, variants in variants_by_condition.items():
        analyses[condition] = section_manager.analyze_condition_sections(variants, condition)
    
    return analyses


def get_display_ready_sections(section_manager: SectionManager,
                             variants_by_condition: Dict[str, List[EnhancedVariant]]) -> List[Tuple[str, SectionConfig]]:
    """
    Get section configurations ready for display, ordered by priority.
    
    Args:
        section_manager: SectionManager instance to use
        variants_by_condition: Dictionary mapping conditions to variant lists
        
    Returns:
        List of (condition, SectionConfig) tuples ordered by display priority
    """
    # Get section configurations for all conditions
    section_configs = section_manager.evaluate_section_necessity_per_condition(variants_by_condition)
    
    # Filter out conditions with no displayable sections
    displayable_configs = {
        condition: config for condition, config in section_configs.items()
        if config.show_risk_section or config.show_protective_section
    }
    
    # Return ordered by priority
    return section_manager.get_section_priority_ordering(displayable_configs)


# Enhanced error handling and validation methods for SectionManager

def _validate_variant_objects(self, variants: List[EnhancedVariant], condition: str) -> List[EnhancedVariant]:
    """
    Enhanced validation of variant objects with fallback mechanisms
    
    Args:
        variants: List of variant objects to validate
        condition: Condition name for logging context
        
    Returns:
        List of valid variant objects with fallback repairs applied
    """
    valid_variants = []
    validation_stats = {
        'total_input': len(variants),
        'repaired': 0,
        'excluded': 0,
        'valid': 0
    }
    
    for i, variant in enumerate(variants):
        try:
            # Check if it's an EnhancedVariant object
            if not hasattr(variant, 'rsid') or not hasattr(variant, 'effect_direction'):
                self.logger.warning(f"Invalid variant object at index {i} for condition {condition} - missing required attributes")
                validation_stats['excluded'] += 1
                continue
            
            # Check required fields with fallback repairs
            if not variant.rsid or not variant.rsid.strip():
                self.logger.warning(f"Variant at index {i} has empty rsid for condition {condition}")
                validation_stats['excluded'] += 1
                continue
            
            # Repair missing confidence level with fallback
            if not hasattr(variant, 'confidence_level') or variant.confidence_level is None:
                self.logger.warning(f"Variant {variant.rsid} missing confidence level for condition {condition}, applying fallback")
                variant.confidence_level = ConfidenceLevel.LOW
                validation_stats['repaired'] += 1
            
            # Repair invalid effect direction with fallback
            if not isinstance(variant.effect_direction, EffectDirection):
                self.logger.warning(f"Variant {variant.rsid} has invalid effect direction for condition {condition}, applying fallback")
                variant.effect_direction = EffectDirection.UNKNOWN
                validation_stats['repaired'] += 1
            
            # Repair missing gene information
            if not hasattr(variant, 'gene') or not variant.gene:
                self.logger.warning(f"Variant {variant.rsid} missing gene information for condition {condition}, applying fallback")
                variant.gene = "Unknown"
                validation_stats['repaired'] += 1
            
            # Repair missing condition associations
            if not hasattr(variant, 'condition_associations') or not variant.condition_associations:
                self.logger.warning(f"Variant {variant.rsid} missing condition associations for condition {condition}, applying fallback")
                variant.condition_associations = [condition]
                validation_stats['repaired'] += 1
            
            # Validate confidence score exists and is reasonable
            if not hasattr(variant, 'confidence_score') or variant.confidence_score is None:
                self.logger.warning(f"Variant {variant.rsid} missing confidence score, applying fallback")
                variant.confidence_score = 0.5  # Default moderate confidence
                validation_stats['repaired'] += 1
            elif not (0.0 <= variant.confidence_score <= 1.0):
                self.logger.warning(f"Variant {variant.rsid} has invalid confidence score {variant.confidence_score}, clamping to valid range")
                variant.confidence_score = max(0.0, min(1.0, variant.confidence_score))
                validation_stats['repaired'] += 1
            
            valid_variants.append(variant)
            validation_stats['valid'] += 1
            
        except Exception as e:
            self.logger.error(f"Error validating variant at index {i} for condition {condition}: {e}")
            validation_stats['excluded'] += 1
            continue
    
    # Log validation summary
    self.logger.info(
        f"Variant validation for {condition}: {validation_stats['valid']} valid, "
        f"{validation_stats['repaired']} repaired, {validation_stats['excluded']} excluded "
        f"out of {validation_stats['total_input']} total variants"
    )
    
    return valid_variants


def _validate_section_config(self, config: SectionConfig, variants: List[EnhancedVariant]) -> Dict[str, Any]:
    """
    Validate section configuration consistency
    
    Args:
        config: SectionConfig to validate
        variants: List of variants used to create the config
        
    Returns:
        Dictionary with validation results
    """
    validation_result = {
        'is_valid': True,
        'errors': [],
        'warnings': []
    }
    
    try:
        # Check consistency between section visibility and variant counts
        if config.show_risk_section and config.risk_variant_count == 0:
            validation_result['errors'].append("Risk section enabled but no risk variants counted")
            validation_result['is_valid'] = False
        
        if config.show_protective_section and config.protective_variant_count == 0:
            validation_result['errors'].append("Protective section enabled but no protective variants counted")
            validation_result['is_valid'] = False
        
        if not config.show_risk_section and config.risk_variant_count > 0:
            validation_result['warnings'].append("Risk variants present but risk section disabled")
        
        if not config.show_protective_section and config.protective_variant_count > 0:
            validation_result['warnings'].append("Protective variants present but protective section disabled")
        
        # Check variant count consistency
        actual_risk_count = sum(1 for v in variants if v.is_risk_variant())
        actual_protective_count = sum(1 for v in variants if v.is_protective_variant())
        
        if config.risk_variant_count != actual_risk_count:
            validation_result['errors'].append(
                f"Risk variant count mismatch: config={config.risk_variant_count}, actual={actual_risk_count}"
            )
            validation_result['is_valid'] = False
        
        if config.protective_variant_count != actual_protective_count:
            validation_result['errors'].append(
                f"Protective variant count mismatch: config={config.protective_variant_count}, actual={actual_protective_count}"
            )
            validation_result['is_valid'] = False
        
        # Check priority consistency
        total_variants = config.risk_variant_count + config.protective_variant_count
        if config.section_priority == SectionPriority.HIGH and total_variants == 0:
            validation_result['warnings'].append("High priority assigned with no variants")
        
        # Check display order consistency
        if hasattr(config, 'display_order') and config.display_order:
            if config.show_risk_section and SectionType.RISK_ASSESSMENT not in config.display_order:
                validation_result['warnings'].append("Risk section enabled but not in display order")
            
            if config.show_protective_section and SectionType.PROTECTIVE_FACTORS not in config.display_order:
                validation_result['warnings'].append("Protective section enabled but not in display order")
    
    except Exception as e:
        validation_result['errors'].append(f"Validation error: {str(e)}")
        validation_result['is_valid'] = False
    
    return validation_result


def _create_fallback_section_config(self, condition: str) -> SectionConfig:
    """
    Create a fallback section configuration for error cases
    
    Args:
        condition: Condition name
        
    Returns:
        Minimal SectionConfig with fallback values
    """
    return SectionConfig(
        show_risk_section=False,
        show_protective_section=False,
        risk_variant_count=0,
        protective_variant_count=0,
        section_priority=SectionPriority.LOW,
        condition_name=condition or "Unknown Condition"
    )


def _validate_variant_inclusion_completeness(self, input_variants: List[EnhancedVariant], 
                                           displayed_variants: List[EnhancedVariant],
                                           condition: str) -> Dict[str, Any]:
    """
    Validate that all expected variants are included in display with comprehensive checking
    
    Args:
        input_variants: Original list of variants provided for processing
        displayed_variants: List of variants that will be displayed
        condition: Condition name for context
        
    Returns:
        Dictionary with validation results and missing variant details
    """
    validation_result = {
        'is_complete': True,
        'missing_variants': [],
        'unexpected_exclusions': [],
        'inclusion_rate': 0.0,
        'warnings': [],
        'errors': []
    }
    
    try:
        if not input_variants:
            validation_result['inclusion_rate'] = 1.0
            return validation_result
        
        # Create sets for efficient comparison
        input_rsids = {v.rsid for v in input_variants if hasattr(v, 'rsid') and v.rsid}
        displayed_rsids = {v.rsid for v in displayed_variants if hasattr(v, 'rsid') and v.rsid}
        
        # Find missing variants
        missing_rsids = input_rsids - displayed_rsids
        
        if missing_rsids:
            validation_result['is_complete'] = False
            
            # Analyze why variants are missing
            for rsid in missing_rsids:
                missing_variant = next((v for v in input_variants if v.rsid == rsid), None)
                if missing_variant:
                    exclusion_reason = self._analyze_variant_exclusion_reason(missing_variant, condition)
                    
                    missing_info = {
                        'rsid': rsid,
                        'gene': getattr(missing_variant, 'gene', 'Unknown'),
                        'effect_direction': getattr(missing_variant, 'effect_direction', EffectDirection.UNKNOWN),
                        'confidence_level': getattr(missing_variant, 'confidence_level', ConfidenceLevel.LOW),
                        'exclusion_reason': exclusion_reason,
                        'should_be_included': exclusion_reason in ['processing_error', 'unexpected_filter']
                    }
                    
                    validation_result['missing_variants'].append(missing_info)
                    
                    # Flag unexpected exclusions
                    if exclusion_reason in ['processing_error', 'unexpected_filter']:
                        validation_result['unexpected_exclusions'].append(missing_info)
                        validation_result['errors'].append(f"Variant {rsid} unexpectedly excluded: {exclusion_reason}")
                    else:
                        validation_result['warnings'].append(f"Variant {rsid} excluded: {exclusion_reason}")
        
        # Calculate inclusion rate
        validation_result['inclusion_rate'] = len(displayed_rsids) / len(input_rsids) if input_rsids else 1.0
        
        # Log validation summary
        self.logger.info(
            f"Variant inclusion validation for {condition}: "
            f"{len(displayed_rsids)}/{len(input_rsids)} variants included "
            f"({validation_result['inclusion_rate']:.1%} inclusion rate)"
        )
        
        if validation_result['unexpected_exclusions']:
            self.logger.error(
                f"Found {len(validation_result['unexpected_exclusions'])} unexpected variant exclusions for {condition}"
            )
        
    except Exception as e:
        validation_result['errors'].append(f"Validation error: {str(e)}")
        self.logger.error(f"Error validating variant inclusion for {condition}: {e}")
    
    return validation_result


def _analyze_variant_exclusion_reason(self, variant: EnhancedVariant, condition: str) -> str:
    """
    Analyze why a variant might have been excluded from display
    
    Args:
        variant: The excluded variant
        condition: Condition name
        
    Returns:
        String describing the likely exclusion reason
    """
    try:
        # Check confidence level
        if hasattr(variant, 'confidence_level'):
            confidence_order = {
                ConfidenceLevel.LOW: 1,
                ConfidenceLevel.MODERATE: 2,
                ConfidenceLevel.HIGH: 3
            }
            min_level = confidence_order[self.min_confidence_level]
            variant_level = confidence_order.get(variant.confidence_level, 0)
            
            if variant_level < min_level:
                return f"low_confidence ({variant.confidence_level.value} < {self.min_confidence_level.value})"
        
        # Check condition association
        if not self._variant_associated_with_condition(variant, condition):
            return "condition_mismatch"
        
        # Check effect direction
        if not hasattr(variant, 'effect_direction') or variant.effect_direction == EffectDirection.UNKNOWN:
            return "unknown_effect_direction"
        
        # Check for missing required fields
        required_fields = ['rsid', 'gene', 'effect_direction', 'confidence_level']
        missing_fields = [field for field in required_fields if not hasattr(variant, field) or getattr(variant, field) is None]
        
        if missing_fields:
            return f"missing_required_fields ({', '.join(missing_fields)})"
        
        # If we can't determine why it was excluded, it might be a processing error
        return "processing_error"
        
    except Exception as e:
        return f"analysis_error ({str(e)})"


def _create_variant_inclusion_report(self, condition: str, input_variants: List[EnhancedVariant],
                                   displayed_variants: List[EnhancedVariant]) -> Dict[str, Any]:
    """
    Create a comprehensive report of variant inclusion for debugging and validation
    
    Args:
        condition: Condition name
        input_variants: Original variants provided
        displayed_variants: Variants that will be displayed
        
    Returns:
        Dictionary with detailed inclusion report
    """
    report = {
        'condition': condition,
        'timestamp': datetime.now().isoformat(),
        'input_summary': {
            'total_variants': len(input_variants),
            'by_effect_direction': {},
            'by_confidence_level': {}
        },
        'displayed_summary': {
            'total_variants': len(displayed_variants),
            'by_effect_direction': {},
            'by_confidence_level': {}
        },
        'inclusion_analysis': {},
        'recommendations': []
    }
    
    try:
        # Analyze input variants
        for variant in input_variants:
            if hasattr(variant, 'effect_direction'):
                direction = variant.effect_direction.value
                report['input_summary']['by_effect_direction'][direction] = \
                    report['input_summary']['by_effect_direction'].get(direction, 0) + 1
            
            if hasattr(variant, 'confidence_level'):
                confidence = variant.confidence_level.value
                report['input_summary']['by_confidence_level'][confidence] = \
                    report['input_summary']['by_confidence_level'].get(confidence, 0) + 1
        
        # Analyze displayed variants
        for variant in displayed_variants:
            if hasattr(variant, 'effect_direction'):
                direction = variant.effect_direction.value
                report['displayed_summary']['by_effect_direction'][direction] = \
                    report['displayed_summary']['by_effect_direction'].get(direction, 0) + 1
            
            if hasattr(variant, 'confidence_level'):
                confidence = variant.confidence_level.value
                report['displayed_summary']['by_confidence_level'][confidence] = \
                    report['displayed_summary']['by_confidence_level'].get(confidence, 0) + 1
        
        # Perform inclusion validation
        validation_result = self._validate_variant_inclusion_completeness(
            input_variants, displayed_variants, condition
        )
        report['inclusion_analysis'] = validation_result
        
        # Generate recommendations
        if validation_result['inclusion_rate'] < 0.8:
            report['recommendations'].append("Low inclusion rate detected - review filtering criteria")
        
        if validation_result['unexpected_exclusions']:
            report['recommendations'].append("Unexpected exclusions found - investigate processing pipeline")
        
        if not displayed_variants and input_variants:
            report['recommendations'].append("No variants displayed despite input variants - check classification and filtering")
        
    except Exception as e:
        report['error'] = f"Error generating inclusion report: {str(e)}"
        self.logger.error(f"Error generating variant inclusion report for {condition}: {e}")
    
    return report


# Add these methods to the SectionManager class
SectionManager._validate_variant_objects = _validate_variant_objects
SectionManager._validate_section_config = _validate_section_config
SectionManager._create_fallback_section_config = _create_fallback_section_config
SectionManager._validate_variant_inclusion_completeness = _validate_variant_inclusion_completeness
SectionManager._analyze_variant_exclusion_reason = _analyze_variant_exclusion_reason
SectionManager._create_variant_inclusion_report = _create_variant_inclusion_report