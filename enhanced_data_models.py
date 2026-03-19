"""
Enhanced data models for risk/protective variant reporting.

This module defines the enhanced dataclasses for the risk-protective variant
reporting system, extending the existing data models with effect direction
and confidence fields.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Union
from enum import Enum
import logging

# Import existing enums from variant_classifier
from variant_classifier import EffectDirection, ConfidenceLevel

logger = logging.getLogger(__name__)


@dataclass
class EnhancedVariant:
    """
    Enhanced variant data model with effect direction and confidence fields.
    
    This extends the basic variant information with classification data
    for risk/protective variant reporting.
    """
    rsid: str
    gene: str
    effect_direction: EffectDirection
    effect_magnitude: float  # Quantitative measure of effect size
    confidence_level: ConfidenceLevel
    confidence_score: float  # Numerical confidence score (0.0-1.0)
    condition_associations: List[str]  # List of associated conditions/diseases
    evidence_sources: List[str]  # Sources of evidence for classification
    
    # Optional fields for additional variant information
    chromosome: Optional[str] = None
    position: Optional[int] = None
    ref_allele: Optional[str] = None
    alt_allele: Optional[str] = None
    allele_frequency: Optional[float] = None
    clinical_significance: Optional[str] = None
    functional_impact: Optional[str] = None
    evidence_strength: Optional[str] = None  # Strong, Moderate, Emerging
    absolute_risk_range: Optional[str] = None  # e.g., "40-50% by age 70"
    population_risk: Optional[str] = None  # e.g., "1-2%"
    risk_tier: Optional[str] = None  # Tier 1, Tier 2, Tier 3
    
    # Verified variant data fields — populated from parsed input, NOT from LLM
    ref_amino_acid: Optional[str] = None     # e.g., "GLY"
    alt_amino_acid: Optional[str] = None     # e.g., "ALA"
    amino_acid_position: Optional[str] = None  # e.g., "62"
    score: Optional[float] = None            # Pathogenicity score from input
    hgvs: Optional[str] = None               # Original HGVS notation from input
    protein_id: Optional[str] = None         # Original NP accession from input
    
    def __post_init__(self):
        """Validate enhanced variant data after initialization."""
        if not self.rsid:
            raise ValueError("RSID cannot be empty")
        
        if not self.gene:
            raise ValueError("Gene cannot be empty")
        
        if not (0.0 <= self.confidence_score <= 1.0):
            raise ValueError(f"Confidence score must be between 0.0 and 1.0, got {self.confidence_score}")
        
        if self.allele_frequency is not None and not (0.0 <= self.allele_frequency <= 1.0):
            raise ValueError(f"Allele frequency must be between 0.0 and 1.0, got {self.allele_frequency}")
    
    def is_risk_variant(self) -> bool:
        """Check if this variant increases disease risk."""
        return self.effect_direction == EffectDirection.RISK_INCREASING
    
    def is_protective_variant(self) -> bool:
        """Check if this variant is protective against disease."""
        return self.effect_direction == EffectDirection.PROTECTIVE
    
    def has_high_confidence(self) -> bool:
        """Check if this variant has high confidence classification."""
        return self.confidence_level == ConfidenceLevel.HIGH
    
    def get_verified_variant_description(self) -> str:
        """Get a concise verified variant description like 'p.Gly62Ala'."""
        if self.ref_amino_acid and self.amino_acid_position and self.alt_amino_acid:
            # Convert 3-letter codes to 1-letter for standard notation
            aa3to1 = {
                'ALA': 'A', 'ARG': 'R', 'ASN': 'N', 'ASP': 'D', 'CYS': 'C',
                'GLU': 'E', 'GLN': 'Q', 'GLY': 'G', 'HIS': 'H', 'ILE': 'I',
                'LEU': 'L', 'LYS': 'K', 'MET': 'M', 'PHE': 'F', 'PRO': 'P',
                'SER': 'S', 'THR': 'T', 'TRP': 'W', 'TYR': 'Y', 'VAL': 'V'
            }
            ref_3 = self.ref_amino_acid.upper().strip()
            alt_3 = self.alt_amino_acid.upper().strip()
            # Use 3-letter title case for standard protein notation
            ref_name = ref_3.capitalize() if len(ref_3) == 3 else ref_3
            alt_name = alt_3.capitalize() if len(alt_3) == 3 else alt_3
            return f"p.{ref_name}{self.amino_acid_position}{alt_name}"
        return self.rsid  # fallback to HGVS
    
    def to_structured_dict(self) -> dict:
        """Convert to a verified data dictionary for template rendering."""
        return {
            'gene': self.gene,
            'protein_id': self.protein_id or '',
            'variant_description': self.get_verified_variant_description(),
            'hgvs': self.hgvs or self.rsid,
            'ref_amino_acid': self.ref_amino_acid or '',
            'alt_amino_acid': self.alt_amino_acid or '',
            'amino_acid_position': self.amino_acid_position or '',
            'score': self.score or self.effect_magnitude,
            'effect_direction': self.effect_direction.value if self.effect_direction else 'unknown',
            'clinical_significance': self.clinical_significance or 'VUS',
            'evidence_strength': self.evidence_strength or 'Emerging',
            'conditions': self.condition_associations or [],
            'absolute_risk_range': self.absolute_risk_range or '',
            'population_risk': self.population_risk or '',
            'risk_tier': self.risk_tier or ''
        }
    
    def __str__(self) -> str:
        """String representation with verified data for LLM consumption."""
        desc = self.get_verified_variant_description()
        diseases = ', '.join(self.condition_associations) if self.condition_associations else 'None'
        score_str = f"{self.score:.3f}" if self.score else f"{self.effect_magnitude:.3f}"
        return (
            f"Gene: {self.gene} | "
            f"Protein: {self.protein_id or 'Unknown'} | "
            f"Variant: {desc} | "
            f"HGVS: {self.hgvs or self.rsid} | "
            f"Position: {self.amino_acid_position or 'Unknown'} | "
            f"Change: {self.ref_amino_acid or '?'} -> {self.alt_amino_acid or '?'} | "
            f"Score: {score_str} | "
            f"Effect: {self.effect_direction.value if self.effect_direction else 'unknown'} | "
            f"Significance: {self.clinical_significance or 'VUS'} | "
            f"Evidence: {self.evidence_strength or 'Emerging'} | "
            f"Diseases: {diseases}"
        )


@dataclass
class ProteinDiseaseAssociation:
    """
    Enhanced protein-disease association model with risk/protective categorization.
    
    This model captures the relationship between proteins and diseases with
    specific focus on risk vs protective effects.
    """
    protein: str
    condition: str
    effect_direction: EffectDirection
    risk_magnitude: float  # Magnitude of risk increase (positive values)
    protective_magnitude: float  # Magnitude of protective effect (positive values)
    evidence_level: str  # Strength of evidence (e.g., "strong", "moderate", "weak")
    population_frequency: float  # Frequency in population
    clinical_actionability: bool  # Whether clinically actionable
    absolute_risk_range: Optional[str] = None
    population_risk: Optional[str] = None
    risk_tier: Optional[str] = None
    
    # Additional association metadata
    source_databases: List[str] = field(default_factory=list)
    pubmed_ids: List[str] = field(default_factory=list)
    last_updated: Optional[str] = None
    
    def __post_init__(self):
        """Validate protein-disease association data after initialization."""
        if not self.protein:
            raise ValueError("Protein cannot be empty")
        
        if not self.condition:
            raise ValueError("Condition cannot be empty")
        
        if self.risk_magnitude < 0.0:
            raise ValueError(f"Risk magnitude cannot be negative, got {self.risk_magnitude}")
        
        if self.protective_magnitude < 0.0:
            raise ValueError(f"Protective magnitude cannot be negative, got {self.protective_magnitude}")
        
        if not (0.0 <= self.population_frequency <= 1.0):
            raise ValueError(f"Population frequency must be between 0.0 and 1.0, got {self.population_frequency}")
    
    def get_net_effect_magnitude(self) -> float:
        """
        Calculate net effect magnitude considering both risk and protective effects.
        
        Returns:
            Positive value for net risk increase, negative for net protection
        """
        return self.risk_magnitude - self.protective_magnitude
    
    def is_net_risk_increasing(self) -> bool:
        """Check if the net effect increases disease risk."""
        return self.get_net_effect_magnitude() > 0
    
    def is_net_protective(self) -> bool:
        """Check if the net effect is protective."""
        return self.get_net_effect_magnitude() < 0


class SectionType(Enum):
    """Enumeration for different report section types."""
    RISK_ASSESSMENT = "risk_assessment"
    PROTECTIVE_FACTORS = "protective_factors"
    CLINICAL_IMPLICATIONS = "clinical_implications"
    MUTATION_PROFILE = "mutation_profile"
    LITERATURE_EVIDENCE = "literature_evidence"
    LIFESTYLE_RECOMMENDATIONS = "lifestyle_recommendations"


class SectionPriority(Enum):
    """Enumeration for section display priority."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class SectionConfig:
    """
    Configuration model for managing section visibility and display.
    
    This model determines which sections should be displayed based on
    the presence and types of variants for each condition.
    """
    show_risk_section: bool
    show_protective_section: bool
    risk_variant_count: int
    protective_variant_count: int
    section_priority: SectionPriority
    
    # Additional configuration options
    condition_name: Optional[str] = None
    custom_headers: Dict[str, str] = field(default_factory=dict)
    display_order: List[SectionType] = field(default_factory=list)
    
    def __post_init__(self):
        """Validate section configuration after initialization."""
        if self.risk_variant_count < 0:
            raise ValueError(f"Risk variant count cannot be negative, got {self.risk_variant_count}")
        
        if self.protective_variant_count < 0:
            raise ValueError(f"Protective variant count cannot be negative, got {self.protective_variant_count}")
        
        # Ensure section visibility is consistent with variant counts
        if self.show_risk_section and self.risk_variant_count == 0:
            logger.warning("Risk section enabled but no risk variants present")
        
        if self.show_protective_section and self.protective_variant_count == 0:
            logger.warning("Protective section enabled but no protective variants present")
    
    def has_any_variants(self) -> bool:
        """Check if there are any variants to display."""
        return self.risk_variant_count > 0 or self.protective_variant_count > 0
    
    def should_display_section(self, section_type: SectionType) -> bool:
        """
        Determine if a specific section type should be displayed.
        
        Args:
            section_type: The type of section to check
            
        Returns:
            True if the section should be displayed
        """
        if section_type == SectionType.RISK_ASSESSMENT:
            return self.show_risk_section
        elif section_type == SectionType.PROTECTIVE_FACTORS:
            return self.show_protective_section
        else:
            # For other sections, display if there are any variants
            return self.has_any_variants()


