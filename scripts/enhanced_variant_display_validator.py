"""
Enhanced Variant Display Validator with Statistics Integration

This module extends the existing variant display validator with comprehensive
statistics tracking and validation capabilities as required by task 8.

Integrates with variant_display_statistics.py to provide complete validation
and statistics tracking for variant display outcomes.

Requirements: 1.3, 1.5, 5.1
"""

import time
from typing import Dict, List, Optional, Set, Any, Tuple
import logging

# Import existing components
from variant_display_validator import VariantDisplayValidator as BaseValidator
from variant_display_statistics import (
    VariantDisplayResult, DisplayStatistics, VariantExclusion, ValidationIssue,
    VariantDisplayStatisticsGenerator, VariantDisplayWarningSystem,
    ValidationSeverity, ExclusionReason
)
from enhanced_data_models import EnhancedVariant, SectionConfig
from variant_classifier import EffectDirection, ConfidenceLevel


class EnhancedVariantDisplayValidator(BaseValidator):
    """
    Enhanced validator that integrates comprehensive statistics tracking
    and validation capabilities for variant display outcomes.
    
    This class extends the base validator with the specific requirements
    from task 8: statistics generation, validation checks, and warning systems.
    
    Requirements: 1.3, 1.5, 5.1
    """
    
    def __init__(self, 
                 min_confidence_level: ConfidenceLevel = ConfidenceLevel.MODERATE,
                 enable_detailed_logging: bool = True,
                 warning_thresholds: Optional[Dict[str, float]] = None):
        """
        Initialize the enhanced variant display validator.
        
        Args:
            min_confidence_level: Minimum confidence level for variant inclusion
            enable_detailed_logging: Whether to enable detailed validation logging
            warning_thresholds: Custom thresholds for warning system
        """
        super().__init__(min_confidence_level, enable_detailed_logging)
        
        # Initialize statistics and warning systems
        self.stats_generator = VariantDisplayStatisticsGenerator(self.logger)
        self.warning_system = VariantDisplayWarningSystem(self.logger, warning_thresholds)
        
        # Enhanced validation statistics
        self.enhanced_stats = {
            'total_validations_with_stats': 0,
            'total_warnings_generated': 0,
            'total_missing_variants_detected': 0,
            'total_exclusions_tracked': 0,
            'average_processing_time_ms': 0.0
        }
    
    def validate_variant_display_with_statistics(self,
                                               input_variants: List[EnhancedVariant],
                                               displayed_variants: List[EnhancedVariant],
                                               condition: str,
                                               section_config: Optional[SectionConfig] = None) -> VariantDisplayResult:
        """
        Enhanced validation with comprehensive statistics tracking.
        
        This method performs all validation checks from the base class plus
        generates detailed statistics and warnings as required by task 8.
        
        Args:
            input_variants: Original list of variants for the condition
            displayed_variants: Variants that are actually displayed
            condition: Name of the condition being validated
            section_config: Optional section configuration for additional validation
            
        Returns:
            Enhanced VariantDisplayResult with comprehensive statistics
            
        Requirements: 1.3, 1.5, 5.1
        """
        start_time = time.time()
        
        try:
            # Perform base validation
            base_result = self.validate_variant_display(
                input_variants, displayed_variants, condition, section_config
            )
            
            # Detect missing variants using enhanced logic
            missing_variants = self._detect_missing_variants_enhanced(
                input_variants or [], displayed_variants or [], condition
            )
            
            # Create enhanced exclusions list
            excluded_variants = self._create_enhanced_exclusions(
                input_variants or [], displayed_variants or [], condition
            )
            
            # Generate comprehensive statistics
            display_stats = self.stats_generator.generate_display_statistics(
                condition=condition,
                input_variants=input_variants or [],
                displayed_variants=displayed_variants or [],
                excluded_variants=excluded_variants,
                missing_variants=missing_variants
            )
            
            # Calculate processing time
            processing_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            
            # Create enhanced result
            enhanced_result = VariantDisplayResult(
                condition=condition,
                input_variants=input_variants or [],
                displayed_variants=displayed_variants or [],
                excluded_variants=excluded_variants,
                missing_variants=missing_variants,
                validation_issues=base_result.validation_issues,
                display_statistics=display_stats,
                validation_passed=base_result.validation_passed and len(missing_variants) == 0,
                processing_duration_ms=processing_time,
                validator_config={
                    'min_confidence_level': self.min_confidence_level.value,
                    'detailed_logging_enabled': self.enable_detailed_logging
                }
            )
            
            # Generate warnings
            warnings = self.warning_system.check_display_warnings(enhanced_result)
            enhanced_result.validation_issues.extend(warnings)
            
            # Update validation status based on warnings
            if any(w.severity == ValidationSeverity.CRITICAL for w in warnings):
                enhanced_result.validation_passed = False
            
            # Update enhanced statistics
            self._update_enhanced_statistics(enhanced_result, processing_time)
            
            # Log comprehensive results
            self._log_enhanced_validation_results(enhanced_result)
            
            return enhanced_result
            
        except Exception as e:
            processing_time = (time.time() - start_time) * 1000
            self.logger.error(f"Enhanced validation failed for {condition}: {str(e)}", exc_info=True)
            
            # Return error result with minimal statistics
            error_stats = DisplayStatistics(
                condition=condition,
                total_input_variants=len(input_variants) if input_variants else 0,
                total_displayed_variants=len(displayed_variants) if displayed_variants else 0,
                total_excluded_variants=0,
                total_missing_variants=0
            )
            
            return VariantDisplayResult(
                condition=condition,
                input_variants=input_variants or [],
                displayed_variants=displayed_variants or [],
                excluded_variants=[],
                missing_variants=[],
                validation_issues=[ValidationIssue(
                    severity=ValidationSeverity.CRITICAL,
                    issue_type="enhanced_validation_error",
                    variant_id=None,
                    condition=condition,
                    message=f"Enhanced validation failed: {str(e)}"
                )],
                display_statistics=error_stats,
                validation_passed=False,
                processing_duration_ms=processing_time
            )
    
    def compare_input_with_displayed_variants(self,
                                            input_variants: List[EnhancedVariant],
                                            displayed_variants: List[EnhancedVariant],
                                            condition: str) -> Dict[str, Any]:
        """
        Create detailed comparison between input and displayed variants.
        
        This method provides comprehensive analysis of which variants were
        included, excluded, or missing from the display.
        
        Args:
            input_variants: Original input variants
            displayed_variants: Variants that were displayed
            condition: Name of the condition
            
        Returns:
            Dictionary with detailed comparison analysis
            
        Requirements: 1.3, 1.5
        """
        try:
            comparison = {
                'condition': condition,
                'input_count': len(input_variants),
                'displayed_count': len(displayed_variants),
                'comparison_details': {
                    'correctly_displayed': [],
                    'incorrectly_displayed': [],
                    'missing_variants': [],
                    'duplicate_variants': []
                },
                'statistics': {
                    'match_rate': 0.0,
                    'missing_rate': 0.0,
                    'incorrect_inclusion_rate': 0.0
                }
            }
            
            # Create sets for efficient comparison
            input_rsids = {v.rsid: v for v in input_variants}
            displayed_rsids = {v.rsid: v for v in displayed_variants}
            
            # Find correctly displayed variants
            for rsid, variant in displayed_rsids.items():
                if rsid in input_rsids:
                    input_variant = input_rsids[rsid]
                    if self._should_variant_be_displayed(input_variant, condition):
                        comparison['comparison_details']['correctly_displayed'].append({
                            'rsid': rsid,
                            'gene': variant.gene,
                            'effect_direction': variant.effect_direction.value,
                            'confidence_level': variant.confidence_level.value
                        })
                    else:
                        comparison['comparison_details']['incorrectly_displayed'].append({
                            'rsid': rsid,
                            'gene': variant.gene,
                            'reason': 'Should not be displayed based on inclusion criteria'
                        })
                else:
                    comparison['comparison_details']['incorrectly_displayed'].append({
                        'rsid': rsid,
                        'gene': variant.gene,
                        'reason': 'Not found in input variants'
                    })
            
            # Find missing variants
            for rsid, variant in input_rsids.items():
                if rsid not in displayed_rsids and self._should_variant_be_displayed(variant, condition):
                    comparison['comparison_details']['missing_variants'].append({
                        'rsid': rsid,
                        'gene': variant.gene,
                        'effect_direction': variant.effect_direction.value,
                        'confidence_level': variant.confidence_level.value,
                        'reason': 'Meets inclusion criteria but not displayed'
                    })
            
            # Check for duplicates in displayed variants
            rsid_counts = {}
            for variant in displayed_variants:
                rsid_counts[variant.rsid] = rsid_counts.get(variant.rsid, 0) + 1
            
            for rsid, count in rsid_counts.items():
                if count > 1:
                    comparison['comparison_details']['duplicate_variants'].append({
                        'rsid': rsid,
                        'count': count
                    })
            
            # Calculate statistics
            correctly_displayed_count = len(comparison['comparison_details']['correctly_displayed'])
            missing_count = len(comparison['comparison_details']['missing_variants'])
            incorrect_count = len(comparison['comparison_details']['incorrectly_displayed'])
            
            if len(input_variants) > 0:
                comparison['statistics']['match_rate'] = correctly_displayed_count / len(input_variants)
                comparison['statistics']['missing_rate'] = missing_count / len(input_variants)
            
            if len(displayed_variants) > 0:
                comparison['statistics']['incorrect_inclusion_rate'] = incorrect_count / len(displayed_variants)
            
            self.logger.info(f"Variant comparison for {condition}: "
                           f"{correctly_displayed_count} correct, "
                           f"{missing_count} missing, "
                           f"{incorrect_count} incorrect")
            
            return comparison
            
        except Exception as e:
            self.logger.error(f"Error comparing variants for {condition}: {str(e)}")
            return {
                'condition': condition,
                'error': f'Comparison failed: {str(e)}',
                'input_count': len(input_variants) if input_variants else 0,
                'displayed_count': len(displayed_variants) if displayed_variants else 0
            }
    
    def generate_validation_summary_report(self, results: List[VariantDisplayResult]) -> str:
        """
        Generate a comprehensive validation summary report.
        
        Args:
            results: List of validation results
            
        Returns:
            Human-readable summary report
            
        Requirements: 1.5, 5.1
        """
        try:
            if not results:
                return "No validation results to summarize."
            
            # Generate summary using statistics generator
            summary = self.stats_generator.create_validation_summary(results)
            missing_report = self.stats_generator.generate_missing_variants_report(results)
            
            # Create formatted report
            lines = [
                "VARIANT DISPLAY VALIDATION SUMMARY REPORT",
                "=" * 50,
                f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                "OVERVIEW:",
                f"  Total conditions validated: {summary['total_conditions']}",
                f"  Successful validations: {summary['successful_validations']}",
                f"  Failed validations: {summary['failed_validations']}",
                f"  Success rate: {summary['successful_validations']/summary['total_conditions']:.1%}",
                "",
                "VARIANT STATISTICS:",
                f"  Total variants processed: {summary['total_variants_processed']}",
                f"  Total variants displayed: {summary['total_variants_displayed']}",
                f"  Total variants excluded: {summary['total_variants_excluded']}",
                f"  Total missing variants: {summary['total_missing_variants']}",
                ""
            ]
            
            if 'overall_statistics' in summary:
                lines.extend([
                    "OVERALL RATES:",
                    f"  Display rate: {summary['overall_statistics']['display_rate']:.1%}",
                    f"  Exclusion rate: {summary['overall_statistics']['exclusion_rate']:.1%}",
                    f"  Missing rate: {summary['overall_statistics']['missing_rate']:.1%}",
                    ""
                ])
            
            if summary['issue_summary']['total_issues'] > 0:
                lines.extend([
                    "VALIDATION ISSUES:",
                    f"  Total issues found: {summary['issue_summary']['total_issues']}",
                    "  By severity:"
                ])
                for severity, count in summary['issue_summary']['by_severity'].items():
                    lines.append(f"    {severity.upper()}: {count}")
                lines.append("")
            
            if summary['exclusion_summary']:
                lines.extend([
                    "EXCLUSION REASONS:",
                ])
                for reason, count in summary['exclusion_summary'].items():
                    lines.append(f"  {reason}: {count} variants")
                lines.append("")
            
            if missing_report['total_missing_variants'] > 0:
                lines.extend([
                    "MISSING VARIANTS ANALYSIS:",
                    f"  Total missing variants: {missing_report['total_missing_variants']}",
                    f"  Conditions with missing variants: {len(missing_report['conditions_with_missing'])}",
                    ""
                ])
                
                if missing_report['missing_by_effect_direction']:
                    lines.append("  Missing by effect direction:")
                    for effect, count in missing_report['missing_by_effect_direction'].items():
                        lines.append(f"    {effect}: {count}")
                    lines.append("")
            
            if summary['conditions_with_issues']:
                lines.extend([
                    "CONDITIONS WITH ISSUES:",
                ])
                for condition_info in summary['conditions_with_issues']:
                    lines.append(f"  {condition_info['condition']}: "
                               f"{condition_info['issue_count']} issues, "
                               f"{condition_info['missing_variants']} missing variants")
                lines.append("")
            
            if 'performance_metrics' in summary and summary['performance_metrics']:
                lines.extend([
                    "PERFORMANCE METRICS:",
                    f"  Average processing time: {summary['performance_metrics']['average_processing_time_ms']:.1f}ms",
                    f"  Max processing time: {summary['performance_metrics']['max_processing_time_ms']:.1f}ms",
                    f"  Min processing time: {summary['performance_metrics']['min_processing_time_ms']:.1f}ms",
                    ""
                ])
            
            return "\n".join(lines)
            
        except Exception as e:
            self.logger.error(f"Error generating validation summary report: {str(e)}")
            return f"Error generating summary report: {str(e)}"
    
    def get_enhanced_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive statistics including base and enhanced metrics.
        
        Returns:
            Dictionary with all validation statistics
            
        Requirements: 5.1
        """
        base_stats = self.get_validation_statistics()
        warning_summary = self.warning_system.get_warning_summary()
        
        return {
            'base_validation_stats': base_stats,
            'enhanced_stats': self.enhanced_stats,
            'warning_summary': warning_summary,
            'combined_metrics': {
                'total_validations': base_stats['total_validations'],
                'enhanced_validations': self.enhanced_stats['total_validations_with_stats'],
                'total_warnings': self.enhanced_stats['total_warnings_generated'],
                'average_processing_time_ms': self.enhanced_stats['average_processing_time_ms']
            }
        }
    
    # Private helper methods for enhanced functionality
    
    def _detect_missing_variants_enhanced(self,
                                        input_variants: List[EnhancedVariant],
                                        displayed_variants: List[EnhancedVariant],
                                        condition: str) -> List[EnhancedVariant]:
        """Enhanced missing variant detection with detailed logging"""
        missing_variants = []
        displayed_rsids = {v.rsid for v in displayed_variants}
        
        for variant in input_variants:
            if self._should_variant_be_displayed(variant, condition):
                if variant.rsid not in displayed_rsids:
                    missing_variants.append(variant)
                    
                    if self.enable_detailed_logging:
                        self.logger.warning(
                            f"Missing variant detected: {variant.rsid} ({variant.gene}) "
                            f"for {condition} - Effect: {variant.effect_direction.value}, "
                            f"Confidence: {variant.confidence_level.value}"
                        )
        
        return missing_variants
    
    def _create_enhanced_exclusions(self,
                                  input_variants: List[EnhancedVariant],
                                  displayed_variants: List[EnhancedVariant],
                                  condition: str) -> List[VariantExclusion]:
        """Create detailed exclusion records for variants not displayed"""
        exclusions = []
        displayed_rsids = {v.rsid for v in displayed_variants}
        
        for variant in input_variants:
            if variant.rsid not in displayed_rsids:
                # Determine exclusion reason
                if not self._variant_associated_with_condition(variant, condition):
                    reason = ExclusionReason.CONDITION_MISMATCH
                    details = f"Variant not associated with condition {condition}"
                elif variant.effect_direction == EffectDirection.UNKNOWN:
                    reason = ExclusionReason.UNKNOWN_EFFECT
                    details = "Variant has unknown effect direction"
                elif not self._meets_confidence_threshold(variant):
                    reason = ExclusionReason.LOW_CONFIDENCE
                    details = f"Confidence level {variant.confidence_level.value} below threshold"
                else:
                    reason = ExclusionReason.PROCESSING_ERROR
                    details = "Variant excluded for unknown reason"
                
                exclusions.append(VariantExclusion(
                    variant=variant,
                    reason=reason,
                    details=details,
                    condition=condition
                ))
        
        return exclusions
    
    def _meets_confidence_threshold(self, variant: EnhancedVariant) -> bool:
        """Check if variant meets minimum confidence threshold"""
        confidence_order = {
            ConfidenceLevel.LOW: 1,
            ConfidenceLevel.MODERATE: 2,
            ConfidenceLevel.HIGH: 3
        }
        
        min_level = confidence_order[self.min_confidence_level]
        variant_level = confidence_order[variant.confidence_level]
        
        return variant_level >= min_level
    
    def _update_enhanced_statistics(self, result: VariantDisplayResult, processing_time: float):
        """Update enhanced validation statistics"""
        self.enhanced_stats['total_validations_with_stats'] += 1
        self.enhanced_stats['total_warnings_generated'] += len([
            issue for issue in result.validation_issues 
            if issue.severity == ValidationSeverity.WARNING
        ])
        self.enhanced_stats['total_missing_variants_detected'] += len(result.missing_variants)
        self.enhanced_stats['total_exclusions_tracked'] += len(result.excluded_variants)
        
        # Update average processing time
        total_validations = self.enhanced_stats['total_validations_with_stats']
        current_avg = self.enhanced_stats['average_processing_time_ms']
        self.enhanced_stats['average_processing_time_ms'] = (
            (current_avg * (total_validations - 1) + processing_time) / total_validations
        )
    
    def _log_enhanced_validation_results(self, result: VariantDisplayResult):
        """Log comprehensive validation results"""
        self.logger.info(
            f"Enhanced validation completed for {result.condition}: "
            f"Displayed: {len(result.displayed_variants)}/{len(result.input_variants)}, "
            f"Missing: {len(result.missing_variants)}, "
            f"Excluded: {len(result.excluded_variants)}, "
            f"Issues: {len(result.validation_issues)}, "
            f"Passed: {result.validation_passed}, "
            f"Processing time: {result.processing_duration_ms:.1f}ms"
        )
        
        if result.missing_variants and self.enable_detailed_logging:
            missing_rsids = [v.rsid for v in result.missing_variants]
            self.logger.warning(f"Missing variants for {result.condition}: {missing_rsids}")
        
        critical_issues = result.get_critical_issues()
        if critical_issues:
            self.logger.error(f"Critical issues found for {result.condition}: "
                            f"{[issue.message for issue in critical_issues]}")