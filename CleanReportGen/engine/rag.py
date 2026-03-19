from Bio import Entrez
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class PubMedRAG:
    """
    Robust utility to search PubMed for RAG contexts.
    Uses Bio.Entrez to handle rate limiting and XML parsing automatically.
    """
    
    def __init__(self, email: str, api_key: Optional[str] = None):
        # NCBI requires an email. 
        Entrez.email = email
        if api_key:
            Entrez.api_key = api_key
            
    def search_pmids(self, query: str, retmax: int = 20) -> List[str]:
        """Search PubMed and return a list of PMIDs."""
        try:
            logger.info(f"Searching: {query}")
            # Use 'esearch' to get IDs
            handle = Entrez.esearch(db="pubmed", term=query, retmax=retmax, retmode="xml")
            record = Entrez.read(handle)
            handle.close()
            
            id_list = record.get("IdList", [])
            logger.info(f"Found {len(id_list)} articles.")
            return id_list
            
        except Exception as e:
            logger.error(f"PubMed search failed: {e}")
            return []

    def fetch_details(self, pmids: List[str]) -> List[Dict[str, str]]:
        """
        Fetch full details for PMIDs. 
        Uses POST automatically to handle large lists of IDs.
        """
        if not pmids:
            return []
            
        try:
            # efetch allows us to grab the full metadata
            # We use retmode='xml' to get a structured dictionary back
            handle = Entrez.efetch(db="pubmed", id=pmids, retmode="xml")
            articles = Entrez.read(handle)
            handle.close()
            
            results: List[Dict[str, str]] = []
            
            # Entrez.read returns a dict; we access the list of PubmedArticle
            pubmed_articles = articles.get("PubmedArticle", [])
            
            for article in pubmed_articles:
                medline = article["MedlineCitation"]
                article_data = medline["Article"]
                
                # 1. robust title extraction
                title = article_data.get("ArticleTitle", "No title")
                
                # 2. robust abstract extraction (handling structured abstracts)
                abstract_text = ""
                if "Abstract" in article_data and "AbstractText" in article_data["Abstract"]:
                    # AbstractText can be a list (structured) or string (unstructured)
                    abstract_parts = article_data["Abstract"]["AbstractText"]
                    
                    if isinstance(abstract_parts, list):
                        # It's structured (e.g., Background, Methods, Results)
                        for part in abstract_parts:
                            # Attributes like 'Label' (e.g., "METHODS") are in .attributes
                            label = part.attributes.get("Label", "")
                            text = str(part)
                            if label:
                                abstract_text += f"{label}: {text}\n"
                            else:
                                abstract_text += f"{text}\n"
                    else:
                        abstract_text = str(abstract_parts)
                    results.append({
                    "pmid": str(medline["PMID"]),
                    "title": title,
                    "abstract": abstract_text.strip()
                     })

                
                
            return results
            
        except Exception as e:
            logger.error(f"Error fetching details: {e}")
            return []

    def get_evidence_context(self, query: str, retmax: int = 10) -> str:
        """Pipeline: Search -> Fetch -> Format String"""
        pmids = self.search_pmids(query, retmax=retmax)
        if not pmids:
            return "No relevant research found."
            
        data = self.fetch_details(pmids)
        
        # Format for LLM ingestion
        formatted_docs = []
        for doc in data:
            entry = (
                f"DOCUMENT_ID: {doc['pmid']}\n"
                f"TITLE: {doc['title']}\n"
                f"ABSTRACT:\n{doc['abstract']}"
            )
            formatted_docs.append(entry)
            
        return "\n\n---\n\n".join(formatted_docs)