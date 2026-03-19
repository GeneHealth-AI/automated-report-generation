import logging
import json
import os
from typing import Dict, List, Any, Optional

from data.models import BlockType, EnhancedVariant, EffectDirection
from core.processing import convert_to_rsid, normalize_hgvs, parse_vcf
from core.classification import VariantClassifier
from engine.generator import BlockGenerationEngine
from data.storage import download_from_s3, upload_to_s3

logger = logging.getLogger(__name__)

class ReportCoordinator:
    """Main orchestrator for report generation."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.generator = BlockGenerationEngine()
        self.classifier = VariantClassifier()
        
    def run(self, vcf_path: str, template_path: str, patient_info: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the full report generation pipeline."""
        logger.info(f"Starting report generation for {patient_info.get('patient_name')}")
        
        # 1. Load Template
        with open(template_path, 'r') as f:
            template = json.load(f)
        
        # 2. Process Variants
        raw_variants = parse_vcf(vcf_path)
        if not raw_variants:
            logger.warning("No variants found in VCF.")
            # Fallback or empty report handling could go here
        rsid_pairs = convert_to_rsid(raw_variants)
        
        # 3. Classify Variants
        enhanced_variants = []
        for orig, rsid in rsid_pairs:
            # Mocking variant data for classifier
            variant_data = {
                "rsid": rsid or "unknown",
                "clinvar_significance": "Pathogenic",
                "literature_evidence": {"risk_association": True}
            }
            classification = self.classifier.classify(variant_data)
            
            # Skip variants that are not clinically impactful (Risk or Protective)
            if classification['effect_direction'] not in [EffectDirection.RISK_INCREASING, EffectDirection.PROTECTIVE]:
                continue
                
            enhanced_variants.append(EnhancedVariant(
                rsid=rsid or "unknown",
                gene="GENE", # Mocked
                effect_direction=classification['effect_direction'],
                effect_magnitude=1.0, # Mocked
                confidence_level=classification['confidence_level'],
                confidence_score=classification['confidence_score'],
                condition_associations=[template.get('category', 'General')],
                evidence_sources=classification['evidence_sources']
            ))

        # 4. Prepare Data for LLM
        mutations_summary = ", ".join([v.rsid for v in enhanced_variants])
        generation_data = {
            "category": template.get("category", "Genetic Risk"),
            "patient_name": patient_info.get("patient_name"),
            "mutations_summary": mutations_summary,
            "mutations_data": [v.__dict__ for v in enhanced_variants],
            "patient_genes": list(set([v.gene for v in enhanced_variants])),
            "literature_data": "Literature context retrieved via RAG...",
            "risk_data": "Risk assessment calculated from variants..."
        }

        # 5. Generate Blocks
        blocks_to_run = [BlockType.INTRODUCTION, BlockType.EXECUTIVE_SUMMARY, BlockType.MUTATION_PROFILE, BlockType.CONCLUSION]
        generated_blocks = self.generator.generate_all_blocks(blocks_to_run, generation_data)
        
        # 6. Assemble Report
        report = {
            "report_metadata": {
                "patient_name": patient_info.get("patient_name"),
                "patient_id": patient_info.get("patient_id"),
                "generated_at": "2026-02-06",
                "version": "2.0.0"
            },
            "blocks": {b.block_type.value: b.__dict__ for b in generated_blocks}
        }
        
        return report