@dataclass
class ReportSection:
    """
    Model for organizing variant data by effect type within report sections.
    
    This model structures the data for individual report sections,
    separating risk-increasing and protective variants.
    """
    section_type: SectionType
    condition: str
    risk_variants: List[EnhancedVariant]
    protective_variants: List[EnhancedVariant]
    show_risk_subsection: bool
    show_protective_subsection: bool
    summary_text: str
    
    # Additional section metadata
    section_title: Optional[str] = None
    section_description: Optional[str] = None
    clinical_recommendations: List[str] = field(default_factory=list)
    evidence_summary: Optional[str] = None
    
    def __post_init__(self):
        """Validate report section data after initialization."""
        if not self.condition:
            raise ValueError("Condition cannot be empty")
        
        if not self.summary_text:
            raise ValueError("Summary text cannot be empty")
        
        # Validate subsection visibility consistency
        if self.show_risk_subsection and not self.risk_variants:
            logger.warning(f"Risk subsection enabled for {self.condition} but no risk variants present")
        
        if self.show_protective_subsection and not self.protective_variants:
            logger.warning(f"Protective subsection enabled for {self.condition} but no protective variants present")
    
    def get_total_variant_count(self) -> int:
        """Get the total number of variants in this section."""
        return len(self.risk_variants) + len(self.protective_variants)
    
    def get_high_confidence_variants(self) -> List[EnhancedVariant]:
        """Get all high-confidence variants from this section."""
        high_conf_variants = []
        high_conf_variants.extend([v for v in self.risk_variants if v.has_high_confidence()])
        high_conf_variants.extend([v for v in self.protective_variants if v.has_high_confidence()])
        return high_conf_variants
    
    def has_actionable_variants(self) -> bool:
        """Check if this section contains clinically actionable variants."""
        # This could be enhanced with specific actionability criteria
        return len(self.get_high_confidence_variants()) > 0
    
    def generate_section_summary(self) -> str:
        """
        Generate a dynamic summary based on the variants in this section.
        
        Returns:
            A summary string describing the section contents
        """
        risk_count = len(self.risk_variants)
        protective_count = len(self.protective_variants)
        
        if risk_count > 0 and protective_count > 0:
            return f"This section contains {risk_count} risk-increasing and {protective_count} protective variants for {self.condition}."
        elif risk_count > 0:
            return f"This section contains {risk_count} risk-increasing variants for {self.condition}."
        elif protective_count > 0:
            return f"This section contains {protective_count} protective variants for {self.condition}."
        else:
            return f"No significant variants identified for {self.condition}."


