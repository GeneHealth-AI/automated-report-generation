import logging
import os
import re
import json
import anthropic
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from threading import Lock
import hashlib
from report_blocks import BlockType, ReportBlock, BlockTemplate
from mutation_cache_manager import MutationCacheManager
import traceback
from pubmed_searcher import PubMedSearcher
# Configure logger
logger = logging.getLogger(__name__)

def create_anthropic_client_safe(api_key=None, timeout=240.0):
    """Create Anthropic client with proxy error handling."""
    if api_key is None:
        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
    
    try:
        return anthropic.Anthropic(api_key=api_key, timeout=timeout)
    except TypeError as e:
        if "proxies" in str(e):
            # Temporarily clear proxy environment variables
            proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'NO_PROXY', 'no_proxy']
            saved_vars = {}
            for var in proxy_vars:
                if var in os.environ:
                    saved_vars[var] = os.environ.pop(var)
            try:
                client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
                return client
            finally:
                for var, value in saved_vars.items():
                    os.environ[var] = value
        else:
            raise

# Gemini is no longer used — all LLM calls go through Claude Sonnet 4.6
GEMINI_AVAILABLE = True  # Kept for backward compatibility checks

BLOCKS_PATH = 'blocks'


'''def generate_textf_response(prompt: str, system_prompt: str, max_tokens: int = 50000) -> str:
    """
    Generate plain text response using Claude API with retry logic for overloaded errors.
    
    Args:
        prompt: The user prompt
        system_prompt: System instructions for Claude
        max_tokens: Maximum tokens to generate
        
    Returns:
        String containing the text response
    """
    # Get API key from environment variable
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")
    
    # Create Anthropic client using the safe method
    client = create_anthropic_client_safe(api_key, 240.0)
        else:
            raise

    # Retry parameters
    max_retries = 5
    retry_delay = 20  # seconds
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            print(f'STARTING API call (attempt {retry_count + 1}/{max_retries})')
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=max_tokens,
                temperature=0.1,  # Low temperature for consistent medical reports
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            print('API call successful!')
            
            # Extract the text content from the response
            content_text = response.content[0].text
            return content_text
            
        except Exception as e:
            error_str = str(e)
            retry_count += 1
            
            # Check if it's an overloaded error
            if "overloaded" in error_str.lower() or "529" in error_str:
                if retry_count < max_retries:
                    print(f"API overloaded. Retrying in {retry_delay} seconds... (Attempt {retry_count}/{max_retries})")
                    import time
                    time.sleep(retry_delay)
                    continue
                else:
                    print(f"Failed after {max_retries} attempts due to API overload")
            
            # For other errors, or if we've exhausted retries, raise the exception
            raise'''
