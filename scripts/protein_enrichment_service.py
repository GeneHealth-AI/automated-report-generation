"""
Protein Enrichment Service for structured protein analysis.

This module provides the ProteinEnrichmentService class that integrates with
existing np_full_info data to enrich protein information with context from
UniProt and other sources.
"""

import os
import csv
import logging
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from functools import lru_cache
import time

from structured_protein_models import (
    EnrichedProtein, UniProtData, MutationInfo, 
    GWASAssociation, KnowgeneAssociation
)

logger = logging.getLogger(__name__)


@dataclass
class ProteinContext:
    """Context information for a single protein."""
    protein_id: str
    gene_name: str
    function: str
    disease_associations: List[str]
    uniprot_data: Optional[UniProtData] = None
    has_data: bool = True


class ProteinEnrichmentService:
    """
    Service for enriching protein information with context from UniProt and other sources.
    
    This service integrates with the existing np_full_info data structure to provide
    comprehensive protein context including function, disease associations, and
    UniProt metadata.
    """
    
    def __init__(self, np_full_info_path: str = "np_full_info"):
        """
        Initialize the protein enrichment service.
        
        Args:
            np_full_info_path: Path to the np_full_info directory
        """
        self.np_full_info_path = np_full_info_path
        self._protein_cache: Dict[str, ProteinContext] = {}
        self._uniprot_mapping: Dict[str, str] = {}
        self._essential_proteins: Dict[str, Dict[str, str]] = {}
        self._cache_loaded = False
        
        # Load data on initialization
        self._load_data()
    
    def _load_data(self) -> None:
        """Load protein data from np_full_info files."""
        try:
            self._load_uniprot_mapping()
            self._load_essential_proteins()
            self._cache_loaded = True
            logger.info(f"Loaded protein data: {len(self._uniprot_mapping)} mappings, "
                       f"{len(self._essential_proteins)} essential proteins")
        except Exception as e:
            logger.error(f"Failed to load protein data: {e}")
            self._cache_loaded = False
    
    def _load_uniprot_mapping(self) -> None:
        """Load NP to UniProt mapping from file."""
        mapping_file = os.path.join(self.np_full_info_path, "uniprot", "np_to_uniprot_mapping.tsv")
        
        if not os.path.exists(mapping_file):
            logger.warning(f"UniProt mapping file not found: {mapping_file}")
            return
        
        try:
            with open(mapping_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and '\t' in line:
                        parts = line.split('\t')
                        if len(parts) >= 2:
                            np_id = parts[0].strip()
                            uniprot_id = parts[1].strip()
                            self._uniprot_mapping[np_id] = uniprot_id
            
            logger.info(f"Loaded {len(self._uniprot_mapping)} UniProt mappings")
        except Exception as e:
            logger.error(f"Error loading UniProt mapping: {e}")
    
    def _load_essential_proteins(self) -> None:
        """Load essential protein information from file."""
        essential_file = os.path.join(self.np_full_info_path, "uniprot", "human_proteins_essential.tsv")
        
        if not os.path.exists(essential_file):
            logger.warning(f"Essential proteins file not found: {essential_file}")
            return
        
        try:
            with open(essential_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter='\t')
                for row in reader:
                    # Extract NP IDs from RefSeq_IDs field
                    refseq_ids = row.get('RefSeq_IDs', '').strip()
                    if refseq_ids:
                        # Split by semicolon and extract NP IDs
                        for refseq_id in refseq_ids.split(';'):
                            refseq_id = refseq_id.strip()
                            # Remove any bracketed information like [A0A0K2S4Q6-1]
                            if '[' in refseq_id:
                                refseq_id = refseq_id.split('[')[0].strip()
                            
                            if refseq_id.startswith('NP_'):
                                # Remove version number for consistent lookup
                                np_id = refseq_id.split('.')[0] if '.' in refseq_id else refseq_id
                                
                                # Extract gene name from Gene_Names field (it's actually the gene symbol)
                                gene_names = row.get('Gene_Names', '').strip()
                                # The gene name is typically the last part after spaces
                                gene_name = gene_names.split()[-1] if gene_names else 'Unknown'
                                
                                self._essential_proteins[np_id] = {
                                    'uniprot_accession': row.get('UniProt_Accession', ''),
                                    'protein_name': row.get('Protein_Name', ''),
                                    'gene_names': gene_name,  # Use extracted gene name
                                    'function': row.get('Function', ''),
                                    'disease': row.get('Disease', ''),
                                    'go_terms': row.get('GO_Terms', ''),
                                    'domains': row.get('Domains', ''),
                                    'full_refseq_id': refseq_id
                                }
            
            logger.info(f"Loaded {len(self._essential_proteins)} essential protein entries")
        except Exception as e:
            logger.error(f"Error loading essential proteins: {e}")
    
    @lru_cache(maxsize=1000)
    def get_protein_context(self, protein_id: str) -> ProteinContext:
        """
        Get comprehensive context for a single protein.
        
        Args:
            protein_id: NP_ accession ID (with or without version)
            
        Returns:
            ProteinContext object with available information
        """
        # Normalize protein ID (remove version if present)
        base_protein_id = protein_id.split('.')[0] if '.' in protein_id else protein_id
        
        # Check cache first
        if protein_id in self._protein_cache:
            return self._protein_cache[protein_id]
        
        # Initialize context with defaults
        context = ProteinContext(
            protein_id=protein_id,
            gene_name="Unknown",
            function="Function not available",
            disease_associations=[],
            uniprot_data=None,
            has_data=False
        )
        
        # Try to get data from essential proteins
        if base_protein_id in self._essential_proteins:
            protein_data = self._essential_proteins[base_protein_id]
            
            # Get gene name (already processed during loading)
            gene_name = protein_data.get('gene_names', 'Unknown')
            context.gene_name = gene_name if gene_name != 'Unknown' else "Unknown"
            
            # Set function
            function = protein_data.get('function', '')
            if function and function.strip():
                context.function = function.strip()
            
            # Parse disease associations
            disease = protein_data.get('disease', '')
            if disease and disease.strip():
                # Split disease text into individual associations
                disease_list = self._parse_disease_text(disease)
                context.disease_associations = disease_list
            
            # Create UniProt data if available
            uniprot_acc = protein_data.get('uniprot_accession', '')
            if uniprot_acc:
                context.uniprot_data = UniProtData(
                    accession=uniprot_acc,
                    name=protein_data.get('protein_name', ''),
                    gene_name=context.gene_name,
                    function=context.function,
                    go_terms=protein_data.get('go_terms', ''),
                    domains=protein_data.get('domains', ''),
                    organism="Homo sapiens"
                )
            
            context.has_data = True
            logger.debug(f"Found context for protein {protein_id}: {context.gene_name}")
        
        else:
            # Try fallback with UniProt mapping
            if base_protein_id in self._uniprot_mapping:
                uniprot_id = self._uniprot_mapping[base_protein_id]
                context.uniprot_data = UniProtData(
                    accession=uniprot_id,
                    name="Unknown",
                    gene_name="Unknown",
                    function="Function not available",
                    organism="Homo sapiens"
                )
                context.has_data = True
                logger.debug(f"Found UniProt mapping for protein {protein_id}: {uniprot_id}")
            else:
                logger.warning(f"No data found for protein {protein_id}")
        
        # Cache the result
        self._protein_cache[protein_id] = context
        return context
    
    def _parse_disease_text(self, disease_text: str) -> List[str]:
        """
        Parse disease text from UniProt format into individual disease names.
        
        Args:
            disease_text: Raw disease text from UniProt
            
        Returns:
            List of individual disease names
        """
        diseases = []
        
        if not disease_text or not disease_text.strip():
            return diseases
        
        # Split by common delimiters and clean up
        # UniProt disease format often contains detailed descriptions
        # We'll extract the main disease names
        
        # Look for disease names in parentheses or after colons
        import re
        
        # Pattern to match disease names in format "Disease name (ABBR) [MIM:123456]:"
        disease_pattern = r'([A-Z][^(:\[]+?)(?:\s*\([^)]*\))?\s*(?:\[MIM:[^\]]*\])?\s*:'
        matches = re.findall(disease_pattern, disease_text)
        
        for match in matches:
            disease_name = match.strip()
            if disease_name and len(disease_name) > 2:  # Filter out very short matches
                diseases.append(disease_name)
        
        # If no structured matches found, try simpler splitting
        if not diseases:
            # Split by periods or semicolons and take first few words
            parts = re.split(r'[.;]', disease_text)
            for part in parts[:3]:  # Limit to first 3 parts
                part = part.strip()
                if part and len(part) > 10:  # Only take substantial text
                    # Extract first sentence or clause
                    first_sentence = part.split('.')[0].strip()
                    if first_sentence:
                        diseases.append(first_sentence)
        
        return diseases[:5]  # Limit to 5 diseases to avoid overwhelming output
    
    def enrich_proteins(self, proteins: List[str], 
                       mutations: Optional[Dict[str, List[MutationInfo]]] = None,
                       gwas_associations: Optional[Dict[str, List[GWASAssociation]]] = None,
                       knowgene_associations: Optional[Dict[str, List[KnowgeneAssociation]]] = None) -> Dict[str, EnrichedProtein]:
        """
        Add context information from UniProt and other sources to a list of proteins.
        
        Args:
            proteins: List of NP_ protein IDs
            mutations: Optional dictionary mapping protein IDs to mutation lists
            gwas_associations: Optional dictionary mapping protein IDs to GWAS associations
            knowgene_associations: Optional dictionary mapping protein IDs to knowgene associations
            
        Returns:
            Dictionary mapping protein IDs to EnrichedProtein objects
        """
        if not self._cache_loaded:
            logger.warning("Protein data not loaded, attempting to reload...")
            self._load_data()
        
        enriched_proteins = {}
        
        for protein_id in proteins:
            try:
                # Get protein context
                context = self.get_protein_context(protein_id)
                
                # Create enriched protein object
                enriched_protein = EnrichedProtein(
                    protein_id=protein_id,
                    gene_name=context.gene_name,
                    function=context.function,
                    disease_associations=context.disease_associations,
                    mutations=mutations.get(protein_id, []) if mutations else [],
                    gwas_associations=gwas_associations.get(protein_id, []) if gwas_associations else [],
                    knowgene_associations=knowgene_associations.get(protein_id, []) if knowgene_associations else [],
                    uniprot_data=context.uniprot_data
                )
                
                enriched_proteins[protein_id] = enriched_protein
                
            except Exception as e:
                logger.error(f"Error enriching protein {protein_id}: {e}")
                # Create minimal enriched protein for failed cases
                enriched_proteins[protein_id] = EnrichedProtein(
                    protein_id=protein_id,
                    gene_name="Unknown",
                    function="Function not available",
                    disease_associations=[],
                    mutations=mutations.get(protein_id, []) if mutations else [],
                    gwas_associations=gwas_associations.get(protein_id, []) if gwas_associations else [],
                    knowgene_associations=knowgene_associations.get(protein_id, []) if knowgene_associations else []
                )
        
        logger.info(f"Enriched {len(enriched_proteins)} proteins")
        return enriched_proteins
    
    def get_available_proteins(self) -> Set[str]:
        """
        Get set of all available protein IDs that have enrichment data.
        
        Returns:
            Set of NP_ protein IDs with available data
        """
        return set(self._essential_proteins.keys()) | set(self._uniprot_mapping.keys())
    
    def get_cache_stats(self) -> Dict[str, int]:
        """
        Get statistics about the loaded data and cache.
        
        Returns:
            Dictionary with cache statistics
        """
        return {
            "uniprot_mappings": len(self._uniprot_mapping),
            "essential_proteins": len(self._essential_proteins),
            "cached_contexts": len(self._protein_cache),
            "cache_loaded": self._cache_loaded
        }
    
    def clear_cache(self) -> None:
        """Clear the protein context cache."""
        self._protein_cache.clear()
        # Clear the LRU cache
        self.get_protein_context.cache_clear()
        logger.info("Protein context cache cleared")
    
    def reload_data(self) -> None:
        """Reload protein data from files."""
        self.clear_cache()
        self._uniprot_mapping.clear()
        self._essential_proteins.clear()
        self._load_data()
        logger.info("Protein data reloaded")


# Utility functions for working with the enrichment service

def create_enrichment_service(np_full_info_path: str = "np_full_info") -> ProteinEnrichmentService:
    """
    Factory function to create a ProteinEnrichmentService instance.
    
    Args:
        np_full_info_path: Path to the np_full_info directory
        
    Returns:
        Configured ProteinEnrichmentService instance
    """
    return ProteinEnrichmentService(np_full_info_path)


def validate_protein_ids(protein_ids: List[str]) -> List[str]:
    """
    Validate and normalize protein IDs.
    
    Args:
        protein_ids: List of protein IDs to validate
        
    Returns:
        List of validated and normalized protein IDs
    """
    validated_ids = []
    
    for protein_id in protein_ids:
        if not protein_id:
            continue
            
        # Normalize the ID
        normalized_id = protein_id.strip()
        
        # Check if it looks like an NP_ accession
        if normalized_id.startswith('NP_'):
            validated_ids.append(normalized_id)
        else:
            logger.warning(f"Invalid protein ID format: {protein_id}")
    
    return validated_ids