# Utility functions for working with enhanced data models

def create_enhanced_variant_from_basic(
    rsid: str,
    gene: str,
    effect_direction: EffectDirection,
    confidence_level: ConfidenceLevel,
    confidence_score: float,
    condition_associations: List[str],
    **kwargs
) -> EnhancedVariant:
    """
    Create an EnhancedVariant from basic parameters.
    
    Args:
        rsid: Variant identifier
        gene: Associated gene
        effect_direction: Risk/protective classification
        confidence_level: Confidence level enum
        confidence_score: Numerical confidence score
        condition_associations: List of associated conditions
        **kwargs: Additional optional parameters
        
    Returns:
        EnhancedVariant object
    """
    return EnhancedVariant(
        rsid=rsid,
        gene=gene,
        effect_direction=effect_direction,
        effect_magnitude=kwargs.get('effect_magnitude', 1.0),
        confidence_level=confidence_level,
        confidence_score=confidence_score,
        condition_associations=condition_associations,
        evidence_sources=kwargs.get('evidence_sources', []),
        chromosome=kwargs.get('chromosome'),
        position=kwargs.get('position'),
        ref_allele=kwargs.get('ref_allele'),
        alt_allele=kwargs.get('alt_allele'),
        allele_frequency=kwargs.get('allele_frequency'),
        clinical_significance=kwargs.get('clinical_significance'),
        functional_impact=kwargs.get('functional_impact')
    )


