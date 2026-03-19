from __future__ import annotations
import os
import json
import logging
import traceback
from typing import Any, Optional, Union, cast, Literal, List
from dataclasses import asdict
from block_generator import ReportBlockGenerator
from pubmed_searcher import PubMedSearcher
from report_blocks import BlockType, ReportBlock
from EnrichPositions import enrich_positions
from mutation_description_generator import MutationDescriptionGenerator
from Bio import Entrez
import re
import requests
import google.generativeai as genai
from block_generator import generate_gemini_response, GEMINI_AVAILABLE
from collections.abc import Iterable
from token_counter import analyze_block_data
from variant_classifier import EffectDirection
from enhanced_data_models import EnhancedVariant, ProteinDiseaseAssociation


MIN_SCORE = .6


BLOCK_PATH = './blocks'
KNOWGENE_PATH = './allproteins2knowgene'

# Clinical Risk and Evidence Mappings
LIFETIME_RISK_MAPPING = {
    'PRSS1': {'absolute': '40-50% by age 70', 'population': '1-2%', 'tier': 'Tier 1'},
    'STK11': {'absolute': '30-40% by age 70', 'population': '1-2%', 'tier': 'Tier 1'},
    'CDKN2A': {'absolute': '15-20% by age 70', 'population': '1-2%', 'tier': 'Tier 1'},
    'BRCA2': {'absolute': '5-10% by age 70', 'population': '1-2%', 'tier': 'Tier 2'},
    'PALB2': {'absolute': '3-5% by age 70', 'population': '1-2%', 'tier': 'Tier 2'},
    'ATM': {'absolute': '3-5% by age 70', 'population': '1-2%', 'tier': 'Tier 2'},
    'SPINK1': {'absolute': '5% by age 70', 'population': '1-2%', 'tier': 'Tier 2'},
    'MLH1': {'absolute': '2-4% by age 70', 'population': '1-2%', 'tier': 'Tier 2'},
    'MSH2': {'absolute': '2-4% by age 70', 'population': '1-2%', 'tier': 'Tier 2'},
    'MSH6': {'absolute': '2-4% by age 70', 'population': '1-2%', 'tier': 'Tier 2'},
    'PMS2': {'absolute': '1-2% by age 70', 'population': '1-2%', 'tier': 'Tier 3'},
    'CFTR': {'absolute': 'Modestly increased risk', 'population': '1-2%', 'tier': 'Tier 3'},
    'CTRBC': {'absolute': 'Modestly increased risk', 'population': '1-2%', 'tier': 'Tier 3'}
}


# Configure logger for this module
logger = logging.getLogger(__name__)

import hashlib

def get_file_hash(path):
    """Calculate SHA256 hash of a file's contents."""
    if not path or not os.path.exists(path):
        return "no_file"
    sha256_hash = hashlib.sha256()
    with open(path, "rb") as f:
        # Read in chunks to handle large files
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

HGVS_RE = re.compile(r"^chr?(\d+|X|Y|M):g\.\d+[ACGTN]+>[ACGTN]+$", re.I)
VARIANT_RECODER = "https://rest.ensembl.org/variant_recoder/homo_sapiens"
HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}
        


def extract_mutated_genes(
    np_accessions: list[str],
    email: str,
    api_key: str | None = None
) -> list[str]:
    Entrez.email = 'sskolusa@gmail.com'
    if api_key:
        Entrez.api_key = api_key

    gene_list: list[str] = []
    for np_acc in np_accessions:
        try:
            # link NP_ → Gene ID
            link_handle = Entrez.elink(dbfrom="protein", db="gene", id=np_acc)
            link_records = Entrez.read(link_handle)
            link_handle.close()
            gene_id = link_records[0]["LinkSetDb"][0]["Link"][0]["Id"]

            # fetch gene summary and extract symbol
            summary_handle = Entrez.esummary(db="gene", id=gene_id)
            summary_record = Entrez.read(summary_handle)
            summary_handle.close()
            gene_symbol = summary_record["DocumentSummarySet"]["DocumentSummary"][0]["Name"]

            gene_list.append(gene_symbol)
        except Exception:
            # skip if any step fails
            continue

    return gene_list
def _normalise(var: Union[str, tuple[str, str]]) -> str:
    """Return upper-case, ‘chr’-stripped HGVS for the API call."""
    if isinstance(var, tuple):
        var = var[0]            # discard allele if present
    var = var.strip()
    if not HGVS_RE.match(var):
        raise ValueError(f"Unrecognised HGVS: {var}")
    # Remove 'chr' prefix and format correctly
    # Keep 'g.' lowercase but make the alleles uppercase
    normalized = var.lstrip("chr")
    
    # Split into parts to handle case correctly
    if ':g.' in normalized:
        chr_part, rest = normalized.split(':g.')
        # Make chromosome uppercase (for X, Y, M) and alleles uppercase
        # but keep 'g.' lowercase
        position_part = rest.upper()  # This makes the alleles uppercase
        return f"{chr_part.upper()}:g.{position_part}"
    else:
        # Fallback if format is unexpected
        return normalized

def convert_to_rsid_pairs(
    variants: Iterable[Union[str, tuple[str, str]]],
    chunk: int = 200
) -> list[tuple[Union[str, tuple[str, str]], str]]:
    """
    Return a list of (original_input, rsID_or_None) in the same order
    the variants were supplied, with no dictionary wrapping.
    """
    original: list[Union[str, tuple[str, str]]] = list(variants)
    
    # Normalize variants
    try:
        hgvs = [_normalise(v) for v in original]
    except ValueError as e:
        logger.warning(f"Failed to normalize variants: {e}")
        return [(v, None) for v in original]
    
    rsids: list[str] = [None] * len(original)          # placeholder list

    for i in range(0, len(hgvs), chunk):
        payload = {"ids": hgvs[i : i + chunk]}
        
        try:
            logger.info("🔧 DEBUG: Making requests.post call to VARIANT_RECODER")
            resp = requests.post(VARIANT_RECODER, json=payload,
                                 headers=HEADERS, timeout=30, proxies={})
            logger.info("✅ DEBUG: requests.post completed successfully")
            resp.raise_for_status()
            
            response_data = resp.json()
            
            for item in response_data:
                # The response structure has the allele as the key
                # e.g., {'C': {'id': ['rs2792751', ...], 'input': '10:G.112180571T>C'}}
                rsid = None
                input_variant = None
                
                for allele, data in item.items():
                    if isinstance(data, dict) and 'id' in data:
                        # Find the first rsID in the id list
                        for id_val in data.get('id', []):
                            if id_val.startswith('rs'):
                                rsid = id_val
                                break
                        input_variant = data.get('input')
                        break
                
                if rsid and input_variant:
                    try:
                        idx = i + payload["ids"].index(input_variant)
                        rsids[idx] = rsid
                    except ValueError:
                        logger.warning(f"Could not find {input_variant} in payload")
                        
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            logger.error(f"❌ DEBUG: RequestException type: {type(e).__name__}")
            
            # Check if this is the proxies error
            if "proxies" in str(e):
                logger.error("🚨 DEBUG: FOUND THE PROXIES ERROR! It's coming from requests.post")
                logger.error(f"🚨 DEBUG: Proxies error in requests: {str(e)}")
            
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response: {e.response.text}")
        except Exception as e:
            logger.error(f"Unexpected error in rsID conversion: {e}")
            logger.error(f"❌ DEBUG: Exception type in rsID conversion: {type(e).__name__}")
            
            # Check if this is the proxies error
            if "proxies" in str(e):
                logger.error("🚨 DEBUG: FOUND THE PROXIES ERROR! It's coming from rsID conversion")
                logger.error(f"🚨 DEBUG: Proxies error in rsID conversion: {str(e)}")
                logger.error(f"❌ DEBUG: Full traceback: {traceback.format_exc()}")

    return list(zip(original, rsids))


def extract_genes(text):
    return [
        fields[1]
        for line in text.splitlines()
        if (fields := line.split(",")) and len(fields) > 1
    ]

def extract_positions(text):
    return [
        (fields[3], fields[2])
        for line in text.splitlines()
        if (fields := line.split(",")) and len(fields) > 3
    ]



