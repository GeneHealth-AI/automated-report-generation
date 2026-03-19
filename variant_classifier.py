"""
Variant Classification System for Risk/Protective Genetic Variant Reporting

This module provides the foundation for classifying genetic variants as either
risk-increasing, protective, or neutral based on various data sources and evidence.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
import logging
import json
import os


class EffectDirection(Enum):
    """Enumeration for variant effect directions"""
    RISK_INCREASING = "risk_increasing"
    PROTECTIVE = "protective"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


class ConfidenceLevel(Enum):
    """Enumeration for classification confidence levels"""
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"


@dataclass
class VariantClassification:
    """Result of variant classification"""
    effect_direction: EffectDirection
    confidence_level: ConfidenceLevel
    confidence_score: float
    evidence_sources: List[str]
    reasoning: str


@dataclass
class ClassificationConfig:
    """Configuration for variant classification thresholds and rules"""
    risk_thresholds: Dict[str, float]
    protective_thresholds: Dict[str, float]
    confidence_weights: Dict[str, float]
    evidence_source_priorities: Dict[str, int]
    default_classification: EffectDirection
    
    @classmethod
    def get_default_config(cls) -> 'ClassificationConfig':
        """Get default classification configuration"""
        return cls(
            risk_thresholds={
                'clinvar_pathogenic': 0.8,
                'literature_risk': 0.6,
                'population_frequency_rare_risk': 0.7
            },
            protective_thresholds={
                'literature_protective': 0.6,
                'population_frequency_common_protective': 0.7
            },
            confidence_weights={
                'clinvar': 0.4,
                'literature': 0.3,
                'population_data': 0.2,
                'functional_prediction': 0.1
            },
            evidence_source_priorities={
                'clinvar': 1,
                'literature': 2,
                'population_data': 3,
                'functional_prediction': 4
            },
            default_classification=EffectDirection.UNKNOWN
        )
    
    @classmethod
    def load_from_file(cls, config_path: str) -> 'ClassificationConfig':
        """
        Load classification configuration from JSON file
        
        Args:
            config_path: Path to the JSON configuration file
        
        Returns:
            ClassificationConfig object loaded from file
        
        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config file is invalid
        """
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        try:
            with open(config_path, 'r') as f:
                config_data = json.load(f)
            
            # Convert string default_classification to enum
            default_classification_str = config_data.get('default_classification', 'unknown')
            default_classification = EffectDirection(default_classification_str)
            
            return cls(
                risk_thresholds=config_data.get('risk_thresholds', {}),
                protective_thresholds=config_data.get('protective_thresholds', {}),
                confidence_weights=config_data.get('confidence_weights', {}),
                evidence_source_priorities=config_data.get('evidence_source_priorities', {}),
                default_classification=default_classification
            )
        
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            raise ValueError(f"Invalid configuration file format: {str(e)}")
    
    def save_to_file(self, config_path: str) -> None:
        """
        Save classification configuration to JSON file
        
        Args:
            config_path: Path where to save the configuration file
        """
        config_data = {
            'risk_thresholds': self.risk_thresholds,
            'protective_thresholds': self.protective_thresholds,
            'confidence_weights': self.confidence_weights,
            'evidence_source_priorities': self.evidence_source_priorities,
            'default_classification': self.default_classification.value
        }
        
        with open(config_path, 'w') as f:
            json.dump(config_data, f, indent=2)


class VariantClassifier:
    """
    Main class for classifying genetic variants as risk-increasing, protective, or neutral
    """
    
    def __init__(self, config: Optional[ClassificationConfig] = None):
        """
        Initialize the variant classifier
        
        Args:
            config: Classification configuration, uses default if None
        """
        self.config = config or ClassificationConfig.get_default_config()
        self.logger = logging.getLogger(__name__)
    
    def classify_variant(self, variant_data: Dict[str, Any]) -> VariantClassification:
        """
        Classify a genetic variant based on available evidence with enhanced error handling
        
        Args:
            variant_data: Dictionary containing variant information including:
                - rsid: Variant identifier
                - gene: Associated gene
                - clinvar_significance: ClinVar pathogenicity classification
                - literature_evidence: Literature-based evidence
                - population_frequency: Population frequency data
                - functional_impact: Predicted functional impact
        
        Returns:
            VariantClassification object with effect direction and confidence
        """
        # Enhanced input validation
        if not variant_data:
            self.logger.warning("Empty variant data provided for classification")
            return self._create_fallback_classification("Empty variant data")
        
        rsid = variant_data.get('rsid', 'unknown')
        
        # Validate required fields
        validation_errors = self._validate_variant_data(variant_data)
        if validation_errors:
            self.logger.warning(f"Variant {rsid} has validation errors: {validation_errors}")
            # Continue with classification but log warnings
        
        try:
            # Extract evidence from variant data with error handling
            evidence = self._extract_evidence_with_validation(variant_data)
            
            # Handle case where no evidence is available
            if not evidence:
                self.logger.info(f"No evidence available for variant {rsid}, using unknown classification")
                return self._create_unknown_classification(rsid, "No evidence available")
            
            # Determine effect direction based on evidence
            effect_direction = self._determine_effect_direction(evidence)
            
            # Handle unknown classifications gracefully
            if effect_direction == EffectDirection.UNKNOWN:
                self.logger.info(f"Variant {rsid} classified as unknown due to insufficient evidence")
                return self._create_unknown_classification(rsid, "Insufficient evidence for classification")
            
            # Calculate confidence score
            confidence_score = self._calculate_confidence_score(evidence)
            
            # Determine confidence level
            confidence_level = self._get_confidence_level(confidence_score)
            
            # Generate reasoning
            reasoning = self._generate_reasoning(evidence, effect_direction)
            
            # Log successful classification
            self.logger.debug(f"Successfully classified variant {rsid} as {effect_direction.value} with {confidence_level.value} confidence")
            
            return VariantClassification(
                effect_direction=effect_direction,
                confidence_level=confidence_level,
                confidence_score=confidence_score,
                evidence_sources=list(evidence.keys()),
                reasoning=reasoning
            )
            
        except Exception as e:
            # Enhanced error logging with more context
            error_msg = f"Classification failed for variant {rsid}: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            
            # Log additional context for debugging
            self.logger.debug(f"Variant data that caused error: {variant_data}")
            
            return self._create_fallback_classification(error_msg, rsid)
    
    def _extract_evidence(self, variant_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract and normalize evidence from variant data"""
        evidence = {}
        
        # ClinVar evidence
        if 'clinvar_significance' in variant_data:
            evidence['clinvar'] = variant_data['clinvar_significance']
        
        # Literature evidence
        if 'literature_evidence' in variant_data:
            evidence['literature'] = variant_data['literature_evidence']
        
        # Population frequency evidence
        if 'population_frequency' in variant_data:
            evidence['population_data'] = variant_data['population_frequency']
        
        # Functional impact evidence
        if 'functional_impact' in variant_data:
            evidence['functional_prediction'] = variant_data['functional_impact']
        
        return evidence
    
    def _determine_effect_direction(self, evidence: Dict[str, Any]) -> EffectDirection:
        """
        Determine effect direction with Entprise/functional evidence as the primary authority.
        Literature and other sources are used for enrichment and confidence boosting.
        """
        # 1. Primary Authority: Functional Prediction (Entprise)
        functional_result = {'risk_score': 0.0, 'protective_score': 0.0}
        if 'functional_prediction' in evidence:
            functional_result = self._evaluate_functional_evidence(evidence['functional_prediction'])
            
        # If functional evidence is strong enough, it dictates the direction
        if functional_result['risk_score'] >= 0.6:
            return EffectDirection.RISK_INCREASING
        elif functional_result['protective_score'] >= 0.6: # In this context, implies "Benign/Neutral"
            return EffectDirection.NEUTRAL
            
        # 2. Secondary Evidence: Aggregate other sources if no strong functional evidence
        risk_score = functional_result['risk_score']
        protective_score = functional_result['protective_score']
        conflicting_evidence = False
        evidence_count = 1 if 'functional_prediction' in evidence else 0
        
        if 'clinvar' in evidence:
            clinvar_result = self._evaluate_clinvar_evidence(evidence['clinvar'])
            risk_score += clinvar_result['risk_score']
            protective_score += clinvar_result['protective_score']
            if clinvar_result['conflicting']: conflicting_evidence = True
            evidence_count += 1
            
        if 'literature' in evidence:
            lit_result = self._evaluate_literature_evidence(evidence['literature'])
            risk_score += lit_result['risk_score']
            protective_score += lit_result['protective_score']
            if lit_result['conflicting']: conflicting_evidence = True
            evidence_count += 1
            
        return self._apply_classification_rules(
            risk_score, protective_score, conflicting_evidence, evidence_count
        )
    
    def _evaluate_clinvar_evidence(self, clinvar_data: Any) -> Dict[str, Any]:
        """
        Enhanced ClinVar evidence evaluation with detailed pathogenicity assessment
        
        Args:
            clinvar_data: ClinVar significance data
            
        Returns:
            Dictionary with risk_score, protective_score, and conflicting flag
        """
        result = {'risk_score': 0.0, 'protective_score': 0.0, 'conflicting': False}
        
        if not clinvar_data:
            return result
        
        # Handle string significance values
        if isinstance(clinvar_data, str):
            clinvar_sig = clinvar_data.lower().strip()
            
            # Check for conflicting interpretations first
            if ('conflicting' in clinvar_sig or 'uncertain' in clinvar_sig):
                result['conflicting'] = True
            
            # Pathogenic classifications (risk-increasing)
            elif 'pathogenic' in clinvar_sig:
                if 'likely' not in clinvar_sig:
                    result['risk_score'] = self.config.risk_thresholds.get('clinvar_pathogenic', 0.8)
                else:  # likely_pathogenic
                    result['risk_score'] = self.config.risk_thresholds.get('clinvar_pathogenic', 0.8) * 0.8
            
            # Benign classifications are Neutral (not Protective)
            elif 'benign' in clinvar_sig:
                # We don't add to protective_score because Benign is Neutral
                pass
        
        # Handle structured ClinVar data
        elif isinstance(clinvar_data, dict):
            significance = clinvar_data.get('clinical_significance', '').lower()
            review_status = clinvar_data.get('review_status', '').lower()
            
            # Apply significance scoring
            if 'pathogenic' in significance:
                base_score = self.config.risk_thresholds.get('clinvar_pathogenic', 0.8)
                if 'likely' in significance:
                    base_score *= 0.8
                result['risk_score'] = base_score
            elif 'benign' in significance:
                # Benign is Neutral, not Protective
                pass
            elif 'conflicting' in significance or 'uncertain' in significance:
                result['conflicting'] = True
            
            # Adjust score based on review status quality
            if 'expert_panel' in review_status or 'practice_guideline' in review_status:
                result['risk_score'] *= 1.2
                result['protective_score'] *= 1.2
            elif 'single_submitter' in review_status:
                result['risk_score'] *= 0.7
                result['protective_score'] *= 0.7
        
        return result
    
    def _evaluate_literature_evidence(self, literature_data: Any) -> Dict[str, Any]:
        """
        Enhanced literature evidence evaluation with study quality assessment
        
        Args:
            literature_data: Literature evidence data
            
        Returns:
            Dictionary with risk_score, protective_score, and conflicting flag
        """
        result = {'risk_score': 0.0, 'protective_score': 0.0, 'conflicting': False}
        
        if not literature_data:
            return result
        
        if isinstance(literature_data, dict):
            # Evaluate risk associations
            if literature_data.get('risk_association', False):
                base_score = self.config.risk_thresholds.get('literature_risk', 0.6)
                
                # Adjust based on study quality indicators
                study_count = literature_data.get('study_count', 1)
                sample_size = literature_data.get('total_sample_size', 0)
                meta_analysis = literature_data.get('meta_analysis', False)
                
                # Quality multipliers
                if meta_analysis:
                    base_score *= 1.3
                if study_count > 5:
                    base_score *= 1.2
                if sample_size > 10000:
                    base_score *= 1.1
                
                result['risk_score'] = min(base_score, 1.0)
            
            # Evaluate protective associations
            if literature_data.get('protective_association', False):
                base_score = self.config.protective_thresholds.get('literature_protective', 0.6)
                
                # Apply same quality adjustments
                study_count = literature_data.get('study_count', 1)
                sample_size = literature_data.get('total_sample_size', 0)
                meta_analysis = literature_data.get('meta_analysis', False)
                
                if meta_analysis:
                    base_score *= 1.3
                if study_count > 5:
                    base_score *= 1.2
                if sample_size > 10000:
                    base_score *= 1.1
                
                result['protective_score'] = min(base_score, 1.0)
            
            # Check for conflicting literature
            if (literature_data.get('risk_association', False) and 
                literature_data.get('protective_association', False)):
                result['conflicting'] = True
            
            # Consider effect size if available
            effect_size = literature_data.get('effect_size')
            if effect_size:
                if effect_size > 1.5:  # Strong effect
                    result['risk_score'] *= 1.2
                    result['protective_score'] *= 1.2
                elif effect_size < 1.2:  # Weak effect
                    result['risk_score'] *= 0.8
                    result['protective_score'] *= 0.8
        
        return result
    
    def _evaluate_population_evidence(self, population_data: Any) -> Dict[str, Any]:
        """
        Enhanced population frequency evidence evaluation
        
        Args:
            population_data: Population frequency and association data
            
        Returns:
            Dictionary with risk_score and protective_score
        """
        result = {'risk_score': 0.0, 'protective_score': 0.0}
        
        if not isinstance(population_data, dict):
            return result
        
        frequency = population_data.get('frequency', 0.0)
        
        # Rare variants with disease association (likely pathogenic)
        if frequency < 0.01 and population_data.get('associated_with_disease', False):
            result['risk_score'] = self.config.risk_thresholds.get('population_frequency_rare_risk', 0.7)
            
            # Very rare variants get higher scores
            if frequency < 0.001:
                result['risk_score'] *= 1.2
        
        # Common variants with protective effect
        elif frequency > 0.1 and population_data.get('protective_effect', False):
            result['protective_score'] = self.config.protective_thresholds.get('population_frequency_common_protective', 0.7)
            
            # Very common protective variants get higher scores
            if frequency > 0.3:
                result['protective_score'] *= 1.1
        
        # Consider population-specific frequencies
        population_frequencies = population_data.get('population_frequencies', {})
        if population_frequencies:
            # Check for population-specific effects
            max_freq_diff = 0.0
            for pop, freq in population_frequencies.items():
                freq_diff = abs(freq - frequency)
                max_freq_diff = max(max_freq_diff, freq_diff)
            
            # Large frequency differences between populations may indicate selection pressure
            if max_freq_diff > 0.1:
                result['risk_score'] *= 1.1
                result['protective_score'] *= 1.1
        
        return result
    
    def _evaluate_functional_evidence(self, functional_data: Any) -> Dict[str, Any]:
        """
        Evaluate functional prediction evidence (e.g. Entprise/EntpriseX scores).
        """
        result = {'risk_score': 0.0, 'protective_score': 0.0}
        
        if not functional_data:
            return result
        
        # Handle string labels
        if isinstance(functional_data, str):
            # Check for direct score embedded in string (e.g. from ReportGenerator)
            if 'Score:' in functional_data:
                try:
                    score_str = functional_data.split('Score:')[1].split(',')[0].strip()
                    score = float(score_str)
                    if score > 0.6:
                        result['risk_score'] = 1.0 # Authority
                    elif score < 0.4:
                        result['protective_score'] = 1.0 # Treated as Neutral/Benign
                    return result
                except:
                    pass
            
            func_impact = functional_data.lower()
            if any(term in func_impact for term in ['damaging', 'deleterious', 'pathogenic']):
                result['risk_score'] = 0.8
            elif any(term in func_impact for term in ['benign', 'tolerated', 'neutral']):
                result['protective_score'] = 0.8
        
        # Handle decimal score directly
        elif isinstance(functional_data, (float, int)):
            score = float(functional_data)
            if score > 0.6:
                result['risk_score'] = 1.0
            elif score < 0.4:
                result['protective_score'] = 1.0
                
        return result
    
    def _apply_classification_rules(self, risk_score: float, protective_score: float, 
                                  conflicting_evidence: bool, evidence_count: int) -> EffectDirection:
        """
        Apply classification rule engine with fallback logic for unknown or conflicting classifications
        
        Args:
            risk_score: Accumulated risk score
            protective_score: Accumulated protective score
            conflicting_evidence: Whether conflicting evidence was found
            evidence_count: Number of evidence sources
            
        Returns:
            EffectDirection enum value
        """
        # Handle cases with no evidence
        if evidence_count == 0 or (risk_score == 0.0 and protective_score == 0.0):
            return EffectDirection.UNKNOWN
        
        # Handle conflicting evidence with fallback logic
        if conflicting_evidence:
            score_difference = abs(risk_score - protective_score)
            
            # If scores are very close, classify as neutral due to conflict
            if score_difference < 0.2:
                return EffectDirection.NEUTRAL
            
            # If one score is clearly higher despite conflict, use it but with caution
            elif risk_score > protective_score and risk_score > 0.6:
                return EffectDirection.RISK_INCREASING
            elif protective_score > risk_score and protective_score > 0.6:
                return EffectDirection.PROTECTIVE
            else:
                return EffectDirection.NEUTRAL
        
        # Standard classification rules
        score_difference = abs(risk_score - protective_score)
        max_score = max(risk_score, protective_score)
        
        # High confidence thresholds
        if max_score >= 0.8:
            if risk_score > protective_score:
                return EffectDirection.RISK_INCREASING
            else:
                return EffectDirection.PROTECTIVE
        
        # Moderate confidence thresholds
        elif max_score >= 0.5:
            # Require clear difference for classification
            if score_difference >= 0.2:
                if risk_score > protective_score:
                    return EffectDirection.RISK_INCREASING
                else:
                    return EffectDirection.PROTECTIVE
            else:
                return EffectDirection.NEUTRAL
        
        # Low confidence - classify as neutral or unknown
        elif max_score >= 0.3:
            return EffectDirection.NEUTRAL
        else:
            return EffectDirection.UNKNOWN
    
    def _calculate_confidence_score(self, evidence: Dict[str, Any]) -> float:
        """
        Enhanced confidence scoring algorithm based on evidence strength, quality, and consistency
        
        Args:
            evidence: Dictionary of evidence sources and their values
        
        Returns:
            Confidence score between 0.0 and 1.0
        """
        if not evidence:
            return 0.0
        
        total_weight = 0.0
        weighted_confidence = 0.0
        evidence_consistency_bonus = 0.0
        evidence_sources_count = 0
        
        # Calculate base confidence for each evidence source
        source_confidences = {}
        
        for source, weight in self.config.confidence_weights.items():
            if source in evidence:
                source_confidence = self._calculate_source_confidence(source, evidence[source])
                if source_confidence > 0:
                    source_confidences[source] = source_confidence
                    weighted_confidence += source_confidence * weight
                    total_weight += weight
                    evidence_sources_count += 1
        
        if total_weight == 0:
            return 0.0
        
        base_confidence = weighted_confidence / total_weight
        
        # Apply evidence consistency bonus
        if evidence_sources_count > 1:
            consistency_score = self._calculate_evidence_consistency(source_confidences)
            evidence_consistency_bonus = consistency_score * 0.1  # Up to 10% bonus
        
        # Apply evidence quantity bonus (more sources = higher confidence)
        quantity_bonus = min(evidence_sources_count * 0.05, 0.15)  # Up to 15% bonus
        
        # Apply evidence quality multiplier
        quality_multiplier = self._calculate_evidence_quality_multiplier(evidence)
        
        # Calculate final confidence score
        final_confidence = (base_confidence + evidence_consistency_bonus + quantity_bonus) * quality_multiplier
        
        return min(final_confidence, 1.0)
    
    def _calculate_source_confidence(self, source: str, evidence_data: Any) -> float:
        """
        Calculate confidence score for a specific evidence source
        
        Args:
            source: Evidence source name
            evidence_data: Data for this evidence source
            
        Returns:
            Confidence score for this source (0.0-1.0)
        """
        if source == 'clinvar':
            return self._calculate_clinvar_confidence(evidence_data)
        elif source == 'literature':
            return self._calculate_literature_confidence(evidence_data)
        elif source == 'population_data':
            return self._calculate_population_confidence(evidence_data)
        elif source == 'functional_prediction':
            return self._calculate_functional_confidence(evidence_data)
        else:
            return 0.5  # Default confidence for unknown sources
    
    def _calculate_clinvar_confidence(self, clinvar_data: Any) -> float:
        """Calculate confidence score for ClinVar evidence"""
        if not clinvar_data:
            return 0.0
        
        base_confidence = 0.5
        
        if isinstance(clinvar_data, str):
            clinvar_sig = clinvar_data.lower().strip()
            
            # High confidence for definitive classifications
            if any(term in clinvar_sig for term in ['pathogenic', 'benign']) and 'likely' not in clinvar_sig:
                base_confidence = 0.9
            elif any(term in clinvar_sig for term in ['likely_pathogenic', 'likely_benign']):
                base_confidence = 0.7
            elif 'uncertain' in clinvar_sig or 'conflicting' in clinvar_sig:
                base_confidence = 0.3
        
        elif isinstance(clinvar_data, dict):
            significance = clinvar_data.get('clinical_significance', '').lower()
            review_status = clinvar_data.get('review_status', '').lower()
            
            # Base confidence from significance
            if 'pathogenic' in significance or 'benign' in significance:
                base_confidence = 0.8 if 'likely' not in significance else 0.6
            elif 'uncertain' in significance or 'conflicting' in significance:
                base_confidence = 0.3
            
            # Adjust based on review status
            if 'expert_panel' in review_status or 'practice_guideline' in review_status:
                base_confidence = min(base_confidence * 1.3, 1.0)
            elif 'multiple_submitters' in review_status:
                base_confidence = min(base_confidence * 1.1, 1.0)
            elif 'single_submitter' in review_status:
                base_confidence *= 0.8
            elif 'no_assertion' in review_status:
                base_confidence *= 0.5
        
        return base_confidence
    
    def _calculate_literature_confidence(self, literature_data: Any) -> float:
        """Calculate confidence score for literature evidence"""
        if not literature_data or not isinstance(literature_data, dict):
            return 0.0
        
        base_confidence = 0.5
        
        # Study count factor
        study_count = literature_data.get('study_count', 1)
        if study_count >= 10:
            base_confidence = 0.8
        elif study_count >= 5:
            base_confidence = 0.7
        elif study_count >= 2:
            base_confidence = 0.6
        
        # Sample size factor
        total_sample_size = literature_data.get('total_sample_size', 0)
        if total_sample_size > 50000:
            base_confidence = min(base_confidence * 1.2, 1.0)
        elif total_sample_size > 10000:
            base_confidence = min(base_confidence * 1.1, 1.0)
        elif total_sample_size < 1000:
            base_confidence *= 0.8
        
        # Meta-analysis bonus
        if literature_data.get('meta_analysis', False):
            base_confidence = min(base_confidence * 1.3, 1.0)
        
        # Effect size consistency
        effect_size = literature_data.get('effect_size')
        if effect_size:
            if effect_size > 2.0:  # Very strong effect
                base_confidence = min(base_confidence * 1.2, 1.0)
            elif effect_size < 1.1:  # Very weak effect
                base_confidence *= 0.7
        
        return base_confidence
    
    def _calculate_population_confidence(self, population_data: Any) -> float:
        """Calculate confidence score for population frequency evidence"""
        if not isinstance(population_data, dict):
            return 0.0
        
        base_confidence = 0.6
        
        frequency = population_data.get('frequency', 0.0)
        
        # Higher confidence for extreme frequencies
        if frequency < 0.001 or frequency > 0.99:
            base_confidence = 0.8
        elif frequency < 0.01 or frequency > 0.9:
            base_confidence = 0.7
        
        # Population diversity bonus
        population_frequencies = population_data.get('population_frequencies', {})
        if len(population_frequencies) > 3:  # Multiple populations
            base_confidence = min(base_confidence * 1.1, 1.0)
        
        return base_confidence
    
    def _calculate_functional_confidence(self, functional_data: Any) -> float:
        """Calculate confidence score for functional prediction evidence"""
        if not functional_data:
            return 0.0
        
        base_confidence = 0.4  # Generally lower confidence for predictions
        
        if isinstance(functional_data, dict):
            # Multiple prediction tools increase confidence
            tool_count = len(functional_data)
            if tool_count >= 5:
                base_confidence = 0.6
            elif tool_count >= 3:
                base_confidence = 0.5
            
            # Check for consensus among tools
            predictions = []
            for tool, prediction in functional_data.items():
                if isinstance(prediction, dict) and 'score' in prediction:
                    predictions.append(prediction['score'])
                elif isinstance(prediction, str):
                    pred_lower = prediction.lower()
                    if 'damaging' in pred_lower:
                        predictions.append(0.8)
                    elif 'benign' in pred_lower:
                        predictions.append(0.2)
            
            if len(predictions) > 1:
                # Calculate consensus
                avg_score = sum(predictions) / len(predictions)
                score_variance = sum((p - avg_score) ** 2 for p in predictions) / len(predictions)
                
                # Low variance indicates consensus
                if score_variance < 0.1:
                    base_confidence = min(base_confidence * 1.3, 1.0)
                elif score_variance > 0.3:
                    base_confidence *= 0.7
        
        return base_confidence
    
    def _calculate_evidence_consistency(self, source_confidences: Dict[str, float]) -> float:
        """
        Calculate consistency score across evidence sources
        
        Args:
            source_confidences: Dictionary mapping sources to their confidence scores
            
        Returns:
            Consistency score (0.0-1.0)
        """
        if len(source_confidences) < 2:
            return 0.0
        
        confidence_values = list(source_confidences.values())
        avg_confidence = sum(confidence_values) / len(confidence_values)
        
        # Calculate variance in confidence scores
        variance = sum((conf - avg_confidence) ** 2 for conf in confidence_values) / len(confidence_values)
        
        # Convert variance to consistency score (lower variance = higher consistency)
        consistency_score = max(0.0, 1.0 - (variance * 4))  # Scale variance to 0-1 range
        
        return consistency_score
    
    def _calculate_evidence_quality_multiplier(self, evidence: Dict[str, Any]) -> float:
        """
        Calculate overall evidence quality multiplier
        
        Args:
            evidence: Dictionary of all evidence sources
            
        Returns:
            Quality multiplier (0.5-1.2)
        """
        quality_factors = []
        
        # Check for high-quality ClinVar evidence
        if 'clinvar' in evidence:
            clinvar_data = evidence['clinvar']
            if isinstance(clinvar_data, dict):
                review_status = clinvar_data.get('review_status', '').lower()
                if 'expert_panel' in review_status or 'practice_guideline' in review_status:
                    quality_factors.append(1.2)
                elif 'multiple_submitters' in review_status:
                    quality_factors.append(1.1)
        
        # Check for high-quality literature evidence
        if 'literature' in evidence and isinstance(evidence['literature'], dict):
            lit_data = evidence['literature']
            if lit_data.get('meta_analysis', False):
                quality_factors.append(1.15)
            if lit_data.get('total_sample_size', 0) > 10000:
                quality_factors.append(1.1)
        
        # Check for comprehensive population data
        if 'population_data' in evidence and isinstance(evidence['population_data'], dict):
            pop_data = evidence['population_data']
            if len(pop_data.get('population_frequencies', {})) > 3:
                quality_factors.append(1.05)
        
        # Return average quality multiplier, bounded between 0.5 and 1.2
        if quality_factors:
            avg_multiplier = sum(quality_factors) / len(quality_factors)
            return min(max(avg_multiplier, 0.5), 1.2)
        else:
            return 1.0
    
    def _get_confidence_level(self, confidence_score: float) -> ConfidenceLevel:
        """Convert confidence score to confidence level enum"""
        if confidence_score >= 0.8:
            return ConfidenceLevel.HIGH
        elif confidence_score >= 0.5:
            return ConfidenceLevel.MODERATE
        else:
            return ConfidenceLevel.LOW
    
    def _generate_reasoning(self, evidence: Dict[str, Any], effect_direction: EffectDirection) -> str:
        """Generate human-readable reasoning for the classification"""
        reasoning_parts = []
        
        if 'clinvar' in evidence:
            reasoning_parts.append(f"ClinVar classification: {evidence['clinvar']}")
        
        if 'literature' in evidence:
            reasoning_parts.append("Literature evidence available")
        
        if 'population_data' in evidence:
            reasoning_parts.append("Population frequency data considered")
        
        if 'functional_prediction' in evidence:
            reasoning_parts.append("Functional impact predictions included")
        
        base_reasoning = "; ".join(reasoning_parts) if reasoning_parts else "Limited evidence available"
        
        return f"Classified as {effect_direction.value} based on: {base_reasoning}"
    
    def update_config(self, new_config: ClassificationConfig) -> None:
        """Update the classification configuration"""
        self.config = new_config
        self.logger.info("Classification configuration updated")
    
    def classify_variants_batch(self, variants: List[Dict[str, Any]]) -> List[VariantClassification]:
        """
        Classify multiple variants in batch with enhanced error handling and fallback behavior
        
        Args:
            variants: List of variant data dictionaries
        
        Returns:
            List of VariantClassification objects
        """
        if not variants:
            self.logger.warning("Empty variant list provided for batch classification")
            return []
        
        classifications = []
        successful_classifications = 0
        failed_classifications = 0
        unknown_classifications = 0
        
        self.logger.info(f"Starting batch classification of {len(variants)} variants")
        
        for i, variant in enumerate(variants):
            try:
                # Validate variant data before processing
                if not isinstance(variant, dict):
                    self.logger.error(f"Variant at index {i} is not a dictionary: {type(variant)}")
                    classifications.append(self._create_fallback_classification(
                        f"Invalid variant data type: {type(variant)}", f"index_{i}"
                    ))
                    failed_classifications += 1
                    continue
                
                classification = self.classify_variant(variant)
                classifications.append(classification)
                
                # Track classification statistics
                if classification.effect_direction == EffectDirection.UNKNOWN:
                    unknown_classifications += 1
                else:
                    successful_classifications += 1
                    
            except Exception as e:
                rsid = variant.get('rsid', f'index_{i}') if isinstance(variant, dict) else f'index_{i}'
                error_msg = f"Failed to classify variant {rsid}: {str(e)}"
                self.logger.error(error_msg, exc_info=True)
                
                # Add fallback classification
                classifications.append(self._create_fallback_classification(error_msg, rsid))
                failed_classifications += 1
        
        # Log batch processing summary
        self.logger.info(
            f"Batch classification completed: {successful_classifications} successful, "
            f"{unknown_classifications} unknown, {failed_classifications} failed out of {len(variants)} total"
        )
        
        # Warn if high failure rate
        failure_rate = failed_classifications / len(variants)
        if failure_rate > 0.1:  # More than 10% failures
            self.logger.warning(f"High failure rate in batch classification: {failure_rate:.1%}")
        
        return classifications
    
    def classify_variant_for_condition(self, variant_data: Dict[str, Any], condition: str) -> VariantClassification:
        """
        Classify a variant specifically for a given condition/disease
        
        Args:
            variant_data: Dictionary containing variant information
            condition: Specific condition/disease to classify for
        
        Returns:
            VariantClassification object with condition-specific classification
        """
        # Create condition-specific variant data
        condition_specific_data = variant_data.copy()
        
        # Filter evidence to condition-specific data if available
        if 'condition_specific_evidence' in variant_data:
            condition_evidence = variant_data['condition_specific_evidence'].get(condition, {})
            if condition_evidence:
                # Merge condition-specific evidence
                for key, value in condition_evidence.items():
                    condition_specific_data[key] = value
        
        # Perform classification
        classification = self.classify_variant(condition_specific_data)
        
        # Add condition context to reasoning
        classification.reasoning = f"For {condition}: {classification.reasoning}"
        
        return classification
    
    def validate_classification_consistency(self, variant_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate classification consistency and identify potential issues
        
        Args:
            variant_data: Dictionary containing variant information
        
        Returns:
            Dictionary with validation results and warnings
        """
        validation_result = {
            'is_consistent': True,
            'warnings': [],
            'confidence_factors': {},
            'evidence_gaps': []
        }
        
        try:
            # Extract evidence
            evidence = self._extract_evidence(variant_data)
            
            # Check for evidence gaps
            expected_sources = ['clinvar', 'literature', 'population_data', 'functional_prediction']
            missing_sources = [source for source in expected_sources if source not in evidence]
            validation_result['evidence_gaps'] = missing_sources
            
            # Check for conflicting evidence
            conflicting_indicators = []
            
            # ClinVar conflicts
            if 'clinvar' in evidence:
                clinvar_data = evidence['clinvar']
                if isinstance(clinvar_data, str) and ('conflicting' in clinvar_data.lower() or 'uncertain' in clinvar_data.lower()):
                    conflicting_indicators.append('ClinVar reports conflicting interpretations')
            
            # Literature conflicts
            if 'literature' in evidence and isinstance(evidence['literature'], dict):
                lit_data = evidence['literature']
                if lit_data.get('risk_association', False) and lit_data.get('protective_association', False):
                    conflicting_indicators.append('Literature shows both risk and protective associations')
            
            # Population frequency inconsistencies
            if 'population_data' in evidence and isinstance(evidence['population_data'], dict):
                pop_data = evidence['population_data']
                frequency = pop_data.get('frequency', 0.0)
                if frequency > 0.05 and pop_data.get('associated_with_disease', False):
                    conflicting_indicators.append('High frequency variant associated with disease (unusual)')
            
            if conflicting_indicators:
                validation_result['is_consistent'] = False
                validation_result['warnings'].extend(conflicting_indicators)
            
            # Calculate confidence factors
            for source in evidence:
                confidence = self._calculate_source_confidence(source, evidence[source])
                validation_result['confidence_factors'][source] = confidence
            
        except Exception as e:
            validation_result['is_consistent'] = False
            validation_result['warnings'].append(f"Validation error: {str(e)}")
        
        return validation_result
    
    def get_classification_summary(self, variants: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Get a comprehensive summary of classifications for a list of variants
        
        Args:
            variants: List of variant data dictionaries
        
        Returns:
            Dictionary with detailed classification statistics
        """
        summary = {
            'total_variants': len(variants),
            'effect_direction_counts': {direction.value: 0 for direction in EffectDirection},
            'confidence_level_counts': {level.value: 0 for level in ConfidenceLevel},
            'average_confidence_score': 0.0,
            'high_confidence_variants': 0,
            'variants_with_conflicts': 0,
            'evidence_source_coverage': {
                'clinvar': 0,
                'literature': 0,
                'population_data': 0,
                'functional_prediction': 0
            }
        }
        
        if not variants:
            return summary
        
        total_confidence = 0.0
        
        for variant in variants:
            try:
                classification = self.classify_variant(variant)
                
                # Count effect directions
                summary['effect_direction_counts'][classification.effect_direction.value] += 1
                
                # Count confidence levels
                summary['confidence_level_counts'][classification.confidence_level.value] += 1
                
                # Track confidence scores
                total_confidence += classification.confidence_score
                if classification.confidence_level == ConfidenceLevel.HIGH:
                    summary['high_confidence_variants'] += 1
                
                # Check for conflicts
                validation = self.validate_classification_consistency(variant)
                if not validation['is_consistent']:
                    summary['variants_with_conflicts'] += 1
                
                # Count evidence source coverage
                evidence = self._extract_evidence(variant)
                for source in summary['evidence_source_coverage']:
                    if source in evidence:
                        summary['evidence_source_coverage'][source] += 1
                        
            except Exception as e:
                self.logger.error(f"Error in summary for variant {variant.get('rsid', 'unknown')}: {str(e)}")
                summary['effect_direction_counts'][self.config.default_classification.value] += 1
        
        # Calculate average confidence
        summary['average_confidence_score'] = total_confidence / len(variants) if variants else 0.0
        
        return summary
    
    def export_classification_rules(self) -> Dict[str, Any]:
        """
        Export current classification rules and configuration for audit/debugging
        
        Returns:
            Dictionary containing all classification rules and thresholds
        """
        return {
            'config': {
                'risk_thresholds': self.config.risk_thresholds,
                'protective_thresholds': self.config.protective_thresholds,
                'confidence_weights': self.config.confidence_weights,
                'evidence_source_priorities': self.config.evidence_source_priorities,
                'default_classification': self.config.default_classification.value
            },
            'classification_rules': {
                'high_confidence_threshold': 0.8,
                'moderate_confidence_threshold': 0.5,
                'minimum_score_for_classification': 0.3,
                'conflict_resolution_threshold': 0.2,
                'evidence_consistency_bonus_max': 0.1,
                'evidence_quantity_bonus_max': 0.15,
                'quality_multiplier_range': [0.5, 1.2]
            },
            'version': '1.0',
            'last_updated': None  # Could be set to current timestamp
        }
    
    # Enhanced error handling helper methods
    
    def _validate_variant_data(self, variant_data: Dict[str, Any]) -> List[str]:
        """
        Validate variant data and return list of validation errors
        
        Args:
            variant_data: Dictionary containing variant information
            
        Returns:
            List of validation error messages
        """
        errors = []
        
        # Check for required fields
        if not variant_data.get('rsid'):
            errors.append("Missing or empty rsid")
        
        if not variant_data.get('gene'):
            errors.append("Missing or empty gene")
        
        # Validate data types and ranges
        if 'population_frequency' in variant_data:
            freq = variant_data['population_frequency']
            if freq is not None:
                try:
                    freq_float = float(freq)
                    if not (0.0 <= freq_float <= 1.0):
                        errors.append(f"Population frequency {freq_float} out of valid range [0.0, 1.0]")
                except (ValueError, TypeError):
                    errors.append(f"Invalid population frequency format: {freq}")
        
        # Validate ClinVar significance if present
        if 'clinvar_significance' in variant_data:
            clinvar = variant_data['clinvar_significance']
            if clinvar and isinstance(clinvar, str):
                valid_terms = ['pathogenic', 'likely_pathogenic', 'benign', 'likely_benign', 
                              'uncertain_significance', 'conflicting_interpretations']
                if not any(term in clinvar.lower() for term in valid_terms):
                    errors.append(f"Unrecognized ClinVar significance: {clinvar}")
        
        return errors
    
    def _extract_evidence_with_validation(self, variant_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract and validate evidence from variant data with enhanced error handling
        
        Args:
            variant_data: Dictionary containing variant information
            
        Returns:
            Dictionary of validated evidence sources
        """
        evidence = {}
        
        try:
            # ClinVar evidence with validation
            if 'clinvar_significance' in variant_data:
                clinvar_data = variant_data['clinvar_significance']
                if clinvar_data:  # Only include non-empty data
                    evidence['clinvar'] = clinvar_data
            
            # Literature evidence with validation
            if 'literature_evidence' in variant_data:
                lit_data = variant_data['literature_evidence']
                if lit_data:  # Only include non-empty data
                    evidence['literature'] = lit_data
            
            # Population frequency evidence with validation
            if 'population_frequency' in variant_data:
                pop_data = variant_data['population_frequency']
                if pop_data is not None:
                    try:
                        # Validate numeric data
                        if isinstance(pop_data, (int, float)):
                            if 0.0 <= pop_data <= 1.0:
                                evidence['population_data'] = pop_data
                            else:
                                self.logger.warning(f"Population frequency {pop_data} out of range, skipping")
                        elif isinstance(pop_data, dict):
                            # Validate dictionary structure
                            if 'frequency' in pop_data:
                                evidence['population_data'] = pop_data
                            else:
                                self.logger.warning("Population data missing 'frequency' field, skipping")
                    except (ValueError, TypeError) as e:
                        self.logger.warning(f"Invalid population frequency data: {e}")
            
            # Functional impact evidence with validation
            if 'functional_impact' in variant_data:
                func_data = variant_data['functional_impact']
                if func_data:  # Only include non-empty data
                    evidence['functional_prediction'] = func_data
            
        except Exception as e:
            self.logger.error(f"Error extracting evidence: {str(e)}")
            # Return whatever evidence was successfully extracted
        
        return evidence
    
    def _create_fallback_classification(self, error_message: str, rsid: str = "unknown") -> VariantClassification:
        """
        Create a fallback classification for error cases
        
        Args:
            error_message: Description of the error
            rsid: Variant identifier for logging
            
        Returns:
            VariantClassification with fallback values
        """
        return VariantClassification(
            effect_direction=self.config.default_classification,
            confidence_level=ConfidenceLevel.LOW,
            confidence_score=0.0,
            evidence_sources=[],
            reasoning=f"Fallback classification for {rsid}: {error_message}"
        )
    
    def _create_unknown_classification(self, rsid: str, reason: str) -> VariantClassification:
        """
        Create an unknown classification with appropriate reasoning
        
        Args:
            rsid: Variant identifier
            reason: Reason for unknown classification
            
        Returns:
            VariantClassification with unknown effect direction
        """
        return VariantClassification(
            effect_direction=EffectDirection.UNKNOWN,
            confidence_level=ConfidenceLevel.LOW,
            confidence_score=0.1,  # Minimal confidence for unknown
            evidence_sources=[],
            reasoning=f"Unknown classification for {rsid}: {reason}"
        )