def create_section_config_for_condition(
    condition: str,
    risk_variants: List[EnhancedVariant],
    protective_variants: List[EnhancedVariant],
    priority: SectionPriority = SectionPriority.MEDIUM
) -> SectionConfig:
    """
    Create a SectionConfig based on available variants for a condition.
    
    Args:
        condition: Name of the condition
        risk_variants: List of risk-increasing variants
        protective_variants: List of protective variants
        priority: Section priority level
        
    Returns:
        SectionConfig object
    """
    risk_count = len(risk_variants)
    protective_count = len(protective_variants)
    
    return SectionConfig(
        show_risk_section=risk_count > 0,
        show_protective_section=protective_count > 0,
        risk_variant_count=risk_count,
        protective_variant_count=protective_count,
        section_priority=priority,
        condition_name=condition
    )


def filter_variants_by_confidence(
    variants: List[EnhancedVariant],
    min_confidence: ConfidenceLevel = ConfidenceLevel.MODERATE
) -> List[EnhancedVariant]:
    """
    Filter variants by minimum confidence level.
    
    Args:
        variants: List of variants to filter
        min_confidence: Minimum confidence level to include
        
    Returns:
        Filtered list of variants
    """
    confidence_order = {
        ConfidenceLevel.LOW: 1,
        ConfidenceLevel.MODERATE: 2,
        ConfidenceLevel.HIGH: 3
    }
    
    min_level = confidence_order[min_confidence]
    
    return [
        variant for variant in variants
        if confidence_order[variant.confidence_level] >= min_level
    ]


def group_variants_by_effect_direction(
    variants: List[EnhancedVariant]
) -> Dict[EffectDirection, List[EnhancedVariant]]:
    """
    Group variants by their effect direction.
    
    Args:
        variants: List of variants to group
        
    Returns:
        Dictionary mapping effect directions to variant lists
    """
    grouped = {direction: [] for direction in EffectDirection}
    
    for variant in variants:
        grouped[variant.effect_direction].append(variant)
    
    return grouped