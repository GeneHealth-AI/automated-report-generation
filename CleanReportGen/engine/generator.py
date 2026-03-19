import logging
import json
import time
import google.generativeai as genai
from typing import Dict, List, Any, Optional, Union
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from data.models import BlockType, ReportBlock
from engine.prompts import BlockTemplate
from utils.cache import MutationCache
from engine.rag import PubMedRAG
from config import GEMINI_API_KEY, RATE_LIMIT_DELAY, DEFAULT_MODEL, PUBMED_EMAIL, PUBMED_API_KEY

logger = logging.getLogger(__name__)

# Configure Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

class BlockGenerationEngine:
    """Core engine for generating report blocks using LLMs."""
    
    def __init__(self, cache_path: Optional[str] = None):
        self.cache = MutationCache(cache_path) if cache_path else None
        self.rag = PubMedRAG(email=PUBMED_EMAIL, api_key=PUBMED_API_KEY)
        self._lock = Lock()
        self._last_call_time = 0

    def _rate_limit(self):
        """Ensure API calls are spaced out."""
        with self._lock:
            elapsed = time.time() - self._last_call_time
            if elapsed < RATE_LIMIT_DELAY:
                time.sleep(RATE_LIMIT_DELAY - elapsed)
            self._last_call_time = time.time()

    def call_llm(self, prompt: str, system_prompt: str, model_name: str = DEFAULT_MODEL) -> str:
        """Rate-limited call to Gemini API."""
        self._rate_limit()
        try:
            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=system_prompt
            )
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise

    def generate_block(self, block_type: BlockType, data: Dict[str, Any]) -> ReportBlock:
        """Generate a single report block."""
        template_config = BlockTemplate.get_template(block_type)
        if not template_config:
            raise ValueError(f"No template found for {block_type}")

        # Special handling for Literature Evidence
        if block_type == BlockType.LITERATURE_EVIDENCE:
            return self._generate_literature_evidence(data)

        # 1. Check cache if applicable
        signature = None
        if self.cache and block_type == BlockType.MUTATION_PROFILE:
            # Simple signature logic for cache
            signature = f"{data.get('category')}_{data.get('mutations_summary')}"
            cached = self.cache.get(signature)
            if cached:
                logger.info(f"Using cached content for {block_type}")
                return ReportBlock(
                    block_type=block_type,
                    title=template_config.get("title", block_type.value.replace("_", " ").title()),
                    content=json.loads(cached) if isinstance(cached, str) and cached.startswith("{") else cached,
                    template=template_config["template"],
                    order=template_config["order"]
                )

        # 2. Prepare prompt
        prompt = template_config["llm_prompt"].format(**data)
        system_prompt = "You are a precision medicine genetics expert. Return only valid JSON."

        # 3. Call LLM
        response_text = self.call_llm(prompt, system_prompt)
        
        # 4. Parse and Clean JSON
        try:
            # Clean possible markdown formatting
            clean_json = re.sub(r"```json\s?|\s?```", "", response_text).strip()
            content = json.loads(clean_json)
        except Exception:
            logger.warning(f"Failed to parse JSON for {block_type}, returning raw text.")
            content = response_text

        # 5. Cache result if applicable
        if self.cache and block_type == BlockType.MUTATION_PROFILE and signature:
            self.cache.set(signature, response_text if isinstance(content, str) else json.dumps(content))

        return ReportBlock(
            block_type=block_type,
            title=content.get("title") if isinstance(content, dict) else block_type.value.replace("_", " ").title(),
            content=content,
            template=template_config["template"],
            order=template_config["order"]
        )

    def _generate_literature_evidence(self, data: Dict[str, Any]) -> ReportBlock:
        """Multi-step RAG: search -> select -> summarize -> generate block."""
        category = data.get("category", "Unknown")
        mutation_context = data.get("mutations_summary", "Unknown")
        patient_genes = data.get("patient_genes", [])
        
        # 1. Search PubMed
        query = f"{category} {' '.join(patient_genes)} mutations"
        logger.info(f"Performing multi-step RAG for: {query}")
        raw_studies = self.rag.fetch_details(self.rag.search_pmids(query, retmax=15))
        
        if not raw_studies:
            logger.warning("No studies found for query.")
            return self._empty_literature_block()

        # 2. Select Relevant Studies
        studies_text = "\n\n".join([
            f"PMID: {s['pmid']}\nTITLE: {s['title']}\nABSTRACT: {s['abstract']}" 
            for s in raw_studies
        ])
        
        select_template: Dict[str, Any] = BlockTemplate.STUDY_SELECTION
        select_prompt = str(select_template["llm_prompt"]).format(
            category=category,
            mutation_context=mutation_context,
            studies_text=studies_text
        )
        
        selection_response = self.call_llm(select_prompt, "Return only valid JSON.")
        try:
            selection_data = json.loads(re.sub(r"```json\s?|\s?```", "", selection_response).strip())
            relevant_pmids = selection_data.get("relevant_pmids", [])
        except Exception as e:
            logger.error(f"Failed to parse selection JSON: {e}")
            relevant_pmids = [s["pmid"] for s in raw_studies[:3]] # Fallback

        # 3. Summarize Each Relevant Study
        enriched_summaries = []
        keep_pmids = []
        
        summarize_template: Dict[str, Any] = BlockTemplate.STUDY_SUMMARIZATION
        for pmid in relevant_pmids:
            study = next((s for s in raw_studies if s["pmid"] == pmid), None)
            if not study: continue
            
            sum_prompt = str(summarize_template["llm_prompt"]).format(
                category=category,
                mutation_context=mutation_context,
                title=study["title"],
                abstract=study["abstract"],
                pmid=pmid
            )
            
            sum_response = self.call_llm(sum_prompt, "Return only valid JSON.")
            try:
                summary_data = json.loads(re.sub(r"```json\s?|\s?```", "", sum_response).strip())
                enriched_summaries.append(summary_data)
                keep_pmids.append(pmid)
            except Exception:
                logger.warning(f"Failed to summarize study {pmid}")

        # 4. Final Block Generation
        lit_template: Dict[str, Any] = BlockTemplate.LITERATURE_EVIDENCE
        final_data = {
            **data,
            "literature_data": json.dumps(enriched_summaries),
            "kept_pmids": keep_pmids
        }
        
        prompt = str(lit_template["llm_prompt"]).format(**final_data)
        response_text = self.call_llm(prompt, "Return only valid JSON.")
        
        try:
            content = json.loads(re.sub(r"```json\s?|\s?```", "", response_text).strip())
            if isinstance(content, dict):
                content["kept_pmids"] = keep_pmids
        except Exception:
            content = response_text

        return ReportBlock(
            block_type=BlockType.LITERATURE_EVIDENCE,
            title="Literature Evidence",
            content=content,
            template=str(lit_template["template"]),
            order=int(lit_template["order"])
        )

    def _empty_literature_block(self) -> ReportBlock:
        return ReportBlock(
            block_type=BlockType.LITERATURE_EVIDENCE,
            title="Literature Evidence",
            content={"error": "No relevant literature found"},
            template=BlockTemplate.LITERATURE_EVIDENCE["template"],
            order=BlockTemplate.LITERATURE_EVIDENCE["order"]
        )

    def generate_all_blocks(self, block_types: List[BlockType], data: Dict[str, Any]) -> List[ReportBlock]:
        """Generate multiple blocks in parallel."""
        results = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(self.generate_block, bt, data): bt for bt in block_types}
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    logger.error(f"Block generation failed for {futures[future]}: {e}")
        
        return sorted(results, key=lambda x: x.order)

import re # Needed for regex cleanup
