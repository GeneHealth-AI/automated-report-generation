import logging
from typing import Dict, List, Optional, Any
from data.models import EffectDirection, ConfidenceLevel

logger = logging.getLogger(__name__)

class VariantClassifier:
    """Streamlined engine for classifying genetic variants."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {
            'risk_thresholds': {'clinvar': 0.8, 'literature': 0.6, 'population': 0.7, 'functional': 0.5},
            'protective_thresholds': {'clinvar': 0.8, 'literature': 0.6, 'population': 0.7, 'functional': 0.5}
        }

    def classify(self, variant_data: Dict[str, Any]) -> Dict[str, Any]:
        """Classify a variant based on provided evidence."""
        rsid = variant_data.get('rsid', 'unknown')
        sources = []
        risk_score = 0.0
        protective_score = 0.0
        conflicting = False

        # 1. Primary Authority: Functional (Entprise)
        if func_score := variant_data.get('functional_impact'):
            try:
                score = float(func_score)
                sources.append('functional')
                if score > 0.6:
                    return {
                        "rsid": rsid,
                        "effect_direction": EffectDirection.RISK_INCREASING,
                        "confidence_level": ConfidenceLevel.HIGH,
                        "confidence_score": 0.9,
                        "evidence_sources": sources,
                        "reasoning": f"Primary classification as Risk-Increasing based on functional score ({score})."
                    }
                elif score < 0.4:
                    return {
                        "rsid": rsid,
                        "effect_direction": EffectDirection.NEUTRAL,
                        "confidence_level": ConfidenceLevel.HIGH,
                        "confidence_score": 0.9,
                        "evidence_sources": sources,
                        "reasoning": f"Primary classification as Neutral based on functional score ({score})."
                    }
            except (ValueError, TypeError):
                pass

        # 2. Secondary Evidence: Aggregate other sources if no strong functional evidence
        # ClinVar
        if cv := variant_data.get('clinvar_significance'):
            cv = cv.lower()
            sources.append('clinvar')
            if 'pathogenic' in cv: risk_score += self.config['risk_thresholds']['clinvar']
            elif 'benign' in cv: pass # Benign is neutral
            if 'conflicting' in cv: conflicting = True

        # Literature
        if lit := variant_data.get('literature_evidence'):
            sources.append('literature')
            if lit.get('risk_association'): risk_score += self.config['risk_thresholds']['literature']
            if lit.get('protective_association'): protective_score += self.config['protective_thresholds']['literature']

        # Population
        if pop := variant_data.get('population_frequency'):
            sources.append('population')
            if pop.get('associated_with_disease'): risk_score += self.config['risk_thresholds']['population']
            if pop.get('protective_effect'): protective_score += self.config['protective_thresholds']['population']

        # 3. Determine Direction
        if risk_score > protective_score and risk_score >= 0.5:
            direction = EffectDirection.RISK_INCREASING
        elif protective_score > risk_score and protective_score >= 0.5:
            direction = EffectDirection.PROTECTIVE
        elif conflicting:
            direction = EffectDirection.NEUTRAL
        else:
            direction = EffectDirection.UNKNOWN

        # 3. Calculate Confidence
        avg_score = max(risk_score, protective_score) / max(len(sources), 1)
        if avg_score >= 0.7: confidence = ConfidenceLevel.HIGH
        elif avg_score >= 0.4: confidence = ConfidenceLevel.MODERATE
        else: confidence = ConfidenceLevel.LOW

        return {
            "rsid": rsid,
            "effect_direction": direction,
            "confidence_level": confidence,
            "confidence_score": min(avg_score, 1.0),
            "evidence_sources": sources,
            "reasoning": f"Classified based on {', '.join(sources)} evidence."
        }
