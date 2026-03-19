import logging
import os
from mutation_cache_manager import MutationCacheManager
# Importing generate_gemini_response from block_generator where it is defined
from block_generator import generate_gemini_response

logger = logging.getLogger(__name__)

class MutationDescriptionGenerator:
    """
    Generates rich descriptions for genetic mutations using an LLM,
    with caching to ensure consistency and performance.
    """
    
    def __init__(self, cache_db_path: str = "mutation_cache.db"):
        self.cache = MutationCacheManager(cache_db_path)
        self.model_version = "v1-gemini-3-flash-preview" 

    def generate_description(self, gene: str, ref_aa: str, position: str, alt_aa: str, diseases: str) -> str:
        """
        Generate (or retrieve cached) description for a specific mutation.
        
        Args:
            gene: Gene symbol (e.g., "TP53")
            ref_aa: Reference amino acid (e.g., "Arg" or "R")
            position: Amino acid position (e.g., "248")
            alt_aa: Alternate amino acid (e.g., "Gln" or "Q")
            diseases: Associated diseases string
            
        Returns:
            A rich text description of the mutation's potential impact.
        """
        # Create a deterministic signature
        signature = f"{gene}:P.{ref_aa}{position}{alt_aa}"
        
        # 1. Check Cache
        cached_text = self.cache.get_description(signature)
        if cached_text:
            logger.info(f"Cache hit for {signature}")
            return cached_text
            
        logger.info(f"Cache miss for {signature}. Generating description...")
        
        # 2. Construct Prompt
        prompt = f"""
        Provide a concise but clinical description for the genetic mutation: {gene} p.{ref_aa}{position}{alt_aa}.
        Context:
        - Gene: {gene}
        - Change: {ref_aa} to {alt_aa} at position {position}
        - Associated Disease(s): {diseases}
        
        Focus on:
        1. Whether this position is in a critical domain.
        2. Potential functional impact (e.g., gain/loss of function, stability).
        3. Clinical significance if known (pathogenic vs VUS).
        
        Format as a single paragraph, suitable for a medical report. Do not use bullet points. 
        Keep it under 80 words.
        """
        
        try:
            system_prompt = "You are an expert clinical geneticist assistant. Provide precise, evidence-based summaries of genetic variants."
        
            # 3. Call LLM
            # Using a relatively low max_tokens since we want short descriptions
            logger.info(f"🔧 DEBUG: Prompt length for mutation description: {len(prompt)} characters")
            description = generate_gemini_response(prompt, system_prompt, max_tokens=256)
                
            # Clean up response (trim whitespace)
            description = description.strip()
            
            # 4. Cache Result
            self.cache.cache_description(signature, description, self.model_version)
            
            return description
            
        except Exception as e:
            logger.error(f"Error generating description for {signature}: {e}")
            return f"Mutation {gene} {ref_aa}{position}{alt_aa} detected. (Automated description generation failed)."
