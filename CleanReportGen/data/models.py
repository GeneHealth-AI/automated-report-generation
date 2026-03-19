from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union
import logging

logger = logging.getLogger(__name__)

# --- Enums (Consolidated from variant_classifier.py and report_blocks.py) ---

class EffectDirection(Enum):
    """Enumeration for variant effect directions."""
    RISK_INCREASING = "risk_increasing"
    PROTECTIVE = "protective"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"

class ConfidenceLevel(Enum):
    """Enumeration for classification confidence levels."""
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"

class BlockType(Enum):
    """Enumeration for report block types."""
    INTRODUCTION = "introduction"
    EXECUTIVE_SUMMARY = "executive_summary"
    MUTATION_PROFILE = "mutation_profile"
    LITERATURE_EVIDENCE = "literature_evidence"
    RISK_ASSESSMENT = "risk_assessment"
    CLINICAL_IMPLICATIONS = "clinical_implications"
    LIFESTYLE_RECOMMENDATIONS = "lifestyle_recommendations"
    MONITORING_PLAN = "monitoring_plan"
    RESEARCH_OPPORTUNITIES = "research_opportunities"
    CONCLUSION = "conclusion"

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

# --- Dataclasses ---

@dataclass
class ReportBlock:
    """Structure for a single section of the genetic report."""
    block_type: BlockType
    title: str
    content: Union[str, Dict[str, Any]]
    template: str
    order: int
    is_required: bool = True
    user_customizable: bool = True
    feedback: str = ''
    modifications: str = ''

@dataclass
class EnhancedVariant:
    """Enhanced variant data model with effect direction and confidence fields."""
    rsid: str
    gene: str
    effect_direction: EffectDirection
    effect_magnitude: float
    confidence_level: ConfidenceLevel
    confidence_score: float
    condition_associations: List[str]
    evidence_sources: List[str]
    
    chromosome: Optional[str] = None
    position: Optional[int] = None
    ref_allele: Optional[str] = None
    alt_allele: Optional[str] = None
    allele_frequency: Optional[float] = None
    clinical_significance: Optional[str] = None
    functional_impact: Optional[str] = None
    
    def __post_init__(self):
        if not self.rsid: raise ValueError("RSID cannot be empty")
        if not (0.0 <= self.confidence_score <= 1.0):
            raise ValueError(f"Confidence score out of range: {self.confidence_score}")

@dataclass
class SectionConfig:
    """Configuration for managing section visibility and display."""
    show_risk_section: bool
    show_protective_section: bool
    risk_variant_count: int
    protective_variant_count: int
    section_priority: SectionPriority
    condition_name: Optional[str] = None
    custom_headers: Dict[str, str] = field(default_factory=dict)
    display_order: List[SectionType] = field(default_factory=list)

@dataclass
class ReportSection:
    """Organized variant data for specific report sections."""
    section_type: SectionType
    condition: str
    risk_variants: List[EnhancedVariant]
    protective_variants: List[EnhancedVariant]
    show_risk_subsection: bool
    show_protective_subsection: bool
    summary_text: str
    section_title: Optional[str] = None
    clinical_recommendations: List[str] = field(default_factory=list)