class Report:
    '''This is a class that is saved to allow an inidividual or a provider to save the format of the report that they are interested in.
    This can generate two types of reports:
        1. gene_only: Only reports on the presence or absence of mutations for a specific set of genes and provides background information on those genes and mutations. Requires no prompt.
        2. gene_prompt report: the healthcare provider chooses the genes of interest. These genes are the only ones that are evaluted in the context of the prompt
        3. GH_enhanced: This uses clinvar data and GH predictions to provide a detailed analysis in the context of a prompt.
    '''
    pubmed_searcher: PubMedSearcher
    
    def __init__(self, report_type='gene_prompt', prompt=None, blocks=[], specifics='', 
                 template_data=None, template_id=None, name=None, creator=None, 
                 category=None, version="1.0.0"):
        logger.info("🔧 DEBUG: Report.__init__() starting")
        
        try:
            # JSON template support
            logger.info("🔧 DEBUG: Setting up template metadata")
            self.template_id = template_id or str(__import__('uuid').uuid4())
            self.name = name
            self.creator = creator
            self.created_date = __import__('datetime').datetime.now().isoformat()
            self.last_modified = None
            self.version = version
            self.category = category
            self.data_requirements = {}
            self.metadata = {}
            self.permissions = {"is_public": False, "shared_with": [], "editable_by": []}
            self.style = {}
            logger.info("✅ DEBUG: Template metadata set successfully")
        except Exception as e:
            logger.error(f"❌ DEBUG: Error in Report.__init__ metadata setup: {str(e)}")
            raise
        
        # Legacy supported
        self.prompt = prompt
        self.blocks = blocks
        if not self.blocks:
            # Convert string block names to BlockType enums
            default_block_names = [
                'introduction', 'executive_summary', 'mutation_profile', 
                'literature_evidence', 'risk_assessment', 'clinical_implications', 
                'lifestyle_recommendations', 'monitoring_plan',
                'conclusion'
            ]
            self.blocks = [BlockType(name) for name in default_block_names]
        else:
            # Convert string blocks to BlockType enums if needed
            converted_blocks = []
            for block in self.blocks:
                if isinstance(block, str):
                    converted_blocks.append(BlockType(block))
                else:
                    converted_blocks.append(block)
            self.blocks = converted_blocks
            
        self.report_type = report_type
        #self.goi = extract_genes(specifics) # not fixed yet
        #self.poi = extract_positions(specifics) # not fixed yet
        self.feedback = None # needed if revision
        self.searcher = None    # searcher
        
        try:
            # Blocks config
            logger.info("🔧 DEBUG: Setting up block configs")
            self.block_configs = {'custom_prompt':self.prompt}  # Store block-specific configurations
            logger.info("✅ DEBUG: Block configs set successfully")
            
            logger.info("🔧 DEBUG: Creating ReportBlockGenerator instance")
            self.block_generator = ReportBlockGenerator(blocks_path=BLOCK_PATH, block_configs=self.block_configs)
            self.pubmed_searcher = PubMedSearcher()
            logger.info("✅ DEBUG: ReportBlockGenerator and PubMedSearcher created successfully")
            
            logger.info("🔧 DEBUG: Creating MutationDescriptionGenerator instance")
            self.mutation_desc_generator = MutationDescriptionGenerator()
            logger.info("✅ DEBUG: MutationDescriptionGenerator created successfully")
        except Exception as e:
            logger.error(f"❌ DEBUG: Error creating ReportBlockGenerator: {str(e)}")
            logger.error(f"❌ DEBUG: ReportBlockGenerator traceback: {traceback.format_exc()}")
            raise
        
        # Initialize metadata mappings
        self._refseq_to_uniprot: dict[str, str] = {}
        self._uniprot_to_info: dict[str, dict[str, Any]] = {}
        
        # Risk and protective variants
        self.risk_variants: list[tuple[EnhancedVariant, EffectDirection]] = []
        self.protective_variants: list[tuple[EnhancedVariant, EffectDirection]] = []
        
        # Initialize attributes that will be used in to_json
        self.goi: list[str] = extract_genes(specifics)
        self.poi: list[tuple[str, str]] = extract_positions(specifics)
        
        # If template_data provided, load from JSON
        try:
            if template_data:
                logger.info("🔧 DEBUG: Loading template data from JSON")
                self.from_json(template_data)
                logger.info("✅ DEBUG: Template data loaded successfully")
        except Exception as e:
            logger.error(f"❌ DEBUG: Error loading template data: {str(e)}")
            logger.error(f"❌ DEBUG: Template data traceback: {traceback.format_exc()}")
            raise

    def to_json(self) -> dict[str, Any]:
        """Convert report configuration to JSON format."""
        block_names = ','.join([block.value for block in self.blocks])
        
        # Create specifics string from genes and positions
        specifics = ""
        for gene in self.goi:
            specifics += f",{gene},,\n"
        for pos, val in self.poi:
            specifics += f",,,{pos},{val}\n"
        
        # Convert risk and protective variants to serializable format
        risk_vars = []
        protective_vars = []
        
        try:
            from dataclasses import asdict
            for v, ed in self.risk_variants:
                v_dict = cast(dict[str, Any], asdict(v))
                v_dict['effect_direction'] = ed.value
                risk_vars.append(v_dict)
            
            for v, ed in self.protective_variants:
                v_dict = cast(dict[str, Any], asdict(v))
                v_dict['effect_direction'] = ed.value
                protective_vars.append(v_dict)
        except Exception as e:
            logger.warning(f"Error serializing variants: {e}")

        return {
            'template_id': self.template_id,
            'creator': self.creator,
            'name': self.name,
            'focus': self.prompt,
            'blocks': block_names,
            'specifics': specifics,
            'only_specifics': 'TRUE' if self.report_type == 'gene_only' else 'FALSE',
            'risk_variants': risk_vars,
            'protective_variants': protective_vars
        }
    
    def from_json(self, template_data):
        """
        Load report configuration from JSON data.
        
        Args:
            template_data: Dictionary containing template configuration
        """
        # Load basic metadata
        self.template_id = template_data.get('template_id', self.template_id)
        self.creator = template_data.get('creator', self.creator)
        self.name = template_data.get('name', self.name)
        self.prompt = template_data.get('focus', self.prompt)
        
        # Load blocks
        if 'sections' in template_data:
            logger.info(f"Loading blocks from sections: {template_data['sections']}")
            sections = template_data['sections']
            self.blocks = []
            for section in sections:
                stype = section.get('type')
                if stype:
                    try:
                        # Try case-insensitive mapping to BlockType
                        bt = BlockType(stype.lower())
                        self.blocks.append(bt)
                    except ValueError:
                        logger.warning(f"Unknown block type in section: {stype}")
        elif 'blocks' in template_data:
            logger.info(f"BLOCKS FOR EXAMINATION {template_data['blocks']}")
            blocks_data = template_data['blocks']
            
            # Handle both string and list formats
            if isinstance(blocks_data, str):
                # Split comma-separated string
                block_names = [name.strip() for name in blocks_data.split(',') if name.strip()]
            elif isinstance(blocks_data, list):
                block_names = blocks_data
            else:
                logger.warning(f"Unexpected blocks format: {type(blocks_data)}")
                block_names = []
            
            self.blocks = [BlockType(name) for name in block_names if name in [bt.value for bt in BlockType]]
        
        ''' # Load specifics (genes or rsIDs)
        if 'specifics' in template_data:
            specifics = template_data['specifics']
            self.goi = extract_genes(specifics)
            self.poi = extract_positions(specifics)
        
        # Set report type based on only_specifics flag
        if template_data.get('only_specifics', '').upper() == 'TRUE':
            self.report_type = 'gene_only'
        else:
            self.report_type = 'gene_prompt'  '''
        
        # Update block configs
        self.block_configs = {'custom_prompt': self.prompt}
        
        # Recreate block generator with updated configs
        self.block_generator = ReportBlockGenerator(blocks_path=BLOCK_PATH, block_configs=self.block_configs)
        
        # Store last modified time
        self.last_modified = __import__('datetime').datetime.now().isoformat()
        
        return self
    
    def save_template_json(self, path):
        """Save template in JSON format"""
        try:
            import json
            template_data = self.to_json()
            with open(path, 'w') as f:
                json.dump(template_data, f, indent=2)
            logger.info(f"Template saved successfully to {path}")
            return True
        except Exception as e:
            logger.error(f"Error saving template: {str(e)}")
            return False
    
    def load_template_json(self, path):
        """Load template from JSON file"""
        try:
            import json
            with open(path, 'r') as f:
                template_data = json.load(f)
            self.from_json(template_data)
            logger.info(f"Template loaded successfully from {path}")
            return self
        except Exception as e:
            logger.error(f"Error loading template: {str(e)}")
            raise ValueError(f"Failed to load template from {path}: {str(e)}")
            
    def generate_diseases(self, knowgene_path: str, vcf_path: str) -> tuple[set[str], list[Any], dict[str, list[Any]], list[Any]]:
        '''
        Enhanced method to classify variants by effect direction during disease generation.
        
        Input: file path to data
        files of the format example:
        ('chr15:g.66528912A>G','G')	NP_060445.3	344	SER	GLY	0.168077499
        
        Will run Knowgene analysis and track mutations with proteins, now including
        variant classification for risk/protective effect categorization.

        '''
        try:
            from variant_classifier import VariantClassifier, EffectDirection, ConfidenceLevel
            from section_manager import SectionManager
            enhanced_features_available = True
        except ImportError as e:
            logger.warning(f"Enhanced features not available: {e}. Using basic functionality.")
            enhanced_features_available = False
        
        # Initialize variant classifier with caching (only if enhanced features available)
        if enhanced_features_available:
            if not hasattr(self, '_variant_classifier'):
                self._variant_classifier = VariantClassifier()
                self._classification_cache = {}  # Add classification caching for performance
            
            # Initialize section manager for enhanced report generation workflow
            if not hasattr(self, '_section_manager'):
                self._section_manager = SectionManager()
        
        protein2disease = {}
        proteins = set()
        protein_diseases = []
        protein_mutations = {}  # Track mutations for each protein
        classified_variants = []  # New: Track classified variants
        
        with open(knowgene_path,'r') as kg:
            for line in kg:
                parts = [p.strip() for p in line.split('\t')]
                if len(parts) >= 2:
                    protein = parts[0]
                    diseases = parts[1].split(';') if len(parts) > 1 else []
                    newdiseases = ''
                    for d in diseases:
                        d = d.split(':')
                        MIN_SCORE = 0.3
                        if len(d) >= 2 and eval(d[0]) > MIN_SCORE:
                            newdiseases += d[1] + ', '
                    protein2disease[protein] = newdiseases
        
        variants_to_convert = []
        with open(vcf_path,'r') as data:
            for line in data:
                parts = [p.strip() for p in line.split('\t')]
                if len(parts) < 6:  # Need at least variant, protein, position, ref, alt, score
                    continue
                    
                # Parse the variant tuple - format is like: ('chr15:g.66528912A>G','G')
                variant_str = parts[0]
                protein = parts[1].strip()
                position = parts[2]
                ref_aa = parts[3]
                alt_aa = parts[4]
                score = parts[-1]
                MIN_SCORE = 0.5  # Lowered to match association threshold
                
                try:
                    score_val = float(score)
                    if score_val > MIN_SCORE:
                        proteins.add(protein)
                        
                        # Track mutation details for this protein
                        if protein not in protein_mutations:
                            protein_mutations[protein] = []
                        
                        # Extract HGVS from tuple format
                        hgvs = ""
                        allele = ""
                        if variant_str.startswith("('") and "','" in variant_str:
                            # Parse tuple format: ('chr15:g.66528912A>G','G')
                            hgvs = variant_str.split("','")[0].strip("('")
                            allele = variant_str.split("','")[1].strip("')")
                        else:
                            # Assume it's just the HGVS string
                            hgvs = variant_str
                        
                        # Store mutation information (with or without enhanced classification)
                        if enhanced_features_available:
                            # Classify variant by effect direction
                            variant_classification = self._classify_variant_with_caching(
                                hgvs, protein, position, ref_aa, alt_aa, score_val, protein2disease.get(protein, '')
                            )
                            
                            gene_name = self._extract_gene_name_from_protein(protein)
                            
                            # Store mutation information with classification metadata
                            mutation_info = {
                                'variant': hgvs,
                                'allele': allele,
                                'position': position,
                                'ref_amino_acid': ref_aa,
                                'alt_amino_acid': alt_aa,
                                'score': score_val,
                                'mutation_description': self.mutation_desc_generator.generate_description(
                                    gene=gene_name,
                                    ref_aa=ref_aa,
                                    position=position,
                                    alt_aa=alt_aa,
                                    diseases=protein2disease.get(protein, '')
                                ),
                                # Add classification metadata
                                'effect_direction': variant_classification.effect_direction,
                                'confidence_level': variant_classification.confidence_level,
                                'confidence_score': variant_classification.confidence_score,
                                'evidence_sources': variant_classification.evidence_sources,
                                'classification_reasoning': variant_classification.reasoning,
                                # New dual-usability fields
                                'clinical_significance': self._infer_clinical_significance(score_val, ref_aa, alt_aa),
                                'evidence_strength': self._infer_evidence_strength(score_val, variant_classification.evidence_sources),
                                'absolute_risk_range': LIFETIME_RISK_MAPPING.get(gene_name, {}).get('absolute'),
                                'population_risk': LIFETIME_RISK_MAPPING.get(gene_name, {}).get('population'),
                                'risk_tier': LIFETIME_RISK_MAPPING.get(gene_name, {}).get('tier')
                            }
                            
                            # Create enhanced variant object
                            try:
                                # Extract gene name from protein info or use protein ID
                                gene_name = self._extract_gene_name_from_protein(protein)
                                
                                # Get associated conditions from protein-disease mapping
                                associated_conditions = self._extract_conditions_from_diseases(protein2disease.get(protein, ''))
                                
                                enhanced_variant = EnhancedVariant(
                                    rsid=hgvs,  # Use HGVS as identifier for now
                                    gene=gene_name,
                                    effect_direction=variant_classification.effect_direction,
                                    effect_magnitude=score_val,
                                    confidence_level=variant_classification.confidence_level,
                                    confidence_score=variant_classification.confidence_score,
                                    condition_associations=associated_conditions,
                                    evidence_sources=variant_classification.evidence_sources,
                                    alt_allele=alt_aa,
                                    functional_impact=f"Score: {score_val}",
                                    clinical_significance=self._infer_clinical_significance(score_val, ref_aa, alt_aa),
                                    evidence_strength=self._infer_evidence_strength(score_val, variant_classification.evidence_sources),
                                    absolute_risk_range=LIFETIME_RISK_MAPPING.get(gene_name, {}).get('absolute'),
                                    population_risk=LIFETIME_RISK_MAPPING.get(gene_name, {}).get('population'),
                                    risk_tier=LIFETIME_RISK_MAPPING.get(gene_name, {}).get('tier'),
                                    # Verified variant data from parsed input
                                    ref_amino_acid=ref_aa,
                                    alt_amino_acid=alt_aa,
                                    amino_acid_position=str(position) if position else None,
                                    score=score_val,
                                    hgvs=hgvs,
                                    protein_id=protein,
                                )
                                classified_variants.append(enhanced_variant)
                                
                            except Exception as e:
                                logger.warning(f"Error creating enhanced variant for {hgvs}: {str(e)}")
                        else:
                            # Basic mutation information without enhanced classification
                            mutation_info = {
                                'variant': hgvs,
                                'allele': allele,
                                'position': position,
                                'ref_amino_acid': ref_aa,
                                'alt_amino_acid': alt_aa,
                                'score': score_val,
                                'score': score_val,
                                'mutation_description': self.mutation_desc_generator.generate_description(
                                    gene=protein, # Fallback to protein ID if we aren't using enhanced extraction yet
                                    ref_aa=ref_aa,
                                    position=position,
                                    alt_aa=alt_aa,
                                    diseases=protein2disease.get(protein, '')
                                )
                            }
                        
                        protein_mutations[protein].append(mutation_info)
                    
                    if score_val > MIN_SCORE:
                        # Extract HGVS from tuple format
                        if variant_str.startswith("('") and "','" in variant_str:
                            # Parse tuple format: ('chr15:g.66528912A>G','G')
                            hgvs = variant_str.split("','")[0].strip("('")
                            allele = variant_str.split("','")[1].strip("')")
                            variants_to_convert.append((hgvs, allele))
                        else:
                            # Assume it's just the HGVS string
                            variants_to_convert.append(variant_str)
                        
                        # Protein-disease association processing
                        if protein in proteins and protein in protein2disease.keys():
                            if enhanced_features_available:
                                # Create enhanced protein-disease association
                                enhanced_association = self._create_enhanced_protein_disease_association(
                                    protein, protein2disease[protein], protein_mutations.get(protein, [])
                                )
                                protein_diseases.append((protein, protein2disease[protein], enhanced_association))
                            else:
                                # Basic protein-disease association
                                protein_diseases.append((protein, protein2disease[protein]))
                            
                except (ValueError, IndexError) as e:
                    logger.warning(f"Error parsing line: {line}")
                    continue

        # Log classification statistics (only if enhanced features available)
        if enhanced_features_available:
            self._log_classification_statistics(classified_variants)
            # Store classified variants for use by enhanced report generation workflow
            self._classified_variants = classified_variants
        else:
            # For basic functionality, set empty classified variants
            classified_variants = []
        
        return proteins, protein_diseases, protein_mutations, classified_variants
    
    def get_variants_by_condition(self) -> dict[str, list[Any]]:
        """
        Get variants organized by condition for enhanced section management.
        
        Returns:
            Dictionary mapping condition names to lists of enhanced variants
            
        Requirements: 4.1, 4.2
        """
        if not hasattr(self, '_classified_variants') or not self._classified_variants:
            logger.warning("No classified variants available. Run generate_diseases first.")
            return {}
        
        from enhanced_data_models import EnhancedVariant
        
        variants_by_condition = {}
        
        from variant_classifier import EffectDirection
        
        for variant in self._classified_variants:
            if isinstance(variant, EnhancedVariant):
                # Filter out Neutral and Unknown variants - only include Risk and Protective
                if variant.effect_direction not in [EffectDirection.RISK_INCREASING, EffectDirection.PROTECTIVE]:
                    continue
                    
                for condition in variant.condition_associations:
                    if condition not in variants_by_condition:
                        variants_by_condition[condition] = []
                    variants_by_condition[condition].append(variant)
        
        logger.info(f"Organized variants into {len(variants_by_condition)} conditions")
        return variants_by_condition
    
    def determine_section_configurations(self) -> dict[str, Any]:
        """
        Determine section configurations using the enhanced classification system.
        
        Returns:
            Dictionary mapping conditions to their section configurations
            
        Requirements: 4.1, 4.2
        """
        if not hasattr(self, '_section_manager'):
            from section_manager import SectionManager
            self._section_manager = SectionManager()
        
        variants_by_condition = self.get_variants_by_condition()
        
        if not variants_by_condition:
            logger.warning("No variants by condition available for section configuration")
            return {}
        
        # Use section manager to determine configurations
        section_configs = self._section_manager.evaluate_section_necessity_per_condition(
            variants_by_condition
        )
        
        logger.info(f"Generated section configurations for {len(section_configs)} conditions")
        return section_configs
    
    def get_enhanced_report_data(self) -> dict[str, Any]:
        """
        Get enhanced report data with section management support.
        
        Returns:
            Dictionary containing enhanced report data with section configurations
            
        Requirements: 4.1, 4.2, 4.3
        """
        # Get section configurations
        section_configs = self.determine_section_configurations()
        variants_by_condition = self.get_variants_by_condition()
        
        # Prepare enhanced data structure
        enhanced_data = {
            'section_configurations': section_configs,
            'variants_by_condition': variants_by_condition,
            'classified_variants': getattr(self, '_classified_variants', []),
            'has_enhanced_classification': True,
            'backward_compatible': True  # Flag for backward compatibility
        }
        
        # Add legacy data for backward compatibility
        if hasattr(self, '_classified_variants'):
            # Convert enhanced variants back to legacy format for compatibility
            legacy_mutations = {}
            for variant in self._classified_variants:
                gene = variant.gene
                if gene not in legacy_mutations:
                    legacy_mutations[gene] = []
                
                legacy_mutation = {
                    'variant': variant.rsid,
                    'position': 'Unknown',
                    'ref_amino_acid': variant.ref_allele or 'Unknown',
                    'alt_amino_acid': variant.alt_allele or 'Unknown',
                    'score': variant.effect_magnitude,
                    'mutation_description': f"{variant.ref_allele or 'Unknown'}{variant.alt_allele or 'Unknown'}",
                    # Include classification data for enhanced blocks
                    'effect_direction': variant.effect_direction,
                    'confidence_level': variant.confidence_level,
                    'confidence_score': variant.confidence_score
                }
                legacy_mutations[gene].append(legacy_mutation)
            
            enhanced_data['legacy_mutations'] = legacy_mutations
        
        return enhanced_data
    
    def migrate_legacy_data_to_enhanced(self, legacy_data: dict[str, Any]) -> dict[str, Any]:
        """
        Migrate existing report data to support enhanced classification system.
        
        Args:
            legacy_data: Existing report data in legacy format
            
        Returns:
            Enhanced data structure with backward compatibility
            
        Requirements: 4.4 (migration support for existing report data)
        """
        logger.info("Migrating legacy report data to enhanced format")
        
        # Start with legacy data
        enhanced_data = legacy_data.copy()
        
        # Add enhanced classification support flags
        enhanced_data['has_enhanced_classification'] = False  # Legacy data doesn't have classification
        enhanced_data['backward_compatible'] = True
        enhanced_data['migration_applied'] = True
        
        # Create empty enhanced structures for compatibility
        enhanced_data['section_configurations'] = {}
        enhanced_data['variants_by_condition'] = {}
        enhanced_data['classified_variants'] = []
        
        # Try to extract and convert legacy mutation data if available
        if 'PROTEIN_MUTATIONS' in legacy_data:
            try:
                legacy_mutations = legacy_data['PROTEIN_MUTATIONS']
                if isinstance(legacy_mutations, dict):
                    # Convert legacy mutations to basic enhanced format
                    from variant_classifier import EffectDirection, ConfidenceLevel
                    
                    converted_variants = []
                    for protein, mutations in legacy_mutations.items():
                        if isinstance(mutations, list):
                            for mutation in mutations:
                                if isinstance(mutation, dict):
                                    try:
                                        # Create basic enhanced variant from legacy data
                                        enhanced_variant = EnhancedVariant(
                                            rsid=mutation.get('variant', f"unknown_{protein}"),
                                            gene=protein,
                                            effect_direction=EffectDirection.UNKNOWN,  # Legacy data doesn't have classification
                                            effect_magnitude=mutation.get('score', 0.0),
                                            confidence_level=ConfidenceLevel.LOW,  # Conservative for legacy data
                                            confidence_score=0.5,  # Default confidence
                                            condition_associations=[],  # Legacy data doesn't have condition mapping
                                            evidence_sources=['legacy_migration'],
                                            ref_allele=mutation.get('ref_amino_acid'),
                                            alt_allele=mutation.get('alt_amino_acid'),
                                            functional_impact=mutation.get('mutation_description', '')
                                        )
                                        converted_variants.append(enhanced_variant)
                                    except Exception as e:
                                        logger.warning(f"Error converting legacy mutation for {protein}: {e}")
                    
                    enhanced_data['classified_variants'] = converted_variants
                    logger.info(f"Converted {len(converted_variants)} legacy mutations to enhanced format")
                    
            except Exception as e:
                logger.error(f"Error migrating legacy mutation data: {e}")
        
        # Add migration metadata
        enhanced_data['migration_metadata'] = {
            'migration_timestamp': __import__('datetime').datetime.now().isoformat(),
            'original_data_keys': list(legacy_data.keys()),
            'enhanced_features_available': False,
            'classification_system_version': 'legacy_migration'
        }
        
        logger.info("Legacy data migration completed")
        return enhanced_data
    
    def ensure_backward_compatibility(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Ensure backward compatibility with existing report templates and workflows.
        
        Args:
            data: Report data (enhanced or legacy)
            
        Returns:
            Data structure compatible with existing templates
            
        Requirements: 4.3 (backward compatibility with existing report templates)
        """
        # Always ensure legacy fields are present
        legacy_fields = [
            'MUTATED_PROTEINS', 'PROTEIN_DISEASES', 'PROTEIN_MUTATIONS',
            'PROTEIN_DISEASE_MUTATIONS', 'FAMILY_HISTORY', 'DEMOGRAPHICS',
            'GWAS_ASSOCIATIONS', 'GENESOFINTEREST', 'VARIANTS'
        ]
        
        for field in legacy_fields:
            if field not in data:
                data[field] = ''
        
        # If enhanced data is available, create legacy-compatible representations
        if data.get('has_enhanced_classification', False):
            # Convert enhanced variants back to legacy format for template compatibility
            if 'classified_variants' in data and data['classified_variants']:
                legacy_protein_mutations = {}
                legacy_mutated_proteins = set()
                
                for variant in data['classified_variants']:
                    gene = variant.gene
                    legacy_mutated_proteins.add(gene)
                    
                    if gene not in legacy_protein_mutations:
                        legacy_protein_mutations[gene] = []
                    
                    legacy_mutation = {
                        'variant': variant.rsid,
                        'position': 'Unknown',
                        'ref_amino_acid': variant.ref_allele or 'Unknown',
                        'alt_amino_acid': variant.alt_allele or 'Unknown',
                        'score': variant.effect_magnitude,
                        'mutation_description': f"{variant.ref_allele or 'Unknown'}{variant.alt_allele or 'Unknown'}"
                    }
                    legacy_protein_mutations[gene].append(legacy_mutation)
                
                # Update legacy fields
                data['MUTATED_PROTEINS'] = ', '.join(legacy_mutated_proteins)
                data['PROTEIN_MUTATIONS'] = legacy_protein_mutations
        
        # Ensure block generator compatibility
        data['backward_compatible'] = True

        # Pass lifetime risk mapping data for risk comparison visuals
        import json as _json
        data['RISK_DATA'] = _json.dumps(LIFETIME_RISK_MAPPING, indent=2)

        return data
    
    def _validate_variant_objects(self, variants: list[Any], condition: str) -> list[Any]:
        """
        Validate variant objects and filter out invalid ones.
        
        Args:
            variants: List of variant objects to validate
            condition: Condition name for logging context
            
        Returns:
            List of valid variant objects
        """
        if not variants:
            return []
        
        valid_variants = []
        for variant in variants:
            try:
                # Check if variant has required attributes
                if hasattr(variant, 'rsid') and hasattr(variant, 'gene') and hasattr(variant, 'effect_direction'):
                    valid_variants.append(variant)
                else:
                    logger.warning(f"Invalid variant object for condition {condition}: missing required attributes")
            except Exception as e:
                logger.warning(f"Error validating variant for condition {condition}: {e}")
        
        return valid_variants
    
    def _create_fallback_section_config(self, condition: str):
        """
        Create a fallback section configuration for error cases.
        
        Args:
            condition: Condition name
            
        Returns:
            Minimal SectionConfig object
        """
        from enhanced_data_models import SectionConfig, SectionPriority
        
        return SectionConfig(
            show_risk_section=False,
            show_protective_section=False,
            risk_variant_count=0,
            protective_variant_count=0,
            section_priority=SectionPriority.LOW,
            condition_name=condition
        )
    
    def _validate_section_config(self, section_config, variants: list[Any]) -> dict[str, Any]:
        """
        Validate section configuration consistency.
        
        Args:
            section_config: SectionConfig object to validate
            variants: List of variants for validation
            
        Returns:
            Dictionary with validation results
        """
        validation_result = {
            'is_valid': True,
            'errors': [],
            'warnings': []
        }
        
        # Check consistency between section visibility and variant counts
        if section_config.show_risk_section and section_config.risk_variant_count == 0:
            validation_result['warnings'].append("Risk section enabled but no risk variants present")
        
        if section_config.show_protective_section and section_config.protective_variant_count == 0:
            validation_result['warnings'].append("Protective section enabled but no protective variants present")
        
        # Check if variant counts match actual variants
        actual_variant_count = len(variants) if variants else 0
        expected_count = section_config.risk_variant_count + section_config.protective_variant_count
        
        if actual_variant_count != expected_count:
            validation_result['warnings'].append(
                f"Variant count mismatch: expected {expected_count}, actual {actual_variant_count}"
            )
        
        return validation_result
    
    def _classify_variant_with_caching(self, hgvs, protein, position, ref_aa, alt_aa, score, diseases):
        """
        Classify variant with caching for performance optimization.
        
        Args:
            hgvs: HGVS notation for the variant
            protein: Protein identifier
            position: Amino acid position
            ref_aa: Reference amino acid
            alt_aa: Alternate amino acid
            score: Variant score (Entprise/EntpriseX)
            diseases: Associated diseases string
            
        Returns:
            VariantClassification object
        """
        # Create cache key
        cache_key = f"{hgvs}_{protein}_{position}_{ref_aa}_{alt_aa}"
        
        # Check cache first
        if cache_key in self._classification_cache:
            return self._classification_cache[cache_key]
        
        # Prepare variant data for classification
        # We now prioritize the functional score (Entprise) as the absolute authority.
        # Literature is used for enrichment.
        
        has_risk_association = False
        if diseases:
            risk_keywords = ['cancer', 'pancreatitis', 'risk', 'pathogenic', 'susceptibility', 'disease']
            has_risk_association = any(kw in diseases.lower() for kw in risk_keywords)
            
        variant_data = {
            'rsid': hgvs,
            'gene': protein,
            'functional_impact': score, # Pass decimal score directly
            'literature_evidence': {
                'disease_associations': diseases,
                'risk_association': has_risk_association,
                'study_count': 1 if diseases else 0,
            }
            # No more simulated ClinVar or Population data - use raw functional evidence only
        }
        
        classification = self._variant_classifier.classify_variant(variant_data)
        self._classification_cache[cache_key] = classification
        return classification
        # Classify the variant
        classification = self._variant_classifier.classify_variant(variant_data)
        
        # Cache the result
        self._classification_cache[cache_key] = classification
        
        return classification
    
    def _extract_gene_name_from_protein(self, protein: str) -> str:
        """Extract gene name from protein identifier or return protein ID."""
        if hasattr(self, '_refseq_to_uniprot'):
            uniprot_acc = None
            if protein in self._refseq_to_uniprot:
                 uniprot_acc = self._refseq_to_uniprot[protein]
            elif '.' in protein:
                 base_id = protein.split('.')[0]
                 if base_id in self._refseq_to_uniprot:
                     uniprot_acc = self._refseq_to_uniprot[base_id]
            
            if uniprot_acc and hasattr(self, '_uniprot_to_info') and uniprot_acc in self._uniprot_to_info:
                info = self._uniprot_to_info[uniprot_acc]
                return str(info.get('gene_names', protein))
        return protein
    
    def _extract_conditions_from_diseases(self, diseases_string: str) -> list[str]:
        """Extract condition names from disease string."""
        if not diseases_string or diseases_string.strip() == '':
            return []
        
        # Split by comma and clean up
        conditions = [condition.strip() for condition in diseases_string.split(',') if condition.strip()]
        return conditions
    
    def _create_enhanced_protein_disease_association(self, protein, diseases_string, mutations):
        """
        Create enhanced protein-disease association with effect categorization.
        
        Args:
            protein: Protein identifier
            diseases_string: String of associated diseases
            mutations: List of mutations for this protein
            
        Returns:
            ProteinDiseaseAssociation object
        """
        from variant_classifier import EffectDirection
        
        # Calculate risk and protective magnitudes from mutations
        risk_magnitude = 0.0
        protective_magnitude = 0.0
        
        # These variables (risk_vars, protective_vars, self.risk_variants, self.protective_variants)
        # are not defined in this method or as class attributes.
        # The provided snippet seems to be from a different context or intended for a different method.
        # I will keep the original logic for calculating risk_magnitude and protective_magnitude
        # based on the 'mutations' parameter, as that is consistent with the method's signature.
        # If the intention was to use self.risk_variants/self.protective_variants,
        # those would need to be populated elsewhere in the class.
        
        # The user's provided snippet:
        # v: EnhancedVariant
        # effect_direction: EffectDirection
        # for v, effect_direction in self.risk_variants:
        #     v_dict = cast(dict[str, Any], asdict(v))
        #     v_dict['effect_direction'] = effect_direction.value
        #     risk_vars.append(v_dict)
        # for v, effect_direction in self.protective_variants:
        #     v_dict = cast(dict[str, Any], asdict(v))
        #     v_dict['effect_direction'] = effect_direction.value
        #     protective_vars.append(v_dict)
        # ude += score # This line is a syntax error and likely a typo.

        for mutation in mutations:
            effect_direction = mutation.get('effect_direction', EffectDirection.UNKNOWN)
            score = mutation.get('score', 0.0)
            
            if effect_direction == EffectDirection.RISK_INCREASING:
                risk_magnitude += score
            elif effect_direction == EffectDirection.PROTECTIVE:
                protective_magnitude += score
        
        # Determine overall effect direction
        if risk_magnitude > protective_magnitude:
            overall_effect = EffectDirection.RISK_INCREASING
        elif protective_magnitude > risk_magnitude:
            overall_effect = EffectDirection.PROTECTIVE
        else:
            overall_effect = EffectDirection.NEUTRAL
        
        # Extract primary condition (first disease in the string)
        primary_condition = diseases_string.split(',')[0].strip() if diseases_string else "Unknown"
        
        return ProteinDiseaseAssociation(
            protein=protein,
            condition=primary_condition,
            effect_direction=overall_effect,
            risk_magnitude=risk_magnitude,
            protective_magnitude=protective_magnitude,
            evidence_level="moderate",  # Default evidence level
            population_frequency=0.1,  # Default frequency
            clinical_actionability=len(mutations) > 0,
            absolute_risk_range=LIFETIME_RISK_MAPPING.get(self._extract_gene_name_from_protein(protein), {}).get('absolute'),
            population_risk=LIFETIME_RISK_MAPPING.get(self._extract_gene_name_from_protein(protein), {}).get('population'),
            risk_tier=LIFETIME_RISK_MAPPING.get(self._extract_gene_name_from_protein(protein), {}).get('tier'),
            source_databases=["KnowGene"],
            pubmed_ids=[],
            last_updated=None
        )
    
    def _estimate_population_frequency(self, score):
        """Estimate population frequency based on variant score."""
        # Higher scores suggest rarer, more impactful variants
        if score > 0.9:
            return 0.001  # Very rare
        elif score > 0.8:
            return 0.01   # Rare
        elif score > 0.7:
            return 0.05   # Uncommon
        else:
            return 0.1    # Common
    
    def _infer_clinical_significance(self, score: float, ref_aa: str, alt_aa: str) -> Literal['Pathogenic', 'Likely Pathogenic', 'VUS', 'Likely Benign', 'Benign']:
        """Infer clinical significance from variant characteristics using standard ACMG-like terms."""
        if score > 0.9:
            return "Pathogenic"
        elif score > 0.8:
            return "Likely Pathogenic"
        elif score > 0.6:
            return "VUS"
        elif score > 0.4:
            return "Likely Benign"
        else:
            return "Benign"

    def _infer_evidence_strength(self, score: float, evidence_sources: list[str]) -> Literal['Strong', 'Moderate', 'Emerging']:
        """Infer evidence strength (Strong, Moderate, Emerging) based on score and source count."""
        if score > 0.85 and len(evidence_sources) >= 2:
            return "Strong"
        elif score > 0.6:
            return "Moderate"
        else:
            return "Emerging"
    
    def _log_classification_statistics(self, classified_variants):
        """Log statistics about variant classifications."""
        if not classified_variants:
            logger.info("No variants were classified")
            return
        
        from variant_classifier import EffectDirection
        
        # Count variants by effect direction
        effect_counts = {direction: 0 for direction in EffectDirection}
        for variant in classified_variants:
            effect_counts[variant.effect_direction] += 1
        
        logger.info(f"Variant classification statistics:")
        logger.info(f"  Total variants classified: {len(classified_variants)}")
        logger.info(f"  Risk-increasing: {effect_counts[EffectDirection.RISK_INCREASING]}")
        logger.info(f"  Protective: {effect_counts[EffectDirection.PROTECTIVE]}")
        logger.info(f"  Neutral: {effect_counts[EffectDirection.NEUTRAL]}")
        logger.info(f"  Unknown: {effect_counts[EffectDirection.UNKNOWN]}")

    def _ensure_metadata_loaded(self):
        """Ensure protein metadata mapping files are loaded into class attributes."""
        if hasattr(self, '_refseq_to_uniprot') and self._refseq_to_uniprot:
            return # Already loaded
            
        # Try to find protein data files in several possible locations
        possible_paths = [
            'np_full_info/uniprot/np_to_uniprot_mapping.tsv',
            'GenerateAutomaticReport/np_full_info/uniprot/np_to_uniprot_mapping.tsv',
            os.path.join(os.path.dirname(__file__), 'np_full_info/uniprot/np_to_uniprot_mapping.tsv')
        ]
        
        np_to_uniprot_path = None
        for path in possible_paths:
            if os.path.exists(path):
                np_to_uniprot_path = path
                break
                
        if not np_to_uniprot_path:
            logger.warning("Could not find np_to_uniprot_mapping.tsv file. Using fallback mapping.")
            return
        
        # Find the essential info file in the same directory as the mapping file
        essential_info_dir = os.path.dirname(np_to_uniprot_path)
        essential_info_path = os.path.join(essential_info_dir, 'human_proteins_essential.tsv')
        
        # Load NP to UniProt mapping
        try:
            with open(np_to_uniprot_path, 'r') as f:
                for line in f:
                    parts = line.strip().split('\t')
                    if len(parts) >= 2:
                        np_id = parts[0]
                        uniprot_id = parts[1]
                        self._refseq_to_uniprot[np_id] = uniprot_id
                        if '.' in np_id:
                            base_id = np_id.split('.')[0]
                            if base_id not in self._refseq_to_uniprot:
                                self._refseq_to_uniprot[base_id] = uniprot_id
            logger.info(f"Loaded {len(self._refseq_to_uniprot)} NP to UniProt mappings")
        except Exception as e:
            logger.error(f"Error loading NP to UniProt mapping: {e}")

        # Load UniProt to Info (Gene Names, etc.)
        if os.path.exists(essential_info_path):
            try:
                with open(essential_info_path, 'r') as f:
                    f.readline() # Skip header
                    for line in f:
                        parts = line.strip().split('\t')
                        if len(parts) >= 4:
                            uniprot_acc = parts[0]
                            short_name = parts[1]
                            full_name = parts[2]
                            gene_names = parts[3]
                            self._uniprot_to_info[uniprot_acc] = {
                                'gene_names': gene_names.split(' ')[0],
                                'protein_name': f"{short_name} {full_name}"
                            }
                logger.info(f"Loaded {len(self._uniprot_to_info)} UniProt to Gene mappings")
            except Exception as e:
                logger.error(f"Error loading UniProt essential info: {e}")

    def add_context_proteins(self, proteins: list[str]) -> dict[str, dict[str, Any]]:
        """
        Enhanced method to add background info for proteins with classification metadata.
        """
        # Ensure mapping is loaded
        self._ensure_metadata_loaded()
        
        # Convert set to list if needed
        if isinstance(proteins, set):
            proteins = list(proteins)
        
        # Process each protein in the input list
        enriched_proteins = {}
        for protein in proteins:
            protein_dict = {'accession': protein}
            
            # Lookup in our loaded info
            uniprot_acc = self._refseq_to_uniprot.get(protein)
            if not uniprot_acc and '.' in protein:
                uniprot_acc = self._refseq_to_uniprot.get(protein.split('.')[0])
                
            info = self._uniprot_to_info.get(uniprot_acc) if uniprot_acc else None
            
            if info:
                protein_dict.update({
                    'name': info.get('protein_name', 'Unknown'),
                    'gene_name': info.get('gene_names', 'Unknown'),
                    'function': "Functional context loaded from database",
                    'disease': "Check Knowgene associations",
                    'go_terms': '',
                    'domains': '',
                    'uniprot_id': uniprot_acc
                })
            else:
                protein_dict.update({
                    'name': f"Protein {protein}",
                    'gene_name': self._extract_gene_name_from_protein(protein),
                    'function': "No function information available",
                    'disease': "No disease associations found",
                    'go_terms': '',
                    'domains': '',
                    'uniprot_id': uniprot_acc or ''
                })
            
            # Add classification metadata if available
            protein_dict.update(self._add_classification_metadata_to_protein(protein))
            enriched_proteins[protein] = protein_dict
        
        return enriched_proteins
    
    def _add_classification_metadata_to_protein(self, protein):
        """
        Add classification metadata to protein information.
        
        Args:
            protein: Protein identifier
            
        Returns:
            Dictionary with classification metadata
        """
        metadata = {
            'variant_classifications': [],
            'risk_variant_count': 0,
            'protective_variant_count': 0,
            'neutral_variant_count': 0,
            'high_confidence_variants': 0,
            'classification_summary': ''
        }
        
        # Check if we have classification cache for this protein
        if hasattr(self, '_classification_cache'):
            from variant_classifier import EffectDirection, ConfidenceLevel
            
            protein_classifications = []
            risk_count = 0
            protective_count = 0
            neutral_count = 0
            high_conf_count = 0
            
            # Find all cached classifications for this protein
            for cache_key, classification in self._classification_cache.items():
                if protein in cache_key:
                    protein_classifications.append({
                        'effect_direction': classification.effect_direction.value,
                        'confidence_level': classification.confidence_level.value,
                        'confidence_score': classification.confidence_score,
                        'reasoning': classification.reasoning
                    })
                    
                    # Count by effect direction
                    if classification.effect_direction == EffectDirection.RISK_INCREASING:
                        risk_count += 1
                    elif classification.effect_direction == EffectDirection.PROTECTIVE:
                        protective_count += 1
                    else:
                        neutral_count += 1
                    
                    # Count high confidence
                    if classification.confidence_level == ConfidenceLevel.HIGH:
                        high_conf_count += 1
            
            metadata.update({
                'variant_classifications': protein_classifications,
                'risk_variant_count': risk_count,
                'protective_variant_count': protective_count,
                'neutral_variant_count': neutral_count,
                'high_confidence_variants': high_conf_count,
                'classification_summary': self._generate_protein_classification_summary(
                    risk_count, protective_count, neutral_count, high_conf_count
                )
            })
        
        return metadata
    
    def _generate_protein_classification_summary(self, risk_count, protective_count, neutral_count, high_conf_count):
        """Generate a summary of protein variant classifications."""
        total_variants = risk_count + protective_count + neutral_count
        
        if total_variants == 0:
            return "No classified variants"
        
        summary_parts = []
        
        if risk_count > 0:
            summary_parts.append(f"{risk_count} risk-increasing")
        if protective_count > 0:
            summary_parts.append(f"{protective_count} protective")
        if neutral_count > 0:
            summary_parts.append(f"{neutral_count} neutral")
        
        summary = f"Contains {', '.join(summary_parts)} variants"
        
        if high_conf_count > 0:
            summary += f" ({high_conf_count} high-confidence)"
        
        return summary

    def make_proteins_text(self, proteins):
        """
        Convert protein information to a formatted text string.
        
        Args:
            proteins: Dictionary of proteins with their information, or a list of protein IDs
            
        Returns:
            Formatted text string with protein information
        """
        text = '''Here is a list of proteins that contain mutations as well as:
                gene_name, function, disease associated in the literature, go_terms, domains, uniprot_id,
                and variant classification information (risk/protective effect categorization)\n\n'''
        
        # Check if proteins is a dictionary or a list
        if isinstance(proteins, dict):
            # It's already a dictionary, use it directly
            protein_dict = proteins
        elif isinstance(proteins, (list, set)):
            # If it's a list or set, we need to create a fallback dictionary
            logger.warning("Proteins parameter is a list, not an enriched dictionary. Creating minimal information.")
            protein_dict = {}
            for protein_id in proteins:
                protein_dict[protein_id] = {
                    'name': f"Protein {protein_id}",
                    'gene_name': f"Gene for {protein_id}",
                    'function': "Function information not available",
                    'disease': "Disease associations not available",
                    'go_terms': "",
                    'domains': "",
                    'uniprot_id': ""
                }
        else:
            # Unexpected type
            logger.error(f"Unexpected proteins type: {type(proteins)}")
            return text + "Error: Could not process protein information."
        
        # Check if we need to limit protein data size (for Claude API token limits)
        limit_proteins = os.environ.get('LIMIT_PROTEIN_DATA', 'FALSE').upper() == 'TRUE'
        max_proteins = 50  # Default max proteins
        
        if limit_proteins:
            try:
                max_proteins = int(os.environ.get('MAX_PROTEINS', '50'))
                logger.info(f"Limiting protein data to {max_proteins} proteins due to token limits")
            except ValueError:
                logger.warning("Invalid MAX_PROTEINS value, using default of 50")
                max_proteins = 50
        
        # Now process the dictionary with potential limits
        protein_count = 0
        total_proteins = len(protein_dict)
        
        for protein_id, protein_info in protein_dict.items():
            # Check if we've reached the limit
                
            name       = protein_info.get('name', f"Protein {protein_id}")
            gene_name  = protein_info.get('gene_name', "Unknown")
            
            # Extract additional risk data if available
            risk_tier = protein_info.get('risk_tier', 'Unknown')
            abs_risk = protein_info.get('absolute_risk_range', 'Unknown')
            pop_risk = protein_info.get('population_risk', 'Unknown')
            
            # For large datasets, include only essential information to save tokens
            
    # Include all fields for smaller datasets
            function   = protein_info.get('function', "No function information available")
            disease    = protein_info.get('disease', "No disease associations found")
            go_terms   = protein_info.get('go_terms', "")
            domains    = protein_info.get('domains', "")
            uniprot_id = protein_info.get('uniprot_id', "")
            
            parts = [
                f"Protein ID: {protein_id}",
                f"Name: {name}",
                f"Gene: {gene_name}",
                f"Function: {function}",
                f"Disease: {disease}",
                f"Domains: {domains}",
            ]
            
            # Add classification metadata if available
            classification_summary = protein_info.get('classification_summary', '')
            if classification_summary and classification_summary != 'No classified variants':
                parts.append(f"Variant Classification: {classification_summary}")
            
            risk_count = protein_info.get('risk_variant_count', 0)
            protective_count = protein_info.get('protective_variant_count', 0)
            if risk_count > 0 or protective_count > 0:
                parts.append(f"Risk variants: {risk_count}, Protective variants: {protective_count}")
            
            # Join with newlines for better readability
            line = "\n".join(parts)
            text += line + "\n\n"
            protein_count += 1
            
        return text

    def validate_and_enhance_blocks(self, blocks: list[ReportBlock], protein_mutations: dict[str, Any], input_dictionary: dict[str, Any]) -> list[ReportBlock]:
        """
        Validate LLM outputs and cross-reference with input data to ensure mutation details are provided.
        
        Args:
            blocks: List of ReportBlock objects from LLM generation
            protein_mutations: Dictionary of protein mutations from input data
            input_dictionary: Original input data dictionary
            
        Returns:
            Enhanced blocks with validated and corrected mutation information
        """
        import json
        import re
        
        logger.info("Validating and enhancing blocks with mutation details...")
        
        # Create a lookup for quick protein validation
        protein_lookup = {}
        for protein_id, mutations in protein_mutations.items():
            # Find gene name or common symbols for this protein
            # Find gene name or common symbols for this protein
            gene_name = protein_id
            
            uniprot_acc = None
            if hasattr(self, '_refseq_to_uniprot'):
                if protein_id in self._refseq_to_uniprot:
                    uniprot_acc = self._refseq_to_uniprot[protein_id]
                elif '.' in protein_id:
                     base_id = protein_id.split('.')[0]
                     if base_id in self._refseq_to_uniprot:
                         uniprot_acc = self._refseq_to_uniprot[base_id]

            if uniprot_acc and hasattr(self, '_uniprot_to_info') and uniprot_acc in self._uniprot_to_info:
                info = self._uniprot_to_info[uniprot_acc]
                gene_name = str(info.get('gene_names', protein_id)).split(' ')[0]
            
            protein_lookup[protein_id] = {
                'mutations': mutations,
                'mutation_count': len(mutations),
                'mutation_descriptions': [m.get('mutation_description', '') for m in mutations],
                'gene_name': gene_name
            }
        
        enhanced_blocks: list[ReportBlock] = []
        
        for block in blocks:
            try:
                block_data: dict[str, Any]
                
                def extract_json_robustly(text: str) -> Any:
                    if not isinstance(text, str):
                        return text
                    text = text.strip()
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        pass
                    
                    # Try markdown extraction
                    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
                    if json_match:
                        try:
                            return json.loads(json_match.group(1))
                        except json.JSONDecodeError:
                            pass
                    
                    # Try bracket extraction
                    bracket_match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', text)
                    if bracket_match:
                        try:
                            return json.loads(bracket_match.group(1))
                        except json.JSONDecodeError:
                            pass
                    return text

                if isinstance(block.content, str):
                    parsed = extract_json_robustly(block.content)
                    if isinstance(parsed, dict):
                        block_data = parsed
                    else:
                        block_data = {"content": block.content}
                else:
                    block_data = block.content if isinstance(block.content, dict) else {"content": block.content}
                
                # Check for double wrapping or nested block type name
                block_type_str = block.block_type.value
                if block_type_str in block_data and isinstance(block_data[block_type_str], dict):
                    # Unwrap: {"lifestyle_recommendations": {...}} -> {...}
                    block_data = block_data[block_type_str]
                elif "content" in block_data and isinstance(block_data["content"], str):
                    # Check if "content" itself is a JSON string
                    inner_parsed = extract_json_robustly(block_data["content"])
                    if isinstance(inner_parsed, dict):
                        # Merge or replace? Let's merge but prioritize inner content
                        content_str = block_data.pop("content")
                        block_data.update(inner_parsed)
                        # Re-check for block type name nesting in the inner content
                        if block_type_str in block_data and isinstance(block_data[block_type_str], dict):
                            block_data = block_data[block_type_str]
                
                # Validate and enhance based on block type
                if block.block_type.value == 'mutation_profile':
                    block_data = self._validate_mutation_profile_block(block_data, protein_lookup, input_dictionary)
                elif block.block_type.value == 'executive_summary':
                    block_data = self._validate_executive_summary_block(block_data, protein_lookup, input_dictionary)
                elif block.block_type.value == 'clinical_implications':
                    block_data = self._validate_clinical_implications_block(block_data, protein_lookup, input_dictionary)
                elif block.block_type.value == 'risk_assessment':
                    block_data = self._validate_risk_assessment_block(block_data, protein_lookup, input_dictionary)
                elif block.block_type.value == 'lifestyle_recommendations':
                    block_data = self._map_lifestyle_recommendations(block_data)
                elif block.block_type.value == 'monitoring_plan':
                    block_data = self._map_monitoring_plan(block_data)
                elif block.block_type.value == 'literature_evidence':
                    block_data = self._validate_literature_evidence_block(block_data)
                elif block.block_type.value == 'conclusion':
                    block_data = self._validate_conclusion_block(block_data)
                
                # Ensure enhanced classification data is present in content if applicable
                if input_dictionary.get('has_enhanced_classification'):
                    from dataclasses import asdict
                    def serialize_variant(v: Any) -> dict[str, Any] | str:
                        if hasattr(v, '__dict__') or (hasattr(v, '__dataclass_fields__')):
                            # Use custom serialization to avoid circular refs if any
                            try:
                                d = asdict(v)
                                # Handle enums
                                for key, value in d.items():
                                    if hasattr(value, 'value'):
                                        d[key] = value.value
                                return d
                            except:
                                return str(v)
                        return str(v)

                    if 'risk_variants' not in block_data and 'risk_increasing_variants' not in block_data:
                        block_data['risk_increasing_variants'] = [serialize_variant(v) for v in input_dictionary.get('risk_variants', [])]
                    if 'protective_variants' not in block_data:
                        block_data['protective_variants'] = [serialize_variant(v) for v in input_dictionary.get('protective_variants', [])]
                    
                    block_data['has_enhanced_classification'] = True

                # Update block content - ALWAYS store as JSON string for final processing
                block.content = json.dumps(block_data, indent=2)
                enhanced_blocks.append(block)
                
            except Exception as e:
                logger.error(f"Error validating block {block.block_type.value}: {e}")
                enhanced_blocks.append(block)  # Keep original if validation fails
        
        logger.info(f"Enhanced {len(enhanced_blocks)} blocks with mutation validation")
        return enhanced_blocks

    def _validate_literature_evidence_block(self, block_data: dict[str, Any]) -> dict[str, Any]:
        """Ensure PMID robustness and clean up evidence data."""
        import re
        
        # Helper to extract PMIDs from text if not explicitly present
        def find_pmids(text):
            if not text or not isinstance(text, str): return []
            return re.findall(r'PMID[:\s]*(\d+)', text, re.IGNORECASE)

        # 1. Check sections for PMIDs and ensure they are preserved
        sections = ['risk_increasing_evidence', 'protective_evidence']
        for sec_key in sections:
            if sec_key in block_data:
                section = block_data[sec_key]
                if 'protein_specific_evidence' in section:
                    for entry in section['protein_specific_evidence']:
                        # Scan key findings for PMIDs to bolster evidence
                        if 'key_research_findings' in entry:
                            findings = entry['key_research_findings']
                            all_findings_text = str(findings)
                            found_pmids = find_pmids(all_findings_text)
                            if found_pmids:
                                logger.info(f"Found PMIDs in {entry.get('protein')} research findings: {found_pmids}")
        
        # 2. Check key_references
        if 'key_references' in block_data:
            for ref in block_data['key_references']:
                if not ref.get('pmid'):
                    found = find_pmids(ref.get('key_finding', ''))
                    if found:
                        ref['pmid'] = found[0]
        
        return block_data

    def _find_protein_id(self, text: str, protein_lookup: dict[str, dict[str, Any]]) -> str | None:
        """Helper to find a protein ID within a potentially verbose string."""
        if not text:
            return None
        
        # Direct match with ID
        if text in protein_lookup:
            return text
            
        # Match with gene name (case insensitive)
        for p_id, p_data in protein_lookup.items():
            gene_name = p_data.get('gene_name', '')
            if gene_name and text.strip().upper() == gene_name.upper():
                return p_id
        
        # Check if any ID is contained in the text (e.g., "GALT (NP_000149.1)" contains "NP_000149.1")
        for p_id in protein_lookup:
            if p_id in text:
                return p_id
                
        # Check if any gene name is contained in the text (e.g., "GALT (Galactose-1...)" contains "GALT")
        # Only match if it's a "whole word" match or similar to avoid false positives with short names
        for p_id, p_data in protein_lookup.items():
            gene_name = p_data.get('gene_name', '')
            if gene_name and len(gene_name) >= 3: # Avoid matching very short gene names as substrings
                if gene_name.upper() in text.upper():
                    return p_id

        # Check if text is contained in any ID (unlikely but for completeness)
        for p_id in protein_lookup:
            if text in p_id:
                return p_id
                
        # Check if text is contained in any gene name
        for p_id, p_data in protein_lookup.items():
            gene_name = p_data.get('gene_name', '')
            if gene_name and len(text) >= 3:
                if text.upper() in gene_name.upper():
                    return p_id
                
        return None

    def _validate_mutation_profile_block(self, block_data, protein_lookup, input_dictionary):
        """Validate and enhance mutation profile block with actual mutation data."""
        if 'mutation_profile' not in block_data:
            return block_data
        
        mutation_profile = block_data['mutation_profile']
        
        # 1. Enforce fragments in risk_increasing_variants
        if 'risk_increasing_variants' in mutation_profile:
            section = mutation_profile['risk_increasing_variants']
            if 'detailed_analysis' in section:
                for entry in section['detailed_analysis']:
                    protein_id = self._find_protein_id(entry.get('protein', ''), protein_lookup)
                    if protein_id:
                        descriptions = protein_lookup[protein_id]['mutation_descriptions']
                        gene_name = protein_lookup[protein_id].get('gene_name', 'Unknown')
                        entry['mutation_details'] = f"High-Quality Mutation Data for {protein_id} ({gene_name}): " + '; '.join(descriptions)
                        entry['data_validated'] = True
        
        # 2. Enforce fragments in protective_variants
        if 'protective_variants' in mutation_profile:
            section = mutation_profile['protective_variants']
            if 'detailed_analysis' in section:
                for entry in section['detailed_analysis']:
                    protein_id = self._find_protein_id(entry.get('protein', ''), protein_lookup)
                    if protein_id:
                        descriptions = protein_lookup[protein_id]['mutation_descriptions']
                        gene_name = protein_lookup[protein_id].get('gene_name', 'Unknown')
                        entry['variant_details'] = f"High-Quality Mutation Data for {protein_id} ({gene_name}): " + '; '.join(descriptions)
                        entry['data_validated'] = True

        # 3. Validate detailed_protein_analysis (legacy or alternate format)
        if 'detailed_protein_analysis' in mutation_profile:
            validated_proteins = []
            for protein_analysis in mutation_profile['detailed_protein_analysis']:
                protein_id = self._find_protein_id(protein_analysis.get('protein', ''), protein_lookup)
                if protein_id:
                    descriptions = protein_lookup[protein_id]['mutation_descriptions']
                    gene_name = protein_lookup[protein_id].get('gene_name', 'Unknown')
                    protein_analysis['mutation_details'] = f"High-Quality Mutation Data for {protein_id} ({gene_name}): " + '; '.join(descriptions)
                    
                    actual_mutations = protein_lookup[protein_id]['mutations']
                    if actual_mutations:
                        protein_analysis['genomic_variants'] = [m.get('variant', '') for m in actual_mutations]
                        protein_analysis['pathogenicity_scores'] = [m.get('score', 0) for m in actual_mutations]
                    
                    protein_analysis['data_validated'] = True
                else:
                    protein_analysis['data_validated'] = False
                validated_proteins.append(protein_analysis)
            mutation_profile['detailed_protein_analysis'] = validated_proteins
        
        # 4. Validate genetic_variants_affecting_proteins (flat list)
        if 'genetic_variants_affecting_proteins' in mutation_profile:
            validated_variants = []
            for variant in mutation_profile['genetic_variants_affecting_proteins']:
                protein_id = self._find_protein_id(variant.get('affected_protein', ''), protein_lookup)
                if protein_id:
                    actual_mutations = protein_lookup[protein_id]['mutations']
                    if actual_mutations:
                        # Find the matching mutation if possible, otherwise use first
                        v_id = variant.get('variant', '')
                        match = next((m for m in actual_mutations if m.get('variant') == v_id), actual_mutations[0])
                        variant['variant'] = match.get('variant', '')
                        
                        gene_name = protein_lookup[protein_id].get('gene_name', 'Unknown')
                        variant['functional_change'] = f"High-Quality Mutation Data for {protein_id} ({gene_name}): " + match.get('mutation_description', '')
                        variant['pathogenicity_score'] = match.get('score', 0)
                        variant['data_validated'] = True
                else:
                    variant['data_validated'] = False
                validated_variants.append(variant)
            mutation_profile['genetic_variants_affecting_proteins'] = validated_variants
        
        # Add comprehensive protein-gene mapping
        mutation_profile['protein_gene_mapping'] = self._create_protein_gene_mapping(protein_lookup, input_dictionary)
        
        return block_data

    def _validate_executive_summary_block(self, block_data, protein_lookup, input_dictionary):
        """Validate and enhance executive summary block with actual mutation data."""
        if 'executive_summary' not in block_data:
            return block_data
        
        summary = block_data['executive_summary']
        
        # 1. Enforce fragments in key_protein_mutations
        if 'key_protein_mutations' in summary:
            for item in summary['key_protein_mutations']:
                protein_id = self._find_protein_id(item.get('protein', ''), protein_lookup)
                if protein_id:
                    # Enforce consistent mutation description
                    item['specific_mutation'] = '; '.join(protein_lookup[protein_id]['mutation_descriptions'])
                    # Set associated diseases
                    diseases_str = protein_lookup[protein_id].get('diseases', '')
                    if diseases_str:
                        item['associated_diseases'] = [d.strip() for d in diseases_str.split(',') if d.strip()]
                    item['data_validated'] = True
        
        # 2. Enforce fragments in variant_summary
        if 'variant_summary' in summary and isinstance(summary['variant_summary'], dict) and 'key_variants' in summary['variant_summary']:
            for variant in summary['variant_summary']['key_variants']:
                protein_id = self._find_protein_id(variant.get('protein_name', ''), protein_lookup)
                if not protein_id:
                    # Search all proteins in lookup for this variant rsID
                    v_id = variant.get('variant', '')
                    for p_id, p_data in protein_lookup.items():
                        if any(m.get('variant') == v_id for m in p_data['mutations']):
                            protein_id = p_id
                            break
                
                if protein_id:
                    actual_mutations = protein_lookup[protein_id]['mutations']
                    v_id = variant.get('variant', '')
                    match = next((m for m in actual_mutations if m.get('variant') == v_id), actual_mutations[0])
                    variant['variant'] = match.get('variant', '')
                    variant['protein_effect'] = match.get('mutation_description', '')
                    variant['data_validated'] = True

        # 3. Map to template expected keys (summary_points)
        if 'summary_points' not in summary:
            # Try to populate from key_findings or action_items or primary_recommendations
            points = []
            if 'key_findings' in summary and isinstance(summary['key_findings'], list):
                points.extend(summary['key_findings'][:3])
            
            if 'primary_recommendations' in summary and isinstance(summary['primary_recommendations'], list):
                for rec in summary['primary_recommendations'][:2]:
                    if isinstance(rec, dict) and 'recommendation' in rec:
                        points.append(rec['recommendation'])
                    elif isinstance(rec, str):
                        points.append(rec)
            
            if points:
                summary['summary_points'] = points
            else:
                summary['summary_points'] = ["Genetic analysis completed", "Personalized recommendations provided"]

        return block_data

    def _validate_conclusion_block(self, block_data: dict[str, Any]) -> dict[str, Any]:
        """Validate and map conclusion block data."""
        # Unwrapping logic if it's nested under 'conclusion'
        data = block_data
        if 'conclusion' in block_data and isinstance(block_data['conclusion'], dict):
            data = block_data['conclusion']
        
        # Normalize keys for conclusion_block.html
        data = self._map_conclusion_block(data)
        
        # If it was nested, put it back (or just return the flat version if that's what's expected)
        if 'conclusion' in block_data:
            block_data['conclusion'] = data
        else:
            block_data = data
            
        return block_data

    def _map_conclusion_block(self, block_data: dict[str, Any]) -> dict[str, Any]:
        """Map Gemini's conclusion JSON keys to those expected by the HTML template."""
        # Template expects: summary, next_steps (action, priority, rationale)
        
        mapped_data = {}
        
        # 1. Summary (Clinical Synthesis)
        mapped_data['summary'] = block_data.get('conclusion_summary', 
                                              block_data.get('summary_of_significance', 
                                              block_data.get('summary', '')))
        
        # 2. Next Steps
        original_steps = block_data.get('next_steps', block_data.get('recommended_next_steps', []))
        mapped_steps = []
        
        for step in original_steps:
            if isinstance(step, dict):
                mapped_steps.append({
                    'action': step.get('action', 'Follow up with provider'),
                    'priority': step.get('priority', 'High'),
                    'rationale': step.get('rationale', step.get('timeline', 'Recommended next step'))
                })
            elif isinstance(step, str):
                mapped_steps.append({
                    'action': step,
                    'priority': 'High',
                    'rationale': 'Recommended next step'
                })
        
        mapped_data['next_steps'] = mapped_steps
        
        # Preserve original keys
        for k, v in block_data.items():
            if k not in mapped_data:
                mapped_data[k] = v
                
        return mapped_data

    def _create_protein_gene_mapping(self, protein_lookup, input_dictionary):
        """
        Create comprehensive protein-gene mapping with mutation details.
        
        Args:
            protein_lookup: Dictionary of protein mutations
            input_dictionary: Original input data
            
        Returns:
            Dictionary mapping proteins to genes with mutation details
        """
        mapping = {}
        
        for protein_id, protein_data in protein_lookup.items():
            mutations = protein_data.get('mutations', [])
            if mutations:
                # Use the already resolved gene name from protein_lookup
                gene_name = protein_data.get('gene_name', 'Unknown')
                
                # If gene_name is still the accession and we have mutated_proteins_text, 
                # keep trying to enrich it (legacy fallback, but safer now)
                if gene_name == protein_id or gene_name == 'Unknown':
                    mutated_proteins_text = input_dictionary.get('MUTATED_PROTEINS', '')
                    if protein_id in mutated_proteins_text:
                        # Extract gene name from the protein text
                        lines = mutated_proteins_text.split('\n')
                        for line in lines:
                            if protein_id in line and 'Gene:' in line:
                                try:
                                    gene_match = line.split('Gene:')[1].split('\n')[0].strip()
                                    if gene_match and gene_match != 'Unknown':
                                        gene_name = gene_match
                                        break
                                except (IndexError, AttributeError):
                                    continue
                
                mapping[protein_id] = {
                    'gene_name': gene_name,
                    'mutation_count': len(mutations),
                    'top_mutations': [m.get('mutation_description', '') for m in mutations[:3]],
                    'pathogenicity_scores': [m.get('score', 0) for m in mutations[:3]],
                    'genomic_variants': [m.get('variant', '') for m in mutations[:3]]
                }
        
        return mapping

    def _validate_clinical_implications_block(self, block_data, protein_lookup, input_dictionary):
        """Validate and enhance clinical implications block with actual mutation data."""
        if 'clinical_implications' not in block_data:
            return block_data
        
        clinical_implications = block_data['clinical_implications']
        
        # Validate protein_specific_treatments
        if 'protein_specific_treatments' in clinical_implications:
            validated_treatments = []
            for treatment in clinical_implications['protein_specific_treatments']:
                protein_id = self._find_protein_id(treatment.get('protein', ''), protein_lookup)
                
                if protein_id:
                    actual_mutations = protein_lookup[protein_id]['mutations']
                    if actual_mutations:
                        # Enhance with specific mutation context
                        mutation_context = f"Specific mutations: {'; '.join(protein_lookup[protein_id]['mutation_descriptions'][:2])}"
                        current_management = treatment.get('clinical_management', '')
                        treatment['clinical_management'] = f"{current_management}\n\n{mutation_context}"
                        treatment['data_validated'] = True
                
                validated_treatments.append(treatment)
            
            clinical_implications['protein_specific_treatments'] = validated_treatments
        
        return block_data

    def _map_lifestyle_recommendations(self, block_data: dict[str, Any]) -> dict[str, Any]:
        """Map Gemini's lifestyle recommendations JSON keys to those expected by the HTML template."""
        # The template expects: summary, dietary_focus (type, rationale), 
        # activity_recommendations (activity, benefit), environmental_and_habit_changes (list of strings)
        
        mapped_data = {}
        
        # 1. Summary
        mapped_data['summary'] = block_data.get('overview', '')
        
        # 2. Dietary Focus
        dietary_recommendations = block_data.get('dietary_recommendations', [])
        mapped_dietary = []
        for rec in dietary_recommendations:
            mapped_dietary.append({
                'type': rec.get('recommendation', 'Dietary Recommendation'),
                'rationale': rec.get('rationale', '')
            })
        mapped_data['dietary_focus'] = mapped_dietary
        
        # 3. Activity Recommendations
        exercise_recommendations = block_data.get('exercise_recommendations', [])
        mapped_activity = []
        for rec in exercise_recommendations:
            mapped_activity.append({
                'activity': rec.get('type', 'Exercise'),
                'benefit': rec.get('genetic_benefits', rec.get('rationale', ''))
            })
        mapped_data['activity_recommendations'] = mapped_activity
        
        # 4. Habits & Environment
        environmental = block_data.get('environmental_considerations', [])
        mapped_habits = []
        for item in environmental:
            factor = item.get('factor', 'Habit')
            rec = item.get('recommendation', '')
            if rec:
                mapped_habits.append(f"{factor}: {rec}")
            else:
                mapped_habits.append(factor)
        mapped_data['environmental_and_habit_changes'] = mapped_habits
        
        # Preserve original keys just in case
        for k, v in block_data.items():
            if k not in mapped_data:
                mapped_data[k] = v
                
        return mapped_data

    def _map_monitoring_plan(self, block_data: dict[str, Any]) -> dict[str, Any]:
        """Map Gemini's monitoring plan JSON keys to those expected by the HTML template."""
        # The template expects: follow_up_schedule (timepoint, focus, actions[]),
        # warning_signs (sign, meaning, action), tracking_tools (list of strings)
        
        mapped_data = {}
        
        # 1. Follow-up Schedule
        surveillance = block_data.get('disease_surveillance_schedule', [])
        follow_up = []
        seen_diseases = set()
        
        for item in surveillance:
            disease = item.get('disease', 'General')
            if disease in seen_diseases:
                continue
                
            # Handle new consolidated format
            if 'timepoint' in item and ('recommendations' in item or 'actions' in item):
                timepoint = item.get('timepoint', 'Routine')
                actions = item.get('recommendations', item.get('actions', []))
                follow_up.append({
                    'timepoint': timepoint.upper(),
                    'focus': disease,
                    'actions': [actions] if isinstance(actions, str) else actions
                })
                seen_diseases.add(disease)
            # Fallback for old multi-timepoint schedule format
            elif 'schedule' in item:
                schedule = item.get('schedule', {})
                all_actions = []
                primary_timepoint = "Routine"
                
                # Consolidate all timepoints into one entry
                for tp, desc in schedule.items():
                    if desc:
                        if tp == '3_to_6_months':
                            primary_timepoint = '3 TO 6 MONTHS'
                        elif tp == 'annually' and primary_timepoint == 'Routine':
                            primary_timepoint = 'ANNUALLY'
                        
                        action_text = f"[{tp.replace('_', ' ').title()}] {desc}"
                        all_actions.append(action_text)
                
                if all_actions:
                    follow_up.append({
                        'timepoint': primary_timepoint,
                        'focus': disease,
                        'actions': all_actions
                    })
                    seen_diseases.add(disease)
        
        mapped_data['follow_up_schedule'] = follow_up
        
        # 2. Warning Signs
        original_signs = block_data.get('warning_signs', [])
        mapped_signs = []
        for sign in original_signs:
            symptoms = sign.get('symptoms', [])
            mapped_signs.append({
                'sign': ", ".join(symptoms) if isinstance(symptoms, list) else symptoms,
                'meaning': sign.get('disease', 'Potential onset'),
                'action': sign.get('action', 'Contact your healthcare provider')
            })
        mapped_data['warning_signs'] = mapped_signs
        
        # 3. Tracking Tools
        tools = []
        # Extract from protein_specific_monitoring -> biomarkers
        protein_monitoring = block_data.get('protein_specific_monitoring', [])
        for pm in protein_monitoring:
            biomarkers = pm.get('biomarkers', [])
            for bm in biomarkers:
                name = bm.get('biomarker')
                if name and name not in tools:
                    tools.append(name)
        
        # Also add anything explicitly called tracking tools if it exists
        if 'tracking_tools' in block_data:
            extra_tools = block_data['tracking_tools']
            if isinstance(extra_tools, list):
                for t in extra_tools:
                    if t not in tools:
                        tools.append(t)
        
        mapped_data['tracking_tools'] = tools
        
        # Preserve original keys
        for k, v in block_data.items():
            if k not in mapped_data:
                mapped_data[k] = v
                
        return mapped_data

    def _validate_risk_assessment_block(self, block_data, protein_lookup, input_dictionary):
        """Validate and enhance risk assessment block with actual mutation data."""
        if 'risk_assessment' not in block_data:
            return block_data
        
        risk_assessment = block_data['risk_assessment']
        
        # Ensure risk assessment has substantive content
        if not risk_assessment.get('risk_summary') or len(risk_assessment.get('risk_summary', '')) < 50:
            risk_assessment['risk_summary'] = self._generate_fallback_risk_summary(protein_lookup, input_dictionary)
        
        # Validate protein_specific_risk_factors
        if 'protein_specific_risk_factors' in risk_assessment:
            validated_risks = []
            for risk_factor in risk_assessment['protein_specific_risk_factors']:
                protein_id = self._find_protein_id(risk_factor.get('protein', ''), protein_lookup)
                
                if protein_id:
                    actual_mutations = protein_lookup[protein_id]['mutations']
                    if actual_mutations:
                        # Add specific mutation context to pathway effects
                        mutation_details = f"Specific mutations identified: {'; '.join(protein_lookup[protein_id]['mutation_descriptions'][:2])}"
                        current_pathway = risk_factor.get('pathway_effects', '')
                        risk_factor['pathway_effects'] = f"{current_pathway}\n\nMutation details: {mutation_details}"
                        risk_factor['data_validated'] = True
                        risk_factor['mutation_count'] = len(actual_mutations)
                        
                        # Add risk quantification based on mutation scores
                        avg_score = sum(m.get('score', 0) for m in actual_mutations) / len(actual_mutations)
                        if avg_score > 0.8:
                            risk_factor['risk_level'] = 'High'
                        elif avg_score > 0.6:
                            risk_factor['risk_level'] = 'Moderate'
                        else:
                            risk_factor['risk_level'] = 'Low'
                
                validated_risks.append(risk_factor)
            
            risk_assessment['protein_specific_risk_factors'] = validated_risks
        
        # Ensure we have risk factors if protein data exists
        if not risk_assessment.get('protein_specific_risk_factors') and protein_lookup:
            risk_assessment['protein_specific_risk_factors'] = self._generate_fallback_risk_factors(protein_lookup)
        
        return block_data

    def _generate_fallback_risk_summary(self, protein_lookup, input_dictionary):
        """Generate a fallback risk summary when the LLM doesn't provide adequate content."""
        if not protein_lookup:
            return "Risk assessment based on available genetic data indicates the need for clinical evaluation."
        
        high_risk_proteins = []
        moderate_risk_proteins = []
        
        for protein_id, protein_data in protein_lookup.items():
            mutations = protein_data.get('mutations', [])
            if mutations:
                avg_score = sum(m.get('score', 0) for m in mutations) / len(mutations)
                if avg_score > 0.75:
                    high_risk_proteins.append(protein_id)
                elif avg_score > 0.6:
                    moderate_risk_proteins.append(protein_id)
        
        summary_parts = []
        if high_risk_proteins:
            summary_parts.append(f"High-risk protein mutations identified in {len(high_risk_proteins)} proteins, indicating elevated disease risk.")
        if moderate_risk_proteins:
            summary_parts.append(f"Moderate-risk mutations found in {len(moderate_risk_proteins)} proteins, suggesting increased surveillance needs.")
        
        if not summary_parts:
            summary_parts.append("Genetic analysis reveals protein mutations that warrant clinical consideration and monitoring.")
        
        return " ".join(summary_parts)

    def _generate_fallback_risk_factors(self, protein_lookup):
        """Generate fallback risk factors when the LLM doesn't provide adequate content."""
        risk_factors = []
        
        for protein_id, protein_data in protein_lookup.items():
            mutations = protein_data.get('mutations', [])
            if mutations:
                avg_score = sum(m.get('score', 0) for m in mutations) / len(mutations)
                
                risk_factor = {
                    'protein': protein_id,
                    'associated_diseases': ['Condition related to protein function'],
                    'risk_impact': 'High' if avg_score > 0.75 else 'Moderate' if avg_score > 0.6 else 'Low',
                    'modifiable': 'Partially',
                    'pathway_effects': f"Protein mutations may affect normal cellular function and disease pathways. Specific mutations: {'; '.join(protein_data.get('mutation_descriptions', [])[:2])}",
                    'data_validated': True,
                    'mutation_count': len(mutations)
                }
                risk_factors.append(risk_factor)
        
        # Sort by average score descending to ensure high-impact genes like PRSS1 are included
        risk_factors.sort(key=lambda x: sum(m.get('score', 0) for m in protein_lookup[self._find_protein_id(x['protein'], protein_lookup)]['mutations']) / len(protein_lookup[self._find_protein_id(x['protein'], protein_lookup)]['mutations']) if self._find_protein_id(x['protein'], protein_lookup) else 0, reverse=True)
        
        return risk_factors[:15]  # Increased limit to top 15 proteins

    def make_protein_mutations_text(self, protein_mutations):
        """
        Convert protein mutations information to a formatted text string for LLM input.
        
        Args:
            protein_mutations: Dictionary mapping protein IDs to lists of mutation information
            
        Returns:
            Formatted text string with detailed mutation information
        """
        if not protein_mutations:
            return "No protein mutations identified in the analysis."
        
        text = "Detailed Protein Mutations Analysis:\n\n"
        
        for protein_id, mutations in protein_mutations.items():
            if not mutations:
                continue
                
            text += f"Protein: {protein_id}\n"
            text += f"Number of mutations: {len(mutations)}\n"
            
            for i, mutation in enumerate(mutations, 1):
                text += f"  Mutation {i}:\n"
                text += f"    - Genomic variant: {mutation.get('variant', 'Unknown')}\n"
                text += f"    - Allele: {mutation.get('allele', 'Unknown')}\n"
                text += f"    - Amino acid position: {mutation.get('position', 'Unknown')}\n"
                text += f"    - Reference amino acid: {mutation.get('ref_amino_acid', 'Unknown')}\n"
                text += f"    - Alternate amino acid: {mutation.get('alt_amino_acid', 'Unknown')}\n"
                text += f"    - Mutation description: {mutation.get('mutation_description', 'Unknown')}\n"
                text += f"    - Pathogenicity score: {mutation.get('score', 'Unknown')}\n"
                text += f"    - Clinical Significance: {mutation.get('clinical_significance', 'Unknown')}\n"
                text += f"    - Evidence Strength: {mutation.get('evidence_strength', 'Unknown')}\n"
                text += f"    - Risk (Absolute): {mutation.get('absolute_risk_range', 'Unknown')}\n"
                text += f"    - Risk (Population): {mutation.get('population_risk', 'Unknown')}\n"
                text += f"    - Risk Tier: {mutation.get('risk_tier', 'Unknown')}\n"
            
            text += "\n"
        
        return text

    def make_combined_protein_disease_mutations_text(self, protein_diseases, protein_mutations):
        """
        Create a comprehensive text combining protein-disease associations with their specific mutations.
        
        Args:
            protein_diseases: List of (protein, disease) tuples
            protein_mutations: Dictionary mapping protein IDs to mutation lists
            
        Returns:
            Formatted text combining disease associations with mutation details
        """
        if not protein_diseases and not protein_mutations:
            return "No protein-disease associations or mutations identified."
        
        text = "Protein-Disease Associations with Mutation Details:\n\n"
        
        # Create a mapping of proteins to their diseases
        protein_to_diseases = {}
        for protein, diseases in protein_diseases:
            if protein not in protein_to_diseases:
                protein_to_diseases[protein] = []
            if diseases.strip():  # Only add non-empty disease strings
                protein_to_diseases[protein].append(diseases.strip())
        
        # Process each protein that has either diseases or mutations
        all_proteins = set(protein_to_diseases.keys()) | set(protein_mutations.keys())
        
        for protein in all_proteins:
            text += f"Protein: {protein}\n"
            
            # Add disease associations
            if protein in protein_to_diseases and protein_to_diseases[protein]:
                text += f"Disease associations: {'; '.join(protein_to_diseases[protein])}\n"
            else:
                text += "Disease associations: None identified\n"
            
            # Add mutation details
            if protein in protein_mutations and protein_mutations[protein]:
                mutations = protein_mutations[protein]
                text += f"Mutations identified: {len(mutations)}\n"
                
                for i, mutation in enumerate(mutations, 1):
                    text += f"  Mutation {i}: {mutation.get('mutation_description', 'Unknown mutation')} "
                    text += f"(Score: {mutation.get('score', 'Unknown')}, "
                    text += f"Significance: {mutation.get('clinical_significance', 'Unknown')}, "
                    text += f"Evidence: {mutation.get('evidence_strength', 'Unknown')}, "
                    text += f"Variant: {mutation.get('variant', 'Unknown')})\n"
            else:
                text += "Mutations: None identified\n"
            
            text += "\n"
        
        return text
                     
    def _is_gender_incompatible(self, disease_name: str, gender: str) -> bool:
        """
        Check if a disease is incompatible with the specified gender.
        """
        if not gender or gender.lower() == "unknown":
            return False
            
        gender = gender.lower()
        disease = disease_name.lower()
        
        # Comprehensive sex-specific condition mapping
        female_only = [
            'ovarian', 'uterus', 'uterine', 'endometrial', 'cervix', 'cervical', 
            'preeclampsia', 'placenta', 'gestational', 'pregnancy', 'pcos', 
            'polycystic ovary', 'fallopian', 'eclampsia', 'menstrual', 'vulva'
        ]
        
        male_only = [
            'testicular', 'testis', 'prostate', 'prostatic', 'penile', 'penis', 
            'epididymis', 'epididymitis', 'bph', 'seminal vesicle'
        ]
        
        if gender == "male":
            if any(term in disease for term in female_only):
                return True
        elif gender == "female":
            if any(term in disease for term in male_only):
                return True
                
        return False

    def generate_report(self, annotated_path: str, vcf_path: str, report_info: dict[str, Any], name: str, output_format: str = 'text', family_history: str = '') -> list[ReportBlock]:
        '''Generate reports based on the type of report. gene_only and gene_prompt
            Currently only supporting GH_enhanced
            input:
                annotated_path - a VCF that contains only exon positions with disease scores from Entprise or EntpriseX
                vcf_path - a path to the plain VCF to be used for examining GWAS associations
                family_history - text about a person family history. Adds additional context for reporting
                report_info dictionary with
                    member_name
                    member_id
                    provider_name
                output_format - 'text', 'html', or 'both'
                    '''
        # 0. Top-level Cache Bypass (forced regeneration)
        report_sig_data = {
            'prompt': self.prompt,
            'annotated_hash': get_file_hash(annotated_path),
            'vcf_hash': get_file_hash(vcf_path),
            'report_info': report_info,
            'family_history': family_history,
            'blocks': [b.value for b in self.blocks],
            'report_type': self.report_type
        }
        sig_hash = hashlib.sha256(json.dumps(report_sig_data, sort_keys=True).encode()).hexdigest()
        report_signature = f"REPORT:FULL:{sig_hash}"
        pass
        
        # Mapping load ensured before analysis

        # Ensure mapping is loaded before disease generation
        print("LOADING METADATA MAPPINGS")
        self._ensure_metadata_loaded() # is this needed?    
        
        # run analysis on mutations
        # Use the provided proteins and protein_diseases instead of generating from VCF
        # proteins, protein_diseases = generate_diseases(vcf_path)  # This would be used if processing VCF
        print("GENERATING DISEASES")
        proteins, protein_diseases, protein_mutations, classified_variants = self.generate_diseases(KNOWGENE_PATH,annotated_path)
        
        # Filter classified_variants to only include clinically actionable ones (Risk or Protective)
        from variant_classifier import EffectDirection
        classified_variants = [v for v in classified_variants if v.effect_direction in [EffectDirection.RISK_INCREASING, EffectDirection.PROTECTIVE]]
        logger.info(f"Filtered to {len(classified_variants)} clinically significant variants.")
        
        # Gender-specific filtering
        gender = report_info.get('gender', 'Unknown')
        if gender and gender.lower() != 'unknown':
            logger.info(f"Applying gender-specific filtering for: {gender}")
            
            # Filter protein_diseases
            filtered_protein_diseases = []
            for item in protein_diseases:
                protein = item[0]
                disease_string = item[1]
                
                # Split diseases and filter individual ones
                diseases = [d.strip() for d in disease_string.split(',') if d.strip()]
                compatible_diseases = [d for d in diseases if not self._is_gender_incompatible(d, gender)]
                
                if compatible_diseases:
                    new_disease_string = ', '.join(compatible_diseases)
                    # Check if any were filtered out for logging
                    if len(compatible_diseases) < len(diseases):
                        filtered_out = [d for d in diseases if d not in compatible_diseases]
                        logger.info(f"Filtering out sex-incompatible diseases for {protein}: {', '.join(filtered_out)}")
                    
                    # Update the item with the filtered string
                    # item might be a tuple or have 3 elements if enhanced features are on
                    new_item = list(item)
                    new_item[1] = new_disease_string
                    filtered_protein_diseases.append(tuple(new_item))
                else:
                    logger.info(f"Filtering out all diseases for {protein} as they are sex-incompatible: {disease_string}")
            protein_diseases = filtered_protein_diseases
            
            # Filter protein_mutations
            filtered_protein_mutations = {}
            for protein, mutations in protein_mutations.items():
                filtered_muts = []
                for mut in mutations:
                    mutation_diseases = mut.get('diseases', '')
                    # If any associated disease is compatible, keep the mutation
                    # Or if no diseases are listed, keep it
                    if not mutation_diseases:
                        filtered_muts.append(mut)
                        continue
                        
                    # Split diseases and check each
                    diseases = [d.strip() for d in mutation_diseases.split(',') if d.strip()]
                    compatible_diseases = [d for d in diseases if not self._is_gender_incompatible(d, gender)]
                    
                    if compatible_diseases:
                        # Update mutation with only compatible diseases
                        mut['diseases'] = ', '.join(compatible_diseases)
                        filtered_muts.append(mut)
                    else:
                        logger.info(f"Filtering out mutation for {protein} because all associated diseases are sex-incompatible: {mutation_diseases}")
                
                if filtered_muts:
                    filtered_protein_mutations[protein] = filtered_muts
            protein_mutations = filtered_protein_mutations
            
            # Filter classified_variants
            # ClassifiedVariant objects have a 'literature_evidence' attribute which contains 'disease_associations'
            filtered_classified_variants = []
            for variant in classified_variants:
                # We need to check if the variant is primarily associated with sex-incompatible diseases
                # gene name might give a clue but the diseases string is better
                if hasattr(variant, 'literature_evidence') and 'disease_associations' in variant.literature_evidence:
                    assoc = variant.literature_evidence['disease_associations']
                    if assoc:
                        diseases = [d.strip() for d in assoc.split(',') if d.strip()]
                        compatible = [d for d in diseases if not self._is_gender_incompatible(d, gender)]
                        if compatible:
                            variant.literature_evidence['disease_associations'] = ', '.join(compatible)
                            filtered_classified_variants.append(variant)
                        else:
                            logger.info(f"Filtering out variant {variant.rsid} for {gender}")
                    else:
                        filtered_classified_variants.append(variant)
                else:
                    filtered_classified_variants.append(variant)
            classified_variants = filtered_classified_variants
            
            # Update proteins set based on filtered evidence
            proteins = set(protein_mutations.keys())

        # 2. Focus-specific filtering (Relevance to Prompt)
        if self.prompt:
            logger.info(f"Filtering results based on report focus: {self.prompt}")
            
            # Collect all unique diseases from various sources
            all_diseases_to_check = set()
            
            # From protein_diseases
            for item in protein_diseases:
                disease_string = item[1]
                diseases = [d.strip() for d in disease_string.split(',') if d.strip()]
                all_diseases_to_check.update(diseases)
                
            # From protein_mutations
            for mutations in protein_mutations.values():
                for mut in mutations:
                    mutation_diseases = mut.get('diseases', '')
                    if mutation_diseases:
                        diseases = [d.strip() for d in mutation_diseases.split(',') if d.strip()]
                        all_diseases_to_check.update(diseases)
            
            # From classified_variants
            for variant in classified_variants:
                if hasattr(variant, 'literature_evidence') and 'disease_associations' in variant.literature_evidence:
                    assoc = variant.literature_evidence['disease_associations']
                    if assoc:
                        diseases = [d.strip() for d in assoc.split(',') if d.strip()]
                        all_diseases_to_check.update(diseases)
            
            if all_diseases_to_check:
                relevant_diseases = self._get_relevant_diseases(list(all_diseases_to_check))
                logger.info(f"Identified {len(relevant_diseases)} focus-relevant diseases out of {len(all_diseases_to_check)}")
                
                # Filter protein_diseases
                filtered_protein_diseases = []
                for item in protein_diseases:
                    protein = item[0]
                    disease_string = item[1]
                    diseases = [d.strip() for d in disease_string.split(',') if d.strip()]
                    compatible_diseases = [d for d in diseases if d in relevant_diseases]
                    
                    if compatible_diseases:
                        new_disease_string = ', '.join(compatible_diseases)
                        new_item = list(item)
                        new_item[1] = new_disease_string
                        filtered_protein_diseases.append(tuple(new_item))
                protein_diseases = filtered_protein_diseases
                
                # Filter protein_mutations
                filtered_protein_mutations = {}
                for protein, mutations in protein_mutations.items():
                    filtered_muts = []
                    for mut in mutations:
                        mutation_diseases = mut.get('diseases', '')
                        if not mutation_diseases:
                            # If no diseases are associated, we might want to keep it or filter it
                            # For now, let's keep it but ideally we check if the mutation itself is relevant
                            # However, checking every mutation individually is expensive.
                            # Usually mutations without disease tags are generic or new.
                            # Let's keep them to avoid missing new findings.
                            filtered_muts.append(mut)
                            continue
                            
                        diseases = [d.strip() for d in mutation_diseases.split(',') if d.strip()]
                        compatible_diseases = [d for d in diseases if d in relevant_diseases]
                        
                        if compatible_diseases:
                            mut['diseases'] = ', '.join(compatible_diseases)
                            filtered_muts.append(mut)
                    
                    if filtered_muts:
                        filtered_protein_mutations[protein] = filtered_muts
                protein_mutations = filtered_protein_mutations
                
                # Filter classified_variants
                filtered_classified_variants = []
                for variant in classified_variants:
                    if hasattr(variant, 'literature_evidence') and 'disease_associations' in variant.literature_evidence:
                        assoc = variant.literature_evidence['disease_associations']
                        if assoc:
                            diseases = [d.strip() for d in assoc.split(',') if d.strip()]
                            compatible = [d for d in diseases if d in relevant_diseases]
                            if compatible:
                                variant.literature_evidence['disease_associations'] = ', '.join(compatible)
                                filtered_classified_variants.append(variant)
                        else:
                            filtered_classified_variants.append(variant)
                    else:
                        filtered_classified_variants.append(variant)
                classified_variants = filtered_classified_variants
                
                # Final cleanup of proteins set
                proteins = set(protein_mutations.keys())

        print("ENRICHING POSITIONS")
        enriched_positions = enrich_positions(vcf_path,self.prompt)
                
        # Format data for display - handle both 2-tuple and 3-tuple formats
        formatted_protein_diseases_list = []
        proteins_list = []
        
        for item in protein_diseases:
            if len(item) == 2:
                # Basic format: (protein, disease)
                protein, disease = item
                if disease:
                    formatted_protein_diseases_list.append((protein, disease))
                    proteins_list.append(protein)
            elif len(item) == 3:
                # Enhanced format: (protein, disease, enhanced_association)
                protein, disease, _ = item
                if disease:
                    formatted_protein_diseases_list.append((protein, disease))
                    proteins_list.append(protein)
        
        protein_diseases = formatted_protein_diseases_list
        formatted_protein_diseases = "\n".join([f"{protein}: {disease}" for protein, disease in protein_diseases]) if protein_diseases else "No protein-disease associations identified"
        
        # Use the full set of proteins from generate_diseases
        if not proteins and proteins_list:
            proteins = proteins_list
        elif not proteins and not proteins_list:
            # Fallback for visibility
             logger.warning("No proteins identified in generate_diseases")
             
        # Ensure we have a list for methods that expect it
        proteins_to_process = list(proteins) if isinstance(proteins, (set, list)) else proteins_list
        
        print("PROVIDING PROTEIN CONTEXT")
        # Limit the number of proteins enriched to avoid hitting token quotas
        proteins_to_enrich = proteins_to_process # we will increase to full scope later
        proteins_enriched = self.add_context_proteins(proteins_to_enrich)
        
        # Limit data for LLM processing to avoid hitting token quotas
        # We prioritize risk-increasing variants and limit the total count
        print("MAKING PROTEINS TEXT")
        proteins_text = self.make_proteins_text(proteins_enriched) 
        
        # Create a limited version of protein_mutations for text generation
        limited_muts = {}
        # Use the already limited proteins_to_enrich list
        # New: Collect PubMed evidence for genes with high-scoring variants (>= 0.6)
        pubmed_evidence = {}
        processed_genes = set()
        
        # Determine genes with high-scoring mutations
        high_score_proteins = []
        for p, muts in protein_mutations.items():
            if any(float(m.get('score', 0)) >= 0.6 for m in muts):
                high_score_proteins.append(p)
        
        print(f"ENRICHING {len(high_score_proteins)} PROTEINS WITH PUBMED EVIDENCE")
        for p in high_score_proteins:
            # Get gene name
            uniprot_acc = self._refseq_to_uniprot.get(p)
            if not uniprot_acc and '.' in p:
                uniprot_acc = self._refseq_to_uniprot.get(p.split('.')[0])
                
            info = self._uniprot_to_info.get(uniprot_acc) if uniprot_acc else None
            gene_name = info.get('gene_names', self._extract_gene_name_from_protein(p)) if info else self._extract_gene_name_from_protein(p)
            
            if gene_name and gene_name not in processed_genes and gene_name != "Unknown":
                processed_genes.add(gene_name)
                # Search PubMed for gene + focus
                query = f"{gene_name} {self.prompt}"
                logger.info(f"Searching PubMed for: {query}")
                pubmed_searcher: Any = self.pubmed_searcher
                evidence_text = pubmed_searcher.get_evidence(query, retmax=5)
                
                if "No relevant research found" not in evidence_text:
                    # Summarize evidence using LLM
                    summary_prompt = f"""
Summarize the following PubMed research evidence regarding the gene {gene_name} and its association with {self.prompt}.
Provide a concise clinical summary focused on pathogenicity, disease association, and clinical relevance.
Keep track of the PMIDs used.

CRITICAL INSTRUCTION FOR PMIDs:
You must ONLY cite PMIDs that are explicitly present in the TEXT below. Do NOT invent, guess, or hallucinate PMIDs. If no specific PMID is provided in the text for a claim, do not include one.

RESEARCH EVIDENCE:
{evidence_text}

OUTPUT FORMAT:
- Summary: [Clinical summary]
- Studies: [List of PMIDs from the text]
"""
                    summary = self.block_generator._rate_limited_api_call(summary_prompt, "You are a clinical researcher summarizing medical literature.", max_tokens=1024)
                    pubmed_evidence[gene_name] = summary

        for p in proteins_to_enrich:
            if p in protein_mutations:
                # Prioritize risk variants if they exist for this protein
                muts = protein_mutations[p]
                limited_muts[p] = muts[:10] # Limit to 10 mutations per protein
        
        print("Making muts text")
        protein_mutations_text = self.make_protein_mutations_text(limited_muts)
        print("combining proteins and muts")
        combined_protein_disease_mutations_text = self.make_combined_protein_disease_mutations_text(protein_diseases, limited_muts)
        
        prot2mut = {}
        for p in protein_mutations.keys():
            muts = []
            entry = protein_mutations[p]
            for i in entry:
                muts.append(i['mutation_description'])
            prot2mut[p] = muts

            
        print('making input dict')
        
        risk_variants: list[Any] = [v for v in classified_variants if v.effect_direction == EffectDirection.RISK_INCREASING]
        protective_variants: list[Any] = [v for v in classified_variants if v.effect_direction == EffectDirection.PROTECTIVE]
        
        # Determine blocks that need batching vs one-shot
        batched_block_types = [BlockType.MUTATION_PROFILE, BlockType.LITERATURE_EVIDENCE]
        oneshot_block_types = [bt for bt in self.blocks if bt not in batched_block_types]
        
        # Batching variants for MUTATION_PROFILE
        all_variants = risk_variants + protective_variants
        variant_chunks = self._chunk_list(all_variants, 50) if all_variants else [[]]
        
        # Prepare specialized chunks for protein mutations as well
        protein_chunks = self._chunk_list(proteins_to_process, 30) if proteins_to_process else [[]]
        num_chunks = max(len(variant_chunks), len(protein_chunks))
        
        batched_blocks_map = {bt: [] for bt in batched_block_types}
        
        print(f"Generating blocks in {num_chunks} batches...")
        for i in range(num_chunks):
            v_chunk = variant_chunks[i] if i < len(variant_chunks) else variant_chunks[-1]
            p_chunk = protein_chunks[i] if i < len(protein_chunks) else protein_chunks[-1]
            
            # Enrich and format for this chunk
            p_enriched = self.add_context_proteins(p_chunk)
            p_text = self.make_proteins_text(p_enriched)
            
            p_muts_chunk = {}
            for p in p_chunk:
                if p in protein_mutations:
                    p_muts_chunk[p] = protein_mutations[p][:10]
            
            p_muts_text = self.make_protein_mutations_text(p_muts_chunk)
            comb_text = self.make_combined_protein_disease_mutations_text(protein_diseases, p_muts_chunk)
            
            chunk_input_dict = {
                'MUTATED_PROTEINS': p_text,
                'PROTEIN_DISEASES': formatted_protein_diseases,
                'PROTEIN_MUTATIONS': p_muts_text,
                'PROTEIN_DISEASE_MUTATIONS': comb_text,
                'VARIANTS': [str(v) for v in v_chunk],
                'FAMILY_HISTORY': family_history,
                'PROMPT': self.prompt,
                'DEMOGRAPHICS': report_info.get('patient_name', 'Unknown Patient'),
                'CLINICAL_CONTEXT': f"Patient: {report_info.get('patient_name', 'Unknown')}, ID: {report_info.get('member_id', 'Unknown')}",
                'GWAS_ASSOCIATIONS': enriched_positions,
                'risk_variants': [v for v in v_chunk if v.effect_direction == EffectDirection.RISK_INCREASING],
                'protective_variants': [v for v in v_chunk if v.effect_direction == EffectDirection.PROTECTIVE],
                'has_enhanced_classification': True,
                'variants_by_condition': self.get_variants_by_condition(),
                'section_configurations': self.determine_section_configurations(),
                'report_type': self.report_type,
                'PUBMED_EVIDENCE': pubmed_evidence
            }
            
            # Generate only the blocks that need batching
            chunk_blocks = self.block_generator.generate_report_blocks_parallel_with_progress(
                block_types=batched_block_types, 
                data=chunk_input_dict,
                progress_callback=lambda current, total, msg: print(f"Batch {i+1}: {msg} ({current}/{total})")
            )
            
            for b in chunk_blocks:
                if b.block_type in batched_blocks_map:
                    batched_blocks_map[b.block_type].append(b)
        
        # Merge the batched blocks
        final_blocks = []
        for bt, block_list in batched_blocks_map.items():
            if block_list:
                final_blocks.append(self._merge_json_blocks(bt, block_list))
        
        # Generate one-shot blocks (using first 50 variants for context)
        oneshot_input_dict = {
            'MUTATED_PROTEINS': proteins_text,
            'PROTEIN_DISEASES': formatted_protein_diseases,
            'PROTEIN_MUTATIONS': protein_mutations_text,
            'PROTEIN_DISEASE_MUTATIONS': combined_protein_disease_mutations_text,
            'VARIANTS': [str(v) for v in (risk_variants[:50] + protective_variants[:50])],
            'FAMILY_HISTORY': family_history,
            'PROMPT': self.prompt,
            'DEMOGRAPHICS': report_info.get('patient_name', 'Unknown Patient'),
            'CLINICAL_CONTEXT': f"Patient: {report_info.get('patient_name', 'Unknown')}, ID: {report_info.get('member_id', 'Unknown')}",
            'GWAS_ASSOCIATIONS': enriched_positions,
            'risk_variants': risk_variants[:50],
            'protective_variants': protective_variants[:50],
            'has_enhanced_classification': True,
            'variants_by_condition': self.get_variants_by_condition(),
            'section_configurations': self.determine_section_configurations(),
            'report_type': self.report_type,
            'PUBMED_EVIDENCE': pubmed_evidence
        }
        
        oneshot_blocks = self.block_generator.generate_report_blocks_parallel_with_progress(
            block_types=oneshot_block_types, 
            data=oneshot_input_dict
        )
        
        final_blocks.extend(oneshot_blocks)
        blocks = sorted(final_blocks, key=lambda x: x.order)
        
        
        
        # Validate and enhance blocks with mutation details
        blocks = self.validate_and_enhance_blocks(blocks, protein_mutations, oneshot_input_dict)
        
        # Handle different output formats
        if output_format == 'text' or output_format == 'both':
            # Original text output
            os.makedirs('reports_storage', exist_ok=True)
            with open(f'reports_storage/{name}.txt','w') as out:
                print('success?')
                for b in blocks:
                    content_to_write: str = b.content if isinstance(b.content, str) else json.dumps(b.content, indent=2)
                    out.write(content_to_write)
        
        # Prepare enhanced report info for both JSON output and caching
        enhanced_report_info = report_info.copy() if report_info else {}
        enhanced_report_info.update({
            'template_name': self.name or 'Precision Medicine Report',
            'report_name': self.name or 'Precision Medicine Report',
            'focus': self.prompt,
            'gwas_associations': enriched_positions,
            'mutations': prot2mut
        })
        
        if output_format == 'json' or output_format == 'both':
            # JSON output with enhanced metadata
            from json_report_writer import save_report_json
            
            json_path = save_report_json(
                blocks=blocks,
                report_name=name,
                report_info=enhanced_report_info
            )
            if json_path:
                logger.info(f"JSON report saved to: {json_path}")
            else:
                logger.error("Failed to save JSON report")

        # 4. Cache the generated report for future bit-for-bit consistency
        try:
            # Construct report text for cache
            full_text = "".join([b.content if isinstance(b.content, str) else json.dumps(b.content, indent=2) for b in blocks])
            
            cache_payload: dict[str, Any] = {
                'text': full_text,
                'blocks': [
                    {
                        'block_type': b.block_type.value if hasattr(b.block_type, 'value') else str(b.block_type),
                        'content': b.content,
                        'title': b.title,
                        'order': b.order
                    } for b in blocks
                ]
            }
            
            # If JSON was generated, include it in the cache too
            if output_format in ['json', 'both']:
                from json_report_writer import blocks_to_json
                cache_payload['json_data'] = blocks_to_json(blocks, enhanced_report_info)
            
            self.block_generator.cache.cache_description(report_signature, json.dumps(cache_payload), "v1")
            logger.info("✅ DEBUG: Report successfully cached for future use.")
        except Exception as e:
            logger.warning(f"⚠️ DEBUG: Failed to cache report: {e}")
        
        return blocks
        
    def look_at_genes(self, proteins: list[str]) -> list[str]:
        """
        Check if any of the mutated proteins correspond to genes of interest.
        
        Args:
            proteins: List of protein accession numbers
            
        Returns:
            List of genes of interest that are mutated
        """
        # Use the extract_mutated_genes function with required parameters
        mutated_genes = extract_mutated_genes(
            np_accessions=proteins,
            email='sskolusa@gmail.com',  # Using the email from the function definition
            api_key=None  # No API key provided, using default
        )
        
        had_genes_of_interest = []
        if mutated_genes:
            for gene in mutated_genes:
                if gene in self.goi:
                    had_genes_of_interest.append(gene)
        return had_genes_of_interest

    def _get_relevant_diseases(self, diseases: list[str], batch_size: int = 50) -> set[str]:
        """
        Identify which diseases from a list are relevant to the report focus using Gemini.
        """
        if not diseases or not self.prompt or not GEMINI_AVAILABLE:
            return set(diseases)
            
        relevant_diseases = set()
        
        # Batch process diseases to save tokens and time
        for i in range(0, len(diseases), batch_size):
            batch = diseases[i:i+batch_size]
            diseases_text = "\n".join([f"{j+1}. {d}" for j, d in enumerate(batch)])
            
            system_prompt = "You are a specialized clinical geneticist and disease expert."
            prompt = f"""
REPORT FOCUS: {self.prompt}

Please evaluate the following diseases/traits for their RELEVANCE to the report focus.
Only include diseases that have a clear pathological, clinical, or physiological connection to {self.prompt}.
Be selective; if a disease is only tangentially related or too broad, exclude it.

DISEASES TO EVALUATE:
{diseases_text}

INSTRUCTIONS:
1. Return ONLY the numbers of the relevant diseases, separated by commas.
2. If none are relevant, return "NONE".
3. Do not provide any explanations or extra text.
"""
            try:
                # Use the existing helper from block_generator
                response_text = generate_gemini_response(prompt, system_prompt, max_tokens=1024)
                
                if response_text.strip().upper() != "NONE":
                    relevant_nums = self._parse_relevant_numbers(response_text)
                    for num in relevant_nums:
                        if 1 <= num <= len(batch):
                            relevant_diseases.add(batch[num-1])
            except Exception as e:
                logger.error(f"Error in focal filtering for batch {i//batch_size}: {e}")
                # Fallback: keep all diseases in the batch on error to avoid missing data
                relevant_diseases.update(batch)
                
        return relevant_diseases

    def _parse_relevant_numbers(self, text: str) -> list[int]:
        """Parse comma-separated numbers from LLM response."""
        import re
        numbers = re.findall(r'\b\d+\b', text)
        return [int(n) for n in numbers]

    def _chunk_list(self, lst: list, chunk_size: int) -> list[list]:
        """Split a list into chunks of a specified size."""
        return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]

    def _merge_json_blocks(self, block_type: BlockType, blocks: list[ReportBlock]) -> ReportBlock:
        """Merge multiple report blocks that contain JSON content."""
        if not blocks:
            return self._create_error_block(block_type, "No blocks to merge")
        
        if len(blocks) == 1:
            return blocks[0]
            
        logger.info(f"Merging {len(blocks)} blocks for {block_type.value}")
        
        merged_data = {}
        successful_merges = 0
        
        for i, block in enumerate(blocks):
            try:
                # Clean block content for JSON parsing
                content = block.content.strip()
                if content.startswith("```json"):
                    content = content[7:-3].strip()
                elif content.startswith("```"):
                    content = content[3:-3].strip()
                
                data = json.loads(content)
                
                if not merged_data:
                    merged_data = data
                    successful_merges += 1
                    continue
                
                # Merge based on block type
                if block_type == BlockType.MUTATION_PROFILE:
                    # Merge lists
                    list_fields = ['risk_increasing_variants', 'protective_variants', 'neutral_variants', 
                                  'genetic_variants_affecting_proteins', 'key_protein_disease_findings', 
                                  'affected_biological_pathways', 'detailed_analysis']
                    for field in list_fields:
                        if field in data and isinstance(data[field], list):
                            if field not in merged_data:
                                merged_data[field] = []
                            merged_data[field].extend(data[field])
                    
                    # Merge conditions_summary
                    if 'conditions_summary' in data:
                        if 'conditions_summary' not in merged_data:
                            merged_data['conditions_summary'] = {}
                        for cond, summary in data['conditions_summary'].items():
                            if cond in merged_data['conditions_summary']:
                                # Add counts
                                for key in ['risk_count', 'protective_count', 'neutral_count']:
                                    merged_data['conditions_summary'][cond][key] = merged_data['conditions_summary'][cond].get(key, 0) + summary.get(key, 0)
                            else:
                                merged_data['conditions_summary'][cond] = summary
                
                elif block_type == BlockType.LITERATURE_EVIDENCE:
                    # Merge evidence lists
                    if 'evidence' in data and isinstance(data['evidence'], list):
                        if 'evidence' not in merged_data:
                            merged_data['evidence'] = []
                        merged_data['evidence'].extend(data['evidence'])
                
                # Add more merge logic as needed for other JSON blocks
                
                successful_merges += 1
            except Exception as e:
                logger.error(f"Error parsing/merging block {i} for {block_type.value}: {e}")
                continue
        
        if successful_merges == 0:
            return self._create_error_block(block_type, "Failed to parse/merge any blocks")
            
        return ReportBlock(
            block_type=block_type,
            title=blocks[0].title,
            content=json.dumps(merged_data, indent=2),
            template=blocks[0].template,
            order=blocks[0].order
        )
