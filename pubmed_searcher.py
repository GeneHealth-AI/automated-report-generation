from Bio import Entrez
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class PubMedSearcher:
    """
    Robust utility to search PubMed for RAG contexts in the legacy codebase.
    Updated to use Bio.Entrez for better parsing and rate limit handling.
    """
    
    def __init__(self, email: str = "genehealth-ai@example.com", api_key: Optional[str] = None):
        """
        Initialize the searcher.
        NCBI requires an email. 
        """
        Entrez.email = email
        if api_key:
            Entrez.api_key = api_key
            
    def search_pmids(self, query: str, retmax: int = 5) -> List[str]:
        """Search PubMed and return a list of PMIDs."""
        try:
            logger.info(f"Searching PubMed for: {query}")
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
        Handles structured abstracts and title extraction robustly.
        """
        if not pmids:
            return []
            
        try:
            handle = Entrez.efetch(db="pubmed", id=pmids, retmode="xml")
            articles = Entrez.read(handle)
            handle.close()
            
            results: List[Dict[str, str]] = []
            pubmed_articles = articles.get("PubmedArticle", [])
            
            for article in pubmed_articles:
                medline = article["MedlineCitation"]
                article_data = medline["Article"]
                
                title = article_data.get("ArticleTitle", "No title")
                
                abstract_text = ""
                if "Abstract" in article_data and "AbstractText" in article_data["Abstract"]:
                    abstract_parts = article_data["Abstract"]["AbstractText"]
                    
                    if isinstance(abstract_parts, list):
                        for part in abstract_parts:
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
                    "abstract": abstract_text.strip() or "No abstract available."
                })
                
            return results
            
        except Exception as e:
            logger.error(f"Error fetching details from PubMed: {e}")
            return []

    def get_evidence(self, query: str, retmax: int = 3) -> str:
        """
        Pipeline: Search -> Fetch -> Format String.
        Maintains legacy interface name but uses modernized logic.
        """
        pmids = self.search_pmids(query, retmax=retmax)
        if not pmids:
            return "No relevant research found."
            
        data = self.fetch_details(pmids)
        
        formatted_docs = []
        for doc in data:
            entry = (
                f"PMID: {doc['pmid']}\n"
                f"TITLE: {doc['title']}\n"
                f"ABSTRACT: {doc['abstract']}"
            )
            formatted_docs.append(entry)
            
        return "\n\n---\n\n".join(formatted_docs)