def generate_gemini_response(prompt: str, system_prompt: str, max_tokens: int = 128000) -> str:
    """
    Generate a text response using Claude Sonnet 4.6 (Anthropic API).
    Kept as generate_gemini_response for backward compatibility with all callers.

    Args:
        prompt: The user prompt.
        system_prompt: System instructions for the model.
        max_tokens: Maximum tokens to generate (capped at 16384 for Claude).

    Returns:
        String containing the text response.
    """
    # Claude Sonnet 4.6 max output: 16384 tokens (standard mode)
    claude_max_tokens = 16384

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    client = create_anthropic_client_safe(api_key, timeout=240.0)

    max_retries = 5
    retry_delay = 20

    for attempt in range(max_retries):
        try:
            logger.info(f"Claude API call (attempt {attempt + 1}/{max_retries}), prompt: {len(prompt)} chars")
            response = client.messages.create(
                model="claude-sonnet-4-6-20250514",
                max_tokens=claude_max_tokens,
                temperature=0.1,
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}]
            )
            content_text = response.content[0].text
            logger.info(f"Claude API call successful, response: {len(content_text)} chars")
            return content_text

        except anthropic.RateLimitError as e:
            logger.warning(f"Rate limited: {e}")
            if attempt < max_retries - 1:
                logger.info(f"Retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 120)
                continue
            raise

        except anthropic.APIStatusError as e:
            if e.status_code == 529 or "overloaded" in str(e).lower():
                logger.warning(f"API overloaded: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 120)
                    continue
            logger.error(f"Claude API error: {e}")
            raise

        except Exception as e:
            logger.error(f"Unexpected error in Claude API call: {type(e).__name__}: {e}")
            if attempt < max_retries - 1 and any(x in str(e).lower() for x in ['timeout', 'connection']):
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 120)
                continue
            raise

def construct_blocks(blocks_path: str) -> Dict[BlockType, str]:
    """Load block templates from text files."""
    blocks = {}
    for block_type in BlockType:
        template_file = f"{blocks_path}/{block_type.value}_block.txt"
        try:
            with open(template_file, 'r') as f:
                blocks[block_type] = f.read()
        except FileNotFoundError:
            logger.warning(f"Template file not found: {template_file}")
            blocks[block_type] = f"Template for {block_type.value} not found."
    return blocks

def replace_terms(paragraph_path: str, mapping: dict) -> str:
    """
    Replace tokens of the form <KEY> in the paragraph with mapping[KEY].

    Args:
        paragraph: A string containing tokens like <WORD>.
        mapping:   A dict where each key is a token name (without <>) 
                and each value is the replacement string.

    Returns:
        A new string with all <KEY> replaced by mapping[KEY].
        Unknown keys are left as-is.
    """
    paragraph = open(paragraph_path).read()
    token_re = re.compile(r'<(\w+)>')

    def _repl(match):
        key = match.group(1)
        value = mapping.get(key)
        
        # If the value is None or empty, provide a default placeholder
        if value is None or value == '':
            if key == 'MUTATED_PROTEINS':
                return "No protein mutation data available"
            elif key == 'PROTEIN_DISEASES':
                return "No protein-disease associations identified"
            elif key == 'GWAS_ASSOCIATIONS':
                return "No GWAS associations identified"
            elif key == 'PUBMED_EVIDENCE':
                return "No additional PubMed research required for this variant profile."
            elif key == 'RISK_DATA':
                return "No specific risk mapping data available. Use published literature to estimate risk levels."
            else:
                return match.group(0)  # Keep the original placeholder
        
        return str(value)

    return token_re.sub(_repl, paragraph)

class ReportBlockGenerator:
    def __init__(self, blocks_path=BLOCKS_PATH, block_configs=None):
        """
        Initialize the block generator.
        
        Args:
            blocks_path: Path to block template files
            block_configs: Optional dict of block-specific configurations from JSON template
        """
        logger.info("🔧 DEBUG: ReportBlockGenerator.__init__() starting")
        
        try:
            self.blocks_path = blocks_path
            self.block_configs = block_configs or {}
            self.max_workers = 2  # Adjust based on API limits
            
            # Initialize cache
            self.cache = MutationCacheManager()
            self.model_version = "v1-gemini-3-flash-preview" # Version for caching
            
            # Lock for thread-safe operations if needed
            self._lock = Lock()
            logger.info("🔧 DEBUG: Constructing blocks from templates")
            self.blocks = construct_blocks(blocks_path)
            logger.info("✅ DEBUG: Blocks constructed successfully")
            
            self.prompt = self.block_configs.get('custom_prompt', '')
            
            logger.info("🔧 DEBUG: Setting up threading and rate limiting")
            self.rate_limit_lock = Lock()
            self.last_api_call = 0
            self.min_interval = 0.1
            
            # Enhanced block templates for specific sections
            self.enhanced_templates: dict[BlockType, str] = {
                BlockType.MUTATION_PROFILE: "enhanced_mutation_profile_block.html",
                BlockType.CLINICAL_IMPLICATIONS: "enhanced_clinical_implications_block.html",
                BlockType.EXECUTIVE_SUMMARY: "enhanced_executive_summary_block.html",
                BlockType.INTRODUCTION: "enhanced_introduction_block.html",
                BlockType.LIFESTYLE_RECOMMENDATIONS: "enhanced_lifestyle_recommendations_block.html",
                BlockType.MONITORING_PLAN: "enhanced_monitoring_plan_block.html"
            }
            
            logger.info("✅ DEBUG: ReportBlockGenerator initialization completed")
        except Exception as e:
            logger.error(f"❌ DEBUG: Error in ReportBlockGenerator.__init__: {str(e)}")
            logger.error(f"❌ DEBUG: ReportBlockGenerator init traceback: {traceback.format_exc()}")
            raise  
        
    def _rate_limited_api_call(self, prompt: str, system_prompt: str, max_tokens: int = 16384) -> str:
        """
        Make a rate-limited API call to prevent hitting rate limits.
        
        Args:
            prompt: The user prompt
            system_prompt: System instructions for the model
            max_tokens: Maximum tokens to generate
            
        Returns:
            Generated text response
        """
        # Use a lock-protected interval check but run the API call outside the lock
        wait_time = 0
        with self.rate_limit_lock:
            now = time.time()
            time_since_last_call = now - self.last_api_call
            
            if time_since_last_call < self.min_interval:
                wait_time = self.min_interval - time_since_last_call
                # Update last_api_call as if we already waited
                self.last_api_call = now + wait_time
            else:
                self.last_api_call = now
        
        if wait_time > 0:
            time.sleep(wait_time)
            
        # Use Gemini API (OpenAI currently disabled)
        if not os.environ.get('GEMINI_API_KEY'):
            raise ValueError("GEMINI_API_KEY environment variable: the key is the problem")
        if not GEMINI_AVAILABLE:
            raise ValueError("google-generativeai not installed")
        
        result = generate_gemini_response(prompt, system_prompt, max_tokens)
        return result
    
    def get_block_path(self, block_type):
        # Use relative paths for block templates
        blocks_dir = './blocks'
        
        if block_type == BlockType.INTRODUCTION:
            return f'{blocks_dir}/introduction_block.txt'
        elif block_type == BlockType.EXECUTIVE_SUMMARY:
            return f'{blocks_dir}/executive_summary_block.txt'
        elif block_type == BlockType.MUTATION_PROFILE:
            return f'{blocks_dir}/mutation_profile_block.txt'
        elif block_type == BlockType.LITERATURE_EVIDENCE:
            return f'{blocks_dir}/literature_evidence_block.txt'
        elif block_type == BlockType.RISK_ASSESSMENT:
            return f'{blocks_dir}/risk_assessment_block.txt'
        elif block_type == BlockType.CLINICAL_IMPLICATIONS:
            return f'{blocks_dir}/clinical_implications_block.txt'
        elif block_type == BlockType.LIFESTYLE_RECOMMENDATIONS:
            return f'{blocks_dir}/lifestyle_recommendations_block.txt'
        elif block_type == BlockType.MONITORING_PLAN:
            return f'{blocks_dir}/monitoring_plan_block.txt'
        elif block_type == BlockType.RESEARCH_OPPORTUNITIES:
            return f'{blocks_dir}/research_opportunities_block.txt'
        elif block_type == BlockType.GWAS_ANALYSIS:
            return f'{blocks_dir}/gwas_analysis_block.txt'
        elif block_type == BlockType.CONCLUSION:
            return f'{blocks_dir}/conclusion_block.txt'
        else:
            return None 
    
    def generate_block(self, block_type: BlockType, data: Dict[str, Any]) -> ReportBlock:
        """
        Generate a single report block using patient info. Should probably return more fields...
        
        Args:
            block_type: Type of block to generate
            data: Data dictionary containing required information
                DG : list of (disease,gene) tuples
                PATIENT_HISTORY : text about patient history can be none
                FEEDBACK : feedback if the report needs to be modified
                PREVIOUS_VERSION : previous version to be referenced by feedback
                SUMMARY : summary of what has been said in the previous blocks
                
        
        Returns:
            Generated ReportBlock instance dictionary maybe
            """
        # Get block-specific configuration if available
        block_config = self.block_configs.get(block_type, {})
        
        prompt = self.block_configs.get('custom_prompt', '')
        block_text = self.get_block_path(block_type)
        enriched_text = replace_terms(block_text,data)
        # Determine audience-specific instructions
        report_type = data.get('report_type', '').lower()
        is_patient_report = any(term in report_type for term in ['patient', 'standard', 'user', 'consumer'])
        
        audience_instruction = "Use clear, professional medical language appropriate for healthcare providers. Be comprehensive and descriptive; avoid being overly terse."
        if is_patient_report:
            audience_instruction = "Use simple, conversational, and highly accessible language (layman terms) appropriate for a patient without medical training. Avoid all unnecessary medical jargon. If a technical term is essential, explain it using an analogy or simple definition in a friendly, supportive tone. Be descriptive and thorough in your explanations to ensure the patient fully understands the implications."

        system_prompt = f"""You are a world-class precision medicine expert and clinical geneticist with extensive experience in precision medicine:

IMPORTANT: This report has a specific focus that MUST guide all your responses:
This report is designed to tackle {prompt}. Please ensure to orient the information you provide to {prompt}. If genetic information provided is not related to the condition, do not include it in the final output. 

You must tailor ALL content to address this specific focus throughout the report.

        • Genomic medicine and personalized treatment strategies
        • Clinical interpretation of genetic variants and their therapeutic implications
        • Drug-gene interactions and pharmacogenomics
        • Evidence-based medicine and clinical guidelines integration
        • Patient-centered communication of complex genetic information

        Your expertise includes:
        - Comprehensive knowledge of genetic databases (ClinVar, COSMIC, PharmGKB, etc.)
        - Understanding of variant pathogenicity classification (ACMG guidelines)
        - Familiarity with therapeutic guidelines from major organizations (NCCN, FDA, EMA)
        - Experience with diverse patient populations and genetic backgrounds
        - Ability to synthesize complex genomic data into actionable clinical insights

        CRITICAL REQUIREMENTS:
        1. DUAL-USABILITY: Create a consumer-first layer with plain, empowering language while retaining technical accuracy for clinicians.
        2. ABSOLUTE RISK: Always use absolute risk ranges (e.g., "40-50% by age 70") and compare them to population risk (e.g., "1-2% population average") when these data are available.
        3. RISK CALIBRATION: Use language like "risk-increasing" or "protective" rather than solely relying on "pathogenic" or "benign".
        4. ACTIONABLE INSIGHTS: Translate genetic findings into proactive management strategies.
        5. Format your response as a well-structured medical report section using clear headers and bullet points.
        6. Clearly distinguish between established clinical facts and emerging research.
        7. {audience_instruction}
        8. DO NOT HALLUCINATE - only include information supported by scientific evidence.
        9. If feedback or previous block summaries are provided, ensure consistency and build upon them.
        10. Include appropriate caveats about genetic testing limitations.

        Your response should be formatted text following the structure specified in the prompt."""
        
        # Use Gemini API (OpenAI currently disabled)
        if not (os.environ.get('GEMINI_API_KEY') and GEMINI_AVAILABLE):
            raise ValueError("GEMINI_API_KEY environment variable not set or google-generativeai not installed")
        
        result = generate_gemini_response(enriched_text, system_prompt, max_tokens=128000)
        
        # Extract summary and modifications if present in the text
        content_text = result
        
        # Simple extraction of summary and modifications from the text
        modifications = ""
        
        # Look for a summary section at the end
        if "**Summary**" in content_text:
            summary_start = content_text.rfind("**Summary**")
            summary_text = content_text[summary_start:]
            summary = summary_text.split("\n", 2)[1].strip() if "\n" in summary_text else ""
        
        # Look for modifications note
        if "[If feedback was provided" in content_text:
            mod_start = content_text.rfind("[If feedback was provided")
            mod_end = content_text.find("]", mod_start)
            if mod_end > mod_start:
                modifications = content_text[mod_start:mod_end+1]
        
        return ReportBlock(
            block_type=block_type,
            title=self._get_block_title(block_type),
            content=content_text,  # Store the full formatted text
            template=f"{block_type.value}_block.html",
            order=self._get_block_order(block_type),
            modifications=modifications
        )
        

    def generate_report_blocks(self, block_types: List[BlockType], data: Dict[str, Any]) -> List[ReportBlock]:
        """
        Generate multiple blocks for a complete report with enhanced classification system support.
        
        Args:
            block_types: List of block types to generate
            data: Shared data dictionary for all blocks
            
        Returns:
            List of generated ReportBlock instances
            
        Requirements: 4.1, 4.2, 4.3
        """
        blocks = []
        
        # Check if enhanced classification data is available
        has_enhanced_data = data.get('has_enhanced_classification', False)
        
        if has_enhanced_data:
            logger.info("Using enhanced classification system for block generation")
            # Use enhanced block generation workflow
            blocks = self._generate_enhanced_blocks(block_types, data)
        else:
            logger.info("Using legacy block generation workflow")
            # Use legacy block generation for backward compatibility
            blocks = self._generate_legacy_blocks(block_types, data)
        
        # Sort blocks by order
        blocks.sort(key=lambda x: x.order)
        return blocks
    
    def _generate_enhanced_blocks(self, block_types: List[BlockType], data: Dict[str, Any]) -> List[ReportBlock]:
        """
        Generate blocks using the enhanced classification system.
        
        Args:
            block_types: List of block types to generate
            data: Enhanced data dictionary with section configurations
            
        Returns:
            List of generated ReportBlock instances
        """
        blocks = []
        section_configs = data.get('section_configurations', {})
        variants_by_condition = data.get('variants_by_condition', {})
        
        for block_type in block_types:
            # Get block configuration if available
            block_config = self.block_configs.get(block_type, {})
            
            # Check if block should be generated (visibility and requirements)
            if not block_config.get('is_visible', True):
                continue
            
            # Determine if this block type should be generated based on section configurations
            should_generate = self._should_generate_enhanced_block(
                block_type, section_configs, variants_by_condition
            )
            
            if not should_generate:
                logger.debug(f"Skipping {block_type.value} block - no relevant variants")
                continue
                
            # Prepare enhanced block-specific data
            block_data = self._prepare_enhanced_block_data(block_type, data)
            
            block = self.generate_block(block_type, block_data)
            blocks.append(block)
                
            logger.info(f"Successfully generated enhanced {block_type.value} block")
        
        return blocks
    
    def _generate_legacy_blocks(self, block_types: List[BlockType], data: Dict[str, Any]) -> List[ReportBlock]:
        """
        Generate blocks using the legacy workflow for backward compatibility.
        
        Args:
            block_types: List of block types to generate
            data: Legacy data dictionary
            
        Returns:
            List of generated ReportBlock instances
        """
        blocks = []
        
        for block_type in block_types:
            # Get block configuration if available
            block_config = self.block_configs.get(block_type, {})
            
            # Check if block should be generated (visibility and requirements)
            if not block_config.get('is_visible', True):
                continue
                
            # Prepare block-specific data using legacy method
            block_data = self._prepare_block_data(block_type, data)
            
            block = self.generate_block(block_type, block_data)
            blocks.append(block)
                
            logger.debug(f"Successfully generated legacy {block_type.value} block")
        
        return blocks
    
    def _should_generate_enhanced_block(self, block_type: BlockType, 
                                      section_configs: Dict[str, Any],
                                      variants_by_condition: Dict[str, List]) -> bool:
        """
        Determine if a block should be generated based on enhanced section configurations.
        
        Args:
            block_type: Type of block to check
            section_configs: Section configurations by condition
            variants_by_condition: Variants organized by condition
            
        Returns:
            True if the block should be generated
        """
        if not section_configs:
            return True  # Generate all blocks if no section config available
        
        # Check if any condition requires this block type
        for condition, config in section_configs.items():
            if block_type == BlockType.RISK_ASSESSMENT:
                if config.show_risk_section:
                    return True
            elif block_type == BlockType.CLINICAL_IMPLICATIONS:
                # Generate if there are any variants (risk or protective)
                if config.show_risk_section or config.show_protective_section:
                    return True
            elif block_type == BlockType.MUTATION_PROFILE:
                # Generate if there are any variants
                if config.risk_variant_count > 0 or config.protective_variant_count > 0:
                    return True
            elif block_type == BlockType.LITERATURE_EVIDENCE:
                # Generate if there are high-confidence variants
                condition_variants = variants_by_condition.get(condition, [])
                if any(hasattr(v, 'has_high_confidence') and v.has_high_confidence() 
                      for v in condition_variants):
                    return True
            else:
                # For other block types, generate if there are any variants
                if config.risk_variant_count > 0 or config.protective_variant_count > 0:
                    return True
        
        return False
    
    def _prepare_enhanced_block_data(self, block_type: BlockType, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare block-specific data using enhanced classification information.
        
        Args:
            block_type: Type of block being generated
            data: Enhanced data dictionary
            
        Returns:
            Block-specific data dictionary
        """
        # Start with legacy data for backward compatibility
        block_data = self._prepare_block_data(block_type, data)
        
        # Add enhanced classification data
        section_configs = data.get('section_configurations', {})
        variants_by_condition = data.get('variants_by_condition', {})
        classified_variants = data.get('classified_variants', [])
        
        # Add enhanced data fields
        block_data['section_configurations'] = section_configs
        block_data['variants_by_condition'] = variants_by_condition
        block_data['classified_variants'] = classified_variants
        block_data['has_enhanced_classification'] = True
        
        # Add block-specific enhanced data
        if block_type == BlockType.RISK_ASSESSMENT:
            block_data.update(self._prepare_risk_assessment_enhanced_data(
                section_configs, variants_by_condition
            ))
        elif block_type == BlockType.CLINICAL_IMPLICATIONS:
            block_data.update(self._prepare_clinical_implications_enhanced_data(
                section_configs, variants_by_condition
            ))
        elif block_type == BlockType.MUTATION_PROFILE:
            block_data.update(self._prepare_mutation_profile_enhanced_data(
                section_configs, variants_by_condition
            ))
        
        return block_data
    
    def _prepare_risk_assessment_enhanced_data(self, section_configs: Dict[str, Any],
                                             variants_by_condition: Dict[str, List]) -> Dict[str, Any]:
        """Prepare enhanced data for risk assessment blocks."""
        risk_data = {
            'risk_conditions': [],
            'protective_conditions': [],
            'mixed_conditions': []
        }
        
        for condition, config in section_configs.items():
            condition_data = {
                'condition': condition,
                'risk_variant_count': config.risk_variant_count,
                'protective_variant_count': config.protective_variant_count,
                'priority': config.section_priority.value if hasattr(config.section_priority, 'value') else 'medium'
            }
            
            if config.show_risk_section and config.show_protective_section:
                risk_data['mixed_conditions'].append(condition_data)
            elif config.show_risk_section:
                risk_data['risk_conditions'].append(condition_data)
            elif config.show_protective_section:
                risk_data['protective_conditions'].append(condition_data)
        
        return risk_data
    
    def _prepare_clinical_implications_enhanced_data(self, section_configs: Dict[str, Any],
                                                   variants_by_condition: Dict[str, List]) -> Dict[str, Any]:
        """Prepare enhanced data for clinical implications blocks."""
        clinical_data = {
            'actionable_conditions': [],
            'monitoring_conditions': [],
            'total_conditions': len(section_configs)
        }
        
        for condition, config in section_configs.items():
            if config.risk_variant_count > 0 or config.protective_variant_count > 0:
                condition_data = {
                    'condition': condition,
                    'has_risk_variants': config.show_risk_section,
                    'has_protective_variants': config.show_protective_section,
                    'priority': config.section_priority.value if hasattr(config.section_priority, 'value') else 'medium'
                }
                
                # Determine if condition is actionable based on variant confidence
                condition_variants = variants_by_condition.get(condition, [])
                has_high_confidence = any(
                    hasattr(v, 'has_high_confidence') and v.has_high_confidence() 
                    for v in condition_variants
                )
                
                if has_high_confidence:
                    clinical_data['actionable_conditions'].append(condition_data)
                else:
                    clinical_data['monitoring_conditions'].append(condition_data)
        
        return clinical_data
    
    def _prepare_mutation_profile_enhanced_data(self, section_configs: Dict[str, Any],
                                              variants_by_condition: Dict[str, List]) -> Dict[str, Any]:
        """Prepare enhanced data for mutation profile blocks."""
        from variant_classifier import EffectDirection
        
        mutation_data = {
            'risk_variants': [],
            'protective_variants': [],
            'neutral_variants': [],
            'conditions_summary': {}
        }
        
        for condition, variants in variants_by_condition.items():
            condition_summary = {
                'risk_count': 0,
                'protective_count': 0,
                'neutral_count': 0
            }
            
            for variant in variants:
                variant_info = {
                    'rsid': variant.rsid,
                    'gene': variant.gene,
                    'condition': condition,
                    'effect_direction': variant.effect_direction.value,
                    'confidence_level': variant.confidence_level.value,
                    'confidence_score': variant.confidence_score,
                    # Verified input data
                    'protein_id': getattr(variant, 'protein_id', None),
                    'hgvs': getattr(variant, 'hgvs', None),
                    'amino_acid_position': getattr(variant, 'amino_acid_position', None),
                    'ref_amino_acid': getattr(variant, 'ref_amino_acid', None),
                    'alt_amino_acid': getattr(variant, 'alt_amino_acid', None),
                    'score': getattr(variant, 'score', None),
                    'clinical_significance': getattr(variant, 'clinical_significance', None),
                    'evidence_strength': getattr(variant, 'evidence_strength', None),
                    'variant_description': str(variant),
                }
                
                if variant.effect_direction == EffectDirection.RISK_INCREASING:
                    mutation_data['risk_variants'].append(variant_info)
                    condition_summary['risk_count'] += 1
                elif variant.effect_direction == EffectDirection.PROTECTIVE:
                    mutation_data['protective_variants'].append(variant_info)
                    condition_summary['protective_count'] += 1
                else:
                    mutation_data['neutral_variants'].append(variant_info)
                    condition_summary['neutral_count'] += 1
            
            mutation_data['conditions_summary'][condition] = condition_summary
        
        return mutation_data
    def generate_block_parallel(self, block_type: BlockType, data: Dict[str, Any]) -> ReportBlock:
        """
        Generate a single report block - designed for parallel execution.
        
        Args:
            block_type: Type of block to generate
            data: Data dictionary containing required information
                
        Returns:
            Generated ReportBlock instance
        """
        try:
            # Get block-specific configuration if available
            block_config = self.block_configs.get(block_type, {})
            
            prompt = self.block_configs.get('custom_prompt', '')
            block_path = self.get_block_path(block_type)
            if not block_path:
                raise ValueError(f"No template found for block type {block_type}")
            
            enriched_text = replace_terms(block_path, data)
            
            system_prompt = f"""You are a world-class precision medicine expert and clinical geneticist with extensive experience in precision medicine:

IMPORTANT: This report has a specific focus that MUST guide all your responses:
This report is designed to tackle {prompt}. Please ensure to orient the information you provide to {prompt}.

You must tailor ALL content to address this specific focus throughout the report.

            • Genomic medicine and personalized treatment strategies
            • Clinical interpretation of genetic variants and their therapeutic implications
            • Patient-centered communication of complex genetic information
            • Translating dense scientific literature into accessible language

            Your expertise includes:
            - Comprehensive knowledge of genetic databases (ClinVar, COSMIC, PharmGKB, etc.)
            - Understanding of variant pathogenicity classification (ACMG guidelines)
            - Familiarity with therapeutic guidelines from major organizations (NCCN, FDA, EMA)
            - Experience with diverse patient populations and genetic backgrounds
            - Ability to synthesize complex genomic data into actionable clinical insights

            CRITICAL REQUIREMENTS:
            1. LAYMAN ACCESSIBILITY: This report is primarily for the PATIENT, not the clinician. Use clear, plain, empowering language. Avoid dense medical jargon. When technical terms must be used, explain them simply.
            2. ABSOLUTE RISK: Always use absolute risk ranges (e.g., "40-50% by age 70") and compare them to population risk (e.g., "1-2% population average") when these data are available.
            3. RISK CALIBRATION: Use language like "risk-increasing" or "protective" rather than solely relying on "pathogenic" or "benign".
            4. ACTIONABLE INSIGHTS: Translate genetic findings into proactive management strategies.
            5. Format your response as a well-structured medical report section using clear headers and bullet points.
            6. Clearly distinguish between established clinical facts and emerging research.
            7. DO NOT HALLUCINATE - only include information supported by scientific evidence.
            8. If feedback or previous block summaries are provided, ensure consistency and build upon them.
            9. Include appropriate caveats about genetic testing limitations.
            10. As the effectiveness of using genetic data for many cases is not certain, err on the side of caution.
            11. VERIFIED DATA ONLY: You are provided verified variant data from the input analysis. Use ONLY the protein IDs, gene names, HGVS notations, amino acid changes, and pathogenicity scores that are explicitly provided. Do NOT fabricate, invent, or guess any rsIDs (rs numbers), ClinVar IDs, dbSNP identifiers, or clinical annotations that are not in the provided data.
            12. VARIANT ACCURACY: When describing mutations, use the exact HGVS notation and amino acid change from the verified data. If an rsID is not provided, do not create one. Instead use the HGVS notation (e.g., NP_002760.1:p.Gly62Ala) as the variant identifier.
            13. STRICT CITATION RULES (NO FAKE PMIDS): You must NEVER invent, fabricate, guess, or hallucinate PubMed IDs (PMIDs). If the prompt asks for PMIDs, you must ONLY use the exact PMIDs provided to you in the "VERIFIED RESEARCH DATA" section. If no PMIDs are provided for a claim, state that evidence is from general clinical knowledge rather than inventing a citation.

            Your response should be formatted text following the structure specified in the prompt."""
            
            # 1. Check Cache
            # Create a deterministic signature based on prompts
            
            # NEW: Granular caching logic
            # For INTRODUCTION, we want consistency across different patients for the same disease focus.
            # We strip patient-specific fields from the signature to allow cache hits for different patients.
            api_prompt = enriched_text
            if block_type == BlockType.INTRODUCTION:
                sig_data = data.copy()
                # Fields that make a block patient-specific
                patient_fields = ['DEMOGRAPHICS', 'PATIENTNAME', 'FAMILY_HISTORY', 'FAMILYHISTORY', 'PROVIDER', 'CLINICAL_CONTEXT', 'CLINICALHISTORY']
                for field in patient_fields:
                    sig_data.pop(field, None)
                
                # Re-calculate enriched text for signature AND generation (stripped of patient data)
                api_prompt = replace_terms(block_path, sig_data)
                prompt_content = f"{system_prompt}\n{api_prompt}"
            else:
                # Default: full content hash for maximum consistency and safety
                prompt_content = f"{system_prompt}\n{enriched_text}"

            prompt_hash = hashlib.sha256(prompt_content.encode('utf-8')).hexdigest()
            signature = f"BLOCK:{block_type.value}:{prompt_hash}"
            
            cached_text = self.cache.get_description(signature)
            if cached_text:
                logger.info(f"Cache hit for {block_type.value} block")
                content_text = cached_text
            else:
                logger.info(f"Cache miss for {block_type.value} block. Generating...")
                
                # Special logic for Literature Evidence RAG
                if block_type == BlockType.LITERATURE_EVIDENCE:
                    try:
                        logger.info("Starting PubMed RAG process for Literature Evidence")
                        # 1. Generate PubMed search queries
                        query_generation_prompt = f"""
                        Based on the following genetic data, generate 1-3 highly specific PubMed search queries.
                        Focus on the protein mutations and their associations with the disease focus.
                        
                        Genetic Data: {data.get('VARIANTS', 'None')}
                        Disease Focus: {prompt}
                        
                        Output ONLY a JSON list of query strings. Example: ["PRSS1 R122H pancreatic cancer", "CLPS mutations chronic pancreatitis"]
                        """
                        query_resp = self._rate_limited_api_call(query_generation_prompt, "You are a bioinformatics expert. Output ONLY valid JSON.")
                        
                        # Parse queries
                        try:
                            # Clean markdown if present
                            clean_resp = query_resp.strip()
                            if clean_resp.startswith("```json"):
                                clean_resp = clean_resp[7:-3].strip()
                            elif clean_resp.startswith("```"):
                                clean_resp = clean_resp[3:-3].strip()
                            queries = json.loads(clean_resp)
                        except:
                            logger.warning("Failed to parse PubMed queries as JSON, using raw response.")
                            queries = [query_resp.strip()]
                        
                        # 2. Fetch evidence for each query
                        searcher = PubMedSearcher()
                        all_evidence = []
                        for q in queries[:2]: # Limit to top 2 queries for speed
                            evidence = searcher.get_evidence(q, retmax=3)
                            all_evidence.append(f"QUERY: {q}\n{evidence}")
                        
                        combined_evidence = "\n\n=== VERIFIED RESEARCH DATA ===\n" + "\n\n".join(all_evidence)
                        
                        # 3. Append evidence to the API prompt
                        api_prompt = f"{api_prompt}\n\n{combined_evidence}\n\nIMPORTANT: Use the 'VERIFIED RESEARCH DATA' provided above to populate the report. Ensure to include PMIDs for all studies cited."
                    except Exception as rag_e:
                        logger.error(f"PubMed RAG failed: {str(rag_e)}")
                        # Continue with standard generation if RAG fails

                # 2. Make rate-limited API call
                result = self._rate_limited_api_call(api_prompt, system_prompt, max_tokens=16384)
                content_text = result
                
                # 3. Cache Result
                self.cache.cache_description(signature, content_text, self.model_version)
            
            modifications = ""
            
            # Look for modifications note
            if "[If feedback was provided" in content_text:
                mod_start = content_text.rfind("[If feedback was provided")
                mod_end = content_text.find("]", mod_start)
                if mod_end > mod_start:
                    modifications = content_text[mod_start:mod_end+1]
            
            # Determine which template to use
            template_name = f"{block_type.value}_block.html"
            if data.get('has_enhanced_classification'):
                template_name = self.enhanced_templates.get(block_type, template_name)
            
            return ReportBlock(
                block_type=block_type,
                title=self._get_block_title(block_type),
                content=content_text,
                template=template_name,
                order=self._get_block_order(block_type),
                modifications=modifications
            )
            
        except Exception as e:
            logger.error(f"Error generating {block_type.value} block: {str(e)}")
            return self._create_error_block(block_type, str(e))
    
    def generate_report_blocks_parallel_with_progress(self, block_types: List[BlockType], data: Dict[str, Any], progress_callback=None) -> List[ReportBlock]:
        """
        Generate multiple blocks with progress tracking.
        
        Args:
            block_types: List of block types to generate
            data: Shared data dictionary for all blocks
            progress_callback: Optional callback function to report progress
            
        Returns:
            List of generated ReportBlock instances, sorted by order
        """
        blocks = []
        completed_count = 0
        
        # Filter blocks based on visibility
        visible_blocks = []
        for block_type in block_types:
            block_config = self.block_configs.get(block_type, {})
            if block_config.get('is_visible', True):
                visible_blocks.append(block_type)
        
        total_blocks = len(visible_blocks)
        
        # Prepare block data for each block type
        block_data_map = {}
        for block_type in visible_blocks:
            block_data_map[block_type] = self._prepare_block_data(block_type, data)
        
        # Use ThreadPoolExecutor for parallel execution
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_block = {
                executor.submit(self.generate_block_parallel, block_type, block_data_map[block_type]): block_type
                for block_type in visible_blocks
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_block):
                block_type = future_to_block[future]
                try:
                    block = future.result()
                    blocks.append(block)
                    completed_count += 1
                    logger.info(f"Successfully generated {block_type.value} block ({completed_count}/{total_blocks})")
                    
                    # Call progress callback if provided
                    if progress_callback:
                        progress_callback(completed_count, total_blocks, block_type.value)
                        
                except Exception as e:
                    logger.error(f"Failed to generate {block_type.value} block: {str(e)}")
                    # Create error block
                    error_block = self._create_error_block(block_type, str(e))
                    blocks.append(error_block)
                    completed_count += 1
                    
                    if progress_callback:
                        progress_callback(completed_count, total_blocks, f"{block_type.value} (ERROR)")
        
        # Sort blocks by order
        blocks.sort(key=lambda x: x.order)
        return blocks
    
    def _filter_data_for_block(self, block_type: BlockType, data: Dict[str, Any], block_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Filter data based on block-specific configuration.
        
        Args:
            block_type: Type of block being generated
            data: Original data dictionary
            block_config: Block-specific configuration
            
        Returns:
            Filtered data dictionary
        """
        filtered_data = data.copy()
        
        # Apply protein analysis filtering if configured
        protein_analysis = block_config.get('protein_analysis', {})
        if protein_analysis:
            # Filter proteins based on score threshold
            min_score = protein_analysis.get('min_protein_score', 0.6)
            max_proteins = protein_analysis.get('max_proteins', 30)
            
            # This would need actual implementation based on protein data structure
            # For now, just pass the configuration as metadata
            filtered_data['_protein_config'] = protein_analysis
        
        # Apply gene filtering if configured
        include_genes = block_config.get('include_genes', [])
        exclude_genes = block_config.get('exclude_genes', [])
        
        if include_genes or exclude_genes:
            filtered_data['_gene_filter'] = {
                'include': include_genes,
                'exclude': exclude_genes
            }
        
        return filtered_data

    def _build_progressive_summaries(self, current_block_type: BlockType, data: Dict[str, Any]) -> str:
        """
        Build progressive summaries from previous blocks to reduce redundancy and create narrative flow.
        
        Args:
            current_block_type: The type of block currently being generated
            data: Data dictionary containing all available information
            
        Returns:
            String containing summaries of previous blocks for context
        """
        # Define block order for progressive building
        block_order = [
            BlockType.INTRODUCTION,
            BlockType.EXECUTIVE_SUMMARY,
            BlockType.MUTATION_PROFILE,
            BlockType.LITERATURE_EVIDENCE,
            BlockType.RISK_ASSESSMENT,
            BlockType.CLINICAL_IMPLICATIONS,
            BlockType.LIFESTYLE_RECOMMENDATIONS,
            BlockType.MONITORING_PLAN,
            BlockType.GWAS_ANALYSIS
        ]
        
        current_order = block_order.index(current_block_type) if current_block_type in block_order else 0
        
        # Build context from previous blocks
        context_parts = []
        
        if current_order > 0:  # Introduction
            context_parts.append("INTRODUCTION CONTEXT: This report focuses on genetic analysis for the specified condition.")
        
        if current_order > 1:  # Executive Summary
            context_parts.append("EXECUTIVE SUMMARY CONTEXT: Key genetic findings and primary recommendations have been established.")
        
        if current_order > 2:  # Mutation Profile
            context_parts.append("MUTATION PROFILE CONTEXT: Specific protein mutations and their functional impacts have been detailed. Build upon these specific mutations rather than repeating them.")
        
        if current_order > 3:  # Literature Evidence
            context_parts.append("LITERATURE EVIDENCE CONTEXT: Research evidence supporting the genetic findings has been presented. Reference this evidence rather than re-presenting it.")
        
        if current_order > 4:  # Risk Assessment
            context_parts.append("RISK ASSESSMENT CONTEXT: Disease risks based on genetic profile have been evaluated. Use these risk levels in your analysis.")
        
        if current_order > 5:  # Clinical Implications
            context_parts.append("CLINICAL IMPLICATIONS CONTEXT: Treatment and screening recommendations have been provided. Build upon these clinical insights.")
        
        if current_order > 6:  # Lifestyle Recommendations
            context_parts.append("LIFESTYLE CONTEXT: Lifestyle modifications based on genetic profile have been recommended.")
        
        if current_order > 7:  # Monitoring Plan
            context_parts.append("MONITORING CONTEXT: Monitoring strategies have been established.")
        
        # Add specific guidance for reducing redundancy
        if context_parts:
            context_parts.append("\nIMPORTANT: Avoid repeating information from previous sections. Instead, build upon and reference previous findings to create a cohesive narrative flow.")
        
        return "\n".join(context_parts)

    def _filter_relevant_gwas(self, gwas_data: str, condition_focus: str) -> str:
        """
        Filter GWAS associations to only include those relevant to the condition focus.
        
        Args:
            gwas_data: Raw GWAS data string or list
            condition_focus: The condition/disease focus of the report
            
        Returns:
            Filtered GWAS data containing only relevant associations
        """
        if not gwas_data or not condition_focus:
            return gwas_data
        
        # Convert condition focus to lowercase for matching
        focus_lower = condition_focus.lower()
        
        # Enhanced condition-specific keywords with relevance tiers and exclusions
        condition_keywords = {
            'adhd': {
                'primary': ['adhd', 'attention deficit', 'hyperactivity', 'attention', 'hyperactive', 'impulsivity', 'inattention'],
                'secondary': ['executive function', 'working memory', 'cognitive control', 'inhibitory control', 'response inhibition'],
                'comorbid': ['anxiety', 'depression', 'mood', 'sleep', 'substance', 'addiction', 'conduct disorder', 'oppositional defiant'],
                'pharmacogenomic': ['methylphenidate', 'amphetamine', 'atomoxetine', 'stimulant', 'cyp2d6', 'comt', 'dat1', 'drd4'],
                'exclude': ['cancer', 'tumor', 'malignant', 'carcinoma', 'oncology', 'graft', 'pancreatitis', 'lipid', 'cholesterol', 'triglyceride', 'metabolite', 'inflammatory bowel', 'crohn', 'ulcerative colitis', 'autoimmune', 'rheumatoid']
            },
            'depression': {
                'primary': ['depression', 'depressive', 'major depressive', 'unipolar', 'mood disorder'],
                'secondary': ['anhedonia', 'dysthymia', 'melancholia'],
                'comorbid': ['anxiety', 'bipolar', 'substance', 'sleep', 'adhd'],
                'pharmacogenomic': ['ssri', 'snri', 'cyp2d6', 'cyp2c19', 'serotonin'],
                'exclude': ['cancer', 'tumor', 'malignant', 'lipid', 'metabolite']
            },
            'anxiety': {
                'primary': ['anxiety', 'anxious', 'panic', 'phobia', 'generalized anxiety'],
                'secondary': ['worry', 'fear', 'social anxiety'],
                'comorbid': ['depression', 'adhd', 'substance'],
                'pharmacogenomic': ['benzodiazepine', 'ssri', 'gaba'],
                'exclude': ['cancer', 'tumor', 'malignant', 'lipid', 'metabolite']
            },
            # Simplified structure for other conditions
            'autism': ['autism', 'autistic', 'asd', 'asperger', 'pervasive developmental'],
            'bipolar': ['bipolar', 'manic', 'mania', 'mood disorder'],
            'schizophrenia': ['schizophrenia', 'psychotic', 'psychosis'],
            'alzheimer': ['alzheimer', 'dementia', 'cognitive decline'],
            'diabetes': ['diabetes', 'diabetic', 'glucose', 'insulin'],
            'cardiovascular': ['cardiovascular', 'heart', 'cardiac', 'coronary', 'hypertension'],
            'cancer': ['cancer', 'tumor', 'carcinoma', 'malignant', 'oncology']
        }
        
        # Determine relevant keywords and exclusions based on condition focus
        relevant_keywords = []
        exclude_keywords = []
        
        for condition, keywords in condition_keywords.items():
            if condition in focus_lower:
                if isinstance(keywords, dict):
                    # Enhanced structure with tiers
                    relevant_keywords.extend(keywords.get('primary', []))
                    relevant_keywords.extend(keywords.get('secondary', []))
                    relevant_keywords.extend(keywords.get('comorbid', []))
                    relevant_keywords.extend(keywords.get('pharmacogenomic', []))
                    exclude_keywords.extend(keywords.get('exclude', []))
                else:
                    # Simple list structure
                    relevant_keywords.extend(keywords)
        
        # If no specific keywords found, use the focus terms directly
        if not relevant_keywords:
            relevant_keywords = [word.strip() for word in focus_lower.split() if len(word) > 3]
        
        # Filter GWAS data with enhanced relevance checking and exclusions
        if isinstance(gwas_data, str):
            # If it's a string, try to parse it or filter line by line
            lines = gwas_data.split('\n')
            filtered_lines = []
            
            for line in lines:
                line_lower = line.lower()
                
                # Skip if contains exclusion keywords
                if exclude_keywords and any(exclude_keyword in line_lower for exclude_keyword in exclude_keywords):
                    continue
                
                # Check if line contains any relevant keywords
                if any(keyword in line_lower for keyword in relevant_keywords):
                    filtered_lines.append(line)
            
            return '\n'.join(filtered_lines) if filtered_lines else "No GWAS associations relevant to the condition focus were identified."
        
        return gwas_data

    def _prepare_block_data(self, block_type: BlockType, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare block-specific data dictionary based on block type requirements.
        
        Args:
            block_type: Type of block being generated
            data: Base data dictionary containing all available information
            
        Returns:
            Dictionary with block-specific placeholder mappings
        """
        # Build progressive summaries from previous blocks
        previous_summaries = self._build_progressive_summaries(block_type, data)
        
        # Common fields for all blocks
        block_data = {
            "PROMPT": data.get("prompt", ""),
            "PREVIOUS_TEXT": data.get("previous_text", ""),
            "FEEDBACK": data.get("feedback", ""),
            "PREVIOUS_BLOCK_SUMMARIES": previous_summaries,
            "MUTATED_PROTEINS": data.get("MUTATED_PROTEINS", ""),
            "PROTEIN_DISEASES": data.get("PROTEIN_DISEASES", ""),
            "PROTEIN_MUTATIONS": data.get("PROTEIN_MUTATIONS", ""),
            "PROTEIN_DISEASE_MUTATIONS": data.get("PROTEIN_DISEASE_MUTATIONS", ""),
            "FAMILY_HISTORY": data.get("FAMILY_HISTORY", data.get("family_history", "")),
            "DEMOGRAPHICS": data.get("DEMOGRAPHICS", data.get("demographics", "")),
            "GWAS_ASSOCIATIONS": self._filter_relevant_gwas(data.get("GWAS_ASSOCIATIONS", ""), data.get("prompt", "")),
            "GENESOFINTEREST": data.get("GENESOFINTEREST", data.get("genes_of_interest", "")),
            "VARIANTS": data.get("VARIANTS", data.get("variants", "")),
            
        }
        
        # Add enhanced dual section data for supported block types
        if block_type in [BlockType.RISK_ASSESSMENT, BlockType.CLINICAL_IMPLICATIONS, 
                         BlockType.MUTATION_PROFILE, BlockType.LITERATURE_EVIDENCE]:
            block_data.update(self._prepare_dual_section_data(data))
        
        # Block-specific data mappings
        if block_type == BlockType.EXECUTIVE_SUMMARY:
            block_data.update({
                "DISEASEGENES": data.get("DISEASE_GENES", data.get("disease_genes", "")),
                "FAMILYHISTORY": data.get("FAMILY_HISTORY", data.get("family_history", "")),
                "DEMOGRAPHICS": data.get("DEMOGRAPHICS", data.get("demographics", "")),
            })
            
        elif block_type == BlockType.INTRODUCTION:
            block_data.update({
                "DISEASEFOCUS": data.get("prompt", ""),
                "REPORTTYPE": data.get("report_type", ""),
                "PROVIDER": data.get("provider", "")
            })
            
        elif block_type == BlockType.MUTATION_PROFILE:
            block_data.update({
                "DISEASEGENES": data.get("DISEASE_GENES", data.get("disease_genes", "")),
                "VARIANTDATA": data.get("VARIANT_DATA", data.get("variant_data", "")),
                "RSIDS": data.get("RSIDS", data.get("rs_ids", "")),
                "PROTEINMUTATIONS": data.get("PROTEIN_MUTATIONS", data.get("protein_mutations", "")),
                "FAMILYHISTORY": data.get("FAMILY_HISTORY", data.get("family_history", ""))
            })
            
        elif block_type == BlockType.CLINICAL_IMPLICATIONS:
            block_data.update({
                "DISEASEGENES": data.get("disease_genes", ""),
                "FAMILYHISTORY": data.get("family_history", ""),
                "MEDICATIONS": data.get("medications", "")
            })
            
        elif block_type == BlockType.RISK_ASSESSMENT:
            block_data.update({
                "DISEASEGENES": data.get("disease_genes", ""),
                "POLYGENICSCORES": data.get("polygenic_scores", ""),
                "FAMILYHISTORY": data.get("family_history", ""),
                "ENVIRONMENTALFACTORS": data.get("environmental_factors", ""),
                "LIFESTYLEFACTORS": data.get("lifestyle_factors", ""),
                "CLINICALHISTORY": data.get("clinical_history", "")
            })
            
        elif block_type == BlockType.LIFESTYLE_RECOMMENDATIONS:
            block_data.update({
                "DISEASEGENES": data.get("disease_genes", ""),
                "HEALTHSTATUS": data.get("health_status", ""),
                "FAMILYHISTORY": data.get("family_history", ""),
                "CURRENTLIFESTYLE": data.get("current_lifestyle", ""),
                "ENVIRONMENTALEXPOSURES": data.get("environmental_exposures", "")
            })
            # VARIANTS already included in common fields
            
        elif block_type == BlockType.LITERATURE_EVIDENCE:
            block_data.update({
                "DISEASEGENES": data.get("disease_genes", ""),
                "GENES": data.get("genes", ""),
                "PROTEINMUTATIONS": data.get("protein_mutations", ""),
                "DISEASEFOCUS": data.get("disease_focus", ""),
                "VARIANTDATA": data.get("variant_data", "")
            })
            
        elif block_type == BlockType.MONITORING_PLAN:
            block_data.update({
                "DISEASEGENES": data.get("PROTEIN_DISEASES", ""),
                "RISKLEVEL": data.get("risk_level", ""),
                "HEALTHSTATUS": data.get("health_status", ""),
                "FAMILYHISTORY": data.get("family_history", ""),
                "AGE": data.get("age", ""),
                "CLINICALHISTORY": data.get("clinical_history", "")
            })
            # VARIANTS already included in common fields
            
        elif block_type == BlockType.RESEARCH_OPPORTUNITIES:
            block_data.update({
                "DISEASEGENES": data.get("PROTEIN_DISEASES", ""),
                "CONDITIONS": data.get("conditions", ""),
                "DISEASEFOCUS": data.get("disease_focus", ""),
                "DEMOGRAPHICS": data.get("demographics", "")
            })
            # VARIANTS already included in common fields
            
        elif block_type.value == 'gwas_analysis':
            block_data.update({
                "DISEASEGENES": data.get("PROTEIN_DISEASES", ""),
                "VARIANTDATA": data.get("variant_data", ""),
                "PROTEINMUTATIONS": data.get("protein_mutations", ""),
                "DISEASEFOCUS": data.get("disease_focus", "")
            })
            
        return block_data
    
    def _prepare_dual_section_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare dual section configuration data for enhanced block generators
        
        Args:
            data: Original data dictionary
            
        Returns:
            Dictionary with dual section configuration
        """
        dual_section_data = {}
        
        # Extract variant classification data if available
        all_risk_variants = data.get('risk_variants', [])
        all_protective_variants = data.get('protective_variants', [])
        
        # Limit number of variants sent to LLM for processing efficiency
        # But keep the full lists for counts
        risk_variants = all_risk_variants[:50]
        protective_variants = all_protective_variants[:50]
        
        # Determine section visibility
        show_risk_section = len(all_risk_variants) > 0
        show_protective_section = len(all_protective_variants) > 0
        
        # Add dual section configuration
        dual_section_data.update({
            'RISK_VARIANTS': self._format_variants_for_template(risk_variants),
            'PROTECTIVE_VARIANTS': self._format_variants_for_template(protective_variants),
            'SHOW_RISK_SECTION': str(show_risk_section).lower(),
            'SHOW_PROTECTIVE_SECTION': str(show_protective_section).lower(),
            'SECTION_CONFIG': {
                'risk_count': len(all_risk_variants),
                'protective_count': len(all_protective_variants),
                'has_both_types': show_risk_section and show_protective_section
            }
        })
        
        return dual_section_data
    
    def _format_variants_for_template(self, variants: List) -> str:
        """
        Format variant data for template consumption, including verified data.
        
        Args:
            variants: List of variant objects or dictionaries
            
        Returns:
            Formatted string representation of variants with verified data
        """
        if not variants:
            return "No variants of this type identified"
        
        formatted_variants = []
        for variant in variants:
            if isinstance(variant, dict):
                gene = variant.get('gene', 'Unknown')
                effect = variant.get('effect_direction', 'Unknown')
                sig = variant.get('clinical_significance', 'Unknown')
                strength = variant.get('evidence_strength', 'Unknown')
                risk = variant.get('absolute_risk_range', 'Unknown')
                pop = variant.get('population_risk', 'Unknown')
                tier = variant.get('risk_tier', 'Unknown')
                # Verified data fields
                protein_id = variant.get('protein_id', None)
                hgvs = variant.get('hgvs', variant.get('rsid', 'Unknown'))
                ref_aa = variant.get('ref_amino_acid', None)
                alt_aa = variant.get('alt_amino_acid', None)
                aa_pos = variant.get('amino_acid_position', None)
                score = variant.get('score', None)
                
                # Build variant description from verified data
                variant_desc = hgvs
                if ref_aa and alt_aa and aa_pos:
                    variant_desc = f"p.{ref_aa}{aa_pos}{alt_aa}"
                
                protein_str = f"Protein: {protein_id}" if protein_id else ""
                score_str = f"Score: {score:.3f}" if score else ""
                
                info = f"Gene: {gene} | {protein_str} | Variant: {variant_desc} | HGVS: {hgvs} | Effect: {effect} | Significance: {sig} | Evidence: {strength} | {score_str} | AbsRisk: {risk} | PopRisk: {pop} | Tier: {tier}"
                formatted_variants.append(info)
            else:
                # Handle variant objects with attributes — use __str__ for verified data
                try:
                    # Use the __str__ method which outputs verified data
                    info = str(variant)
                    formatted_variants.append(info)
                except Exception as e:
                    logger.warning(f"Error formatting variant object: {e}")
                    formatted_variants.append(str(variant))
        
        return "; ".join(formatted_variants)

    def _get_block_title(self, block_type: BlockType) -> str:
        """Get human-readable title for block type."""
        title_map = {
            BlockType.INTRODUCTION: "Introduction",
            BlockType.EXECUTIVE_SUMMARY: "Executive Summary",
            BlockType.MUTATION_PROFILE: "Genetic Profile",
            BlockType.LITERATURE_EVIDENCE: "Literature Evidence",
            BlockType.RISK_ASSESSMENT: "Risk Assessment",
            BlockType.CLINICAL_IMPLICATIONS: "Clinical Implications",
            BlockType.LIFESTYLE_RECOMMENDATIONS: "Lifestyle Recommendations",
            BlockType.MONITORING_PLAN: "Monitoring Plan",
            BlockType.RESEARCH_OPPORTUNITIES: "Research Opportunities",
            BlockType.GWAS_ANALYSIS: "GWAS Analysis",
            BlockType.CONCLUSION: "Conclusion"
        }
        return title_map.get(block_type, block_type.value.replace('_', ' ').title())

    def _get_block_order(self, block_type: BlockType) -> int:
        """Get display order for block type."""
        order_map = {
            BlockType.INTRODUCTION: 1,
            BlockType.EXECUTIVE_SUMMARY: 2,
            BlockType.LIFESTYLE_RECOMMENDATIONS: 3,
            BlockType.MONITORING_PLAN: 4,
            BlockType.CLINICAL_IMPLICATIONS: 5,
            BlockType.RISK_ASSESSMENT: 6,
            BlockType.MUTATION_PROFILE: 7,
            BlockType.LITERATURE_EVIDENCE: 8,
            BlockType.RESEARCH_OPPORTUNITIES: 9,
            BlockType.GWAS_ANALYSIS: 10,
            BlockType.CONCLUSION: 11
        }
        return order_map.get(block_type, 99)

    def _build_progressive_summaries(self, block_type: BlockType, data: Dict[str, Any]) -> str:
        """
        Build progressive summaries from previous blocks for context.
        
        Args:
            block_type: Current block type being generated
            data: Data dictionary containing previous block information
            
        Returns:
            String containing summaries of previous blocks
        """
        # This is a placeholder implementation - in a full system this would
        # track summaries from previously generated blocks
        previous_summaries = data.get('previous_block_summaries', '')
        if not previous_summaries:
            return "This is the first section of the report."
        return previous_summaries
    
    def _filter_relevant_gwas(self, gwas_data: str, prompt: str) -> str:
        """
        Filter GWAS associations relevant to the report prompt.
        
        Args:
            gwas_data: Raw GWAS association data
            prompt: Report focus/prompt
            
        Returns:
            Filtered GWAS data relevant to the prompt
        """
        if not gwas_data or not prompt:
            return gwas_data
        
        # Simple filtering based on prompt keywords
        # In a full implementation, this would be more sophisticated
        prompt_keywords = prompt.lower().split()
        relevant_lines = []
        
        for line in gwas_data.split('\n'):
            if any(keyword in line.lower() for keyword in prompt_keywords):
                relevant_lines.append(line)
        
        return '\n'.join(relevant_lines) if relevant_lines else gwas_data
    
    def _create_error_block(self, block_type: BlockType, error_message: str) -> ReportBlock:
        """Create an error block when generation fails."""
        # Create a formatted error message as a string instead of a dictionary
        error_content = f"""
# Error Generating {self._get_block_title(block_type)}

**An error occurred while generating this section:**

{error_message}

---
*This section will be regenerated on the next attempt.*
"""
        return ReportBlock(
            block_type=block_type,
            title=self._get_block_title(block_type),
            content=error_content,  # Use string content instead of dictionary
            template=f"{block_type.value}_block.html",
            order=self._get_block_order(block_type)
        )