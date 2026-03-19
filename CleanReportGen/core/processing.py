import re
import requests
import logging
from typing import List, Tuple, Union, Optional, Iterable, Any
from Bio import Entrez

logger = logging.getLogger(__name__)

def parse_vcf(vcf_path: str) -> List[Tuple[str, str]]:
    """Parse a VCF file and return a list of (HGVS, ALT_ALLELE) pairs."""
    import os
    variants = []
    logger.info(f"Parsing VCF: {vcf_path}")
    
    try:
        if not os.path.exists(vcf_path):
            logger.error(f"VCF file not found: {vcf_path}")
            return []

        with open(vcf_path, 'r') as f:
            for line in f:
                if line.startswith('#'):
                    continue
                
                parts = line.strip().split('\t')
                if len(parts) < 5:
                    continue
                
                chrom = parts[0]
                pos = parts[1]
                ref = parts[3]
                alt = parts[4]
                
                # Simple HGVS-like format: chr1:g.123A>T
                hgvs = f"chr{chrom}:g.{pos}{ref}>{alt}"
                variants.append((hgvs, alt))
                
        logger.info(f"Found {len(variants)} variants in VCF.")
        return variants
        
    except Exception as e:
        logger.error(f"Error parsing VCF: {e}")
        return []

HGVS_RE = re.compile(r"^chr?(\d+|X|Y|M):g\.\d+[ACGTN]+>[ACGTN]+$", re.I)
VARIANT_RECODER = "https://rest.ensembl.org/variant_recoder/homo_sapiens"
HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}

def normalize_hgvs(var: Union[str, Tuple[str, str]]) -> str:
    """Return upper-case, ‘chr’-stripped HGVS for API calls."""
    if isinstance(var, tuple):
        var = var[0]
    var = var.strip()
    if not HGVS_RE.match(var):
        raise ValueError(f"Unrecognised HGVS format: {var}")
    
    normalized = var.lstrip("chr")
    if ':g.' in normalized:
        chr_part, rest = normalized.split(':g.')
        return f"{chr_part.upper()}:g.{rest.upper()}"
    return normalized

def convert_to_rsid(variants: Iterable[Union[str, Tuple[str, str]]], chunk_size: int = 200) -> List[Tuple[Any, Optional[str]]]:
    """Convert HGVS variants to rsIDs using Ensembl Variant Recoder."""
    original = list(variants)
    try:
        hgvs_list = [normalize_hgvs(v) for v in original]
    except ValueError as e:
        logger.warning(f"Normalization failed: {e}")
        return [(v, None) for v in original]

    rsids = [None] * len(original)
    for i in range(0, len(hgvs_list), chunk_size):
        chunk = hgvs_list[i : i + chunk_size]
        try:
            resp = requests.post(VARIANT_RECODER, json={"ids": chunk}, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            
            for item in data:
                rsid = None
                input_variant = None
                for allele, details in item.items():
                    if isinstance(details, dict) and 'id' in details:
                        rsid = next((vid for vid in details['id'] if vid.startswith('rs')), None)
                        input_variant = details.get('input')
                        break
                
                if rsid and input_variant:
                    try:
                        idx = i + chunk.index(input_variant)
                        rsids[idx] = rsid
                    except ValueError: continue
        except Exception as e:
            logger.error(f"Ensembl API call failed: {e}")
            
    return list(zip(original, rsids))

def get_gene_symbols(np_accessions: List[str], email: str = "sskolusa@gmail.com") -> List[str]:
    """Fetch gene symbols for a list of protein accessions (NP_)."""
    Entrez.email = email
    symbols = []
    for acc in np_accessions:
        try:
            link = Entrez.read(Entrez.elink(dbfrom="protein", db="gene", id=acc))
            gene_id = link[0]["LinkSetDb"][0]["Link"][0]["Id"]
            summary = Entrez.read(Entrez.esummary(db="gene", id=gene_id))
            symbols.append(summary["DocumentSummarySet"]["DocumentSummary"][0]["Name"])
        except Exception: continue
    return symbols

def extract_metadata_from_vcf(vcf_line: str) -> Tuple[Optional[str], Optional[str]]:
    """Simple extraction of position and gene from a VCF/text line."""
    fields = vcf_line.split(",")
    if len(fields) > 3:
        return fields[1], (fields[3], fields[2]) # gene, (pos, chr)
    return None, None
