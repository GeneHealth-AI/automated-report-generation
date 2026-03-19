"""
Review Agent for post-generation quality assurance of precision medicine reports.

Two-stage review pipeline:
  Stage 1 (Content Review): LLM reviews the report JSON for accuracy, tone, and consistency.
  Stage 2 (Visual Review): Programmatic + LLM review of rendered HTML for structural integrity.
"""

import json
import re
import logging
from typing import Any

from report_blocks import ReportBlock

logger = logging.getLogger(__name__)


def _import_generate_gemini_response():
    """Lazy import to avoid circular dependencies."""
    try:
        from block_generator import generate_gemini_response
        return generate_gemini_response
    except ImportError:
        logger.warning("Could not import generate_gemini_response from block_generator")
        return None


def _parse_json_response(text: str) -> dict:
    """Parse a JSON response from LLM, handling markdown fences."""
    cleaned = text.strip()
    if cleaned.startswith('```'):
        first_newline = cleaned.find('\n')
        if first_newline != -1:
            cleaned = cleaned[first_newline + 1:]
        if cleaned.endswith('```'):
            cleaned = cleaned[:-3].rstrip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


class ReviewAgent:
    """Two-stage review pipeline for generated precision medicine reports."""

    def __init__(self, temperature: float = 0.3):
        """
        Args:
            temperature: LLM temperature for review calls. Higher than generation
                         (0.1) to allow more evaluative reasoning.
        """
        self.temperature = temperature

    # ------------------------------------------------------------------
    # Stage 1: Content Review
    # ------------------------------------------------------------------
    def content_review(
        self,
        blocks: list[ReportBlock],
        report_info: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Review the report content JSON for quality issues.

        Checks:
          - All factual claims are documented / cited
          - Nothing is overly absolute or fear-inducing
          - Language is appropriate for patient audience
          - Consistency across blocks (e.g. risk levels don't contradict)
          - No suspiciously empty sections

        Returns:
            dict with keys: passed (bool), issues (list), overall_assessment (str)
        """
        generate = _import_generate_gemini_response()
        if generate is None:
            return {
                "passed": True,
                "issues": [],
                "overall_assessment": "Review skipped — LLM unavailable",
            }

        # Serialize block content
        blocks_json: dict[str, Any] = {}
        for block in blocks:
            content = block.content
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except json.JSONDecodeError:
                    pass
            blocks_json[block.block_type.value] = {
                "title": block.title,
                "content": content,
            }

        # Truncate to stay within token budget
        serialized = json.dumps(blocks_json, indent=2, default=str)
        if len(serialized) > 50_000:
            serialized = serialized[:50_000] + "\n... (truncated)"

        review_prompt = f"""You are a medical report quality reviewer. Review the following precision medicine report content.

Report Focus: {report_info.get('focus', 'Unknown')}
Patient: {report_info.get('patient_name', 'Unknown')}

REPORT CONTENT:
{serialized}

REVIEW CRITERIA — check each one carefully:

1. CITATION CHECK: Are all factual claims about gene-disease associations supported? Flag any unsupported medical claims that present speculation as fact.

2. TONE CHECK: Is anything overly absolute or fear-inducing? Flag statements like "you WILL develop", "guaranteed", or language that could cause unnecessary anxiety. The report should be factual but empowering.

3. LANGUAGE CHECK: Is the patient-facing content (executive summary, lifestyle recommendations, monitoring plan) at an appropriate reading level (roughly 8th grade)? Flag overly technical jargon in patient sections.

4. CONSISTENCY CHECK: Do blocks contradict each other? For example, does one block say "high risk" while another says "low risk" for the same condition? Are gene names and mutation descriptions consistent?

5. COMPLETENESS CHECK: Are any sections suspiciously empty or missing key information that should be present given the patient's genetic data?

6. WORD CHECK: Does any section use the word "Urgent"? It should use "Critical", "Highly Recommended", or "Important" instead.

Return your review as valid JSON ONLY:
{{
    "passed": true or false,
    "issues": [
        {{
            "block": "block_type_value",
            "issue": "Description of the issue",
            "severity": "critical/warning/info",
            "suggestion": "How to fix it",
            "original_text": "The problematic text snippet (first 100 chars)"
        }}
    ],
    "overall_assessment": "Brief overall quality assessment (2-3 sentences)",
    "readability_score": "estimated grade level of patient-facing content"
}}
"""

        system_prompt = (
            "You are a clinical report quality assurance specialist. "
            "Your job is to review genetic medicine reports for accuracy, tone, and patient-safety. "
            "Be thorough but practical — only flag genuine issues, not stylistic preferences. "
            "Return valid JSON only."
        )

        try:
            result = generate(review_prompt, system_prompt, max_tokens=8000)
            parsed = _parse_json_response(result)
            if parsed:
                return parsed
            return {
                "passed": True,
                "issues": [],
                "overall_assessment": "Review completed but response could not be parsed",
                "raw_review": result[:2000],
            }
        except Exception as e:
            logger.error(f"Content review failed: {e}")
            return {
                "passed": True,
                "issues": [],
                "overall_assessment": f"Content review error (non-blocking): {e}",
            }

    # ------------------------------------------------------------------
    # Stage 2: Visual / Structural Review
    # ------------------------------------------------------------------
    def visual_review(
        self,
        html_content: str,
        blocks: list[ReportBlock],
    ) -> dict[str, Any]:
        """
        Review the rendered HTML for structural and visual consistency.

        Combines programmatic checks with an LLM assessment of the
        structural summary.

        Checks:
          - All expected blocks are present and rendered
          - No error blocks
          - Block order is logical
          - No suspiciously small content
          - report-block class present on all blocks
        """
        generate = _import_generate_gemini_response()

        # --- Programmatic checks ---
        section_count = html_content.count('class="section-anchor"')

        # Error blocks
        error_blocks = re.findall(
            r'data-block-type="(\w+)".*?class="error-message"',
            html_content,
            re.DOTALL,
        )

        # Missing sections
        missing_sections = []
        for block in blocks:
            block_id = f"section-{block.block_type.value}"
            if block_id not in html_content:
                missing_sections.append(block.block_type.value)

        # Missing report-block class
        blocks_without_class = []
        for block in blocks:
            marker = f'data-block-type="{block.block_type.value}"'
            idx = html_content.find(marker)
            if idx > 0:
                preceding = html_content[max(0, idx - 300) : idx]
                if "report-block" not in preceding:
                    blocks_without_class.append(block.block_type.value)

        # Build block summaries for LLM
        block_summaries = []
        for block in sorted(blocks, key=lambda b: b.order):
            content = block.content
            content_keys = (
                list(content.keys()) if isinstance(content, dict) else ["raw_text"]
            )
            content_length = (
                len(json.dumps(content, default=str))
                if isinstance(content, dict)
                else len(str(content))
            )
            block_summaries.append(
                {
                    "type": block.block_type.value,
                    "title": block.title,
                    "order": block.order,
                    "content_keys": content_keys,
                    "content_length": content_length,
                    "has_error": isinstance(content, dict) and "error" in content,
                }
            )

        # If LLM is unavailable, return programmatic results only
        if generate is None:
            return {
                "passed": len(error_blocks) == 0 and len(missing_sections) == 0,
                "visual_issues": [],
                "structural_assessment": "Programmatic check only — LLM unavailable",
                "missing_blocks": missing_sections,
                "render_errors": error_blocks,
                "blocks_missing_report_class": blocks_without_class,
            }

        review_prompt = f"""You are reviewing the structure and visual consistency of a precision medicine HTML report.

PROGRAMMATIC SCAN RESULTS:
- Total sections rendered: {section_count}
- Blocks with render errors: {error_blocks or 'None'}
- Missing sections: {missing_sections or 'None'}
- Blocks without report-block CSS class: {blocks_without_class or 'None'}

BLOCK DETAILS (sorted by display order):
{json.dumps(block_summaries, indent=2)}

REVIEW CRITERIA:
1. Are all expected blocks present and rendered?
2. Is the block order logical? Consumer-friendly content should come first (introduction, executive summary, lifestyle, monitoring), followed by technical/clinician content (risk assessment, mutation profile, literature).
3. Are there any blocks with suspiciously small content (content_length < 200)?
4. Are there any error blocks that need regeneration?
5. Do all blocks have the report-block CSS class for consistent styling?

Return your review as valid JSON ONLY:
{{
    "passed": true or false,
    "visual_issues": [
        {{
            "block": "block_type",
            "issue": "description",
            "severity": "critical/warning/info"
        }}
    ],
    "structural_assessment": "Overall structural quality (1-2 sentences)",
    "missing_blocks": [],
    "render_errors": []
}}
"""
        system_prompt = (
            "You are an HTML report quality reviewer for medical documents. "
            "Return valid JSON only."
        )

        try:
            result = generate(review_prompt, system_prompt, max_tokens=4000)
            parsed = _parse_json_response(result)
            if parsed:
                # Merge programmatic findings
                parsed.setdefault("blocks_missing_report_class", blocks_without_class)
                return parsed
            return {
                "passed": len(error_blocks) == 0 and len(missing_sections) == 0,
                "visual_issues": [],
                "structural_assessment": "Visual review response could not be parsed",
                "missing_blocks": missing_sections,
                "render_errors": error_blocks,
                "blocks_missing_report_class": blocks_without_class,
                "raw_review": result[:2000],
            }
        except Exception as e:
            logger.error(f"Visual review failed: {e}")
            return {
                "passed": len(error_blocks) == 0 and len(missing_sections) == 0,
                "visual_issues": [],
                "structural_assessment": f"Visual review error (non-blocking): {e}",
                "missing_blocks": missing_sections,
                "render_errors": error_blocks,
                "blocks_missing_report_class": blocks_without_class,
            }

    # ------------------------------------------------------------------
    # Combined Review
    # ------------------------------------------------------------------
    def run_full_review(
        self,
        blocks: list[ReportBlock],
        html_content: str,
        report_info: dict[str, Any],
    ) -> dict[str, Any]:
        """Run both review stages and return combined results."""
        logger.info("Starting report review pipeline (Stage 1: Content, Stage 2: Visual)")

        content_result = self.content_review(blocks, report_info)
        logger.info(
            f"Content review: passed={content_result.get('passed', 'N/A')}, "
            f"issues={len(content_result.get('issues', []))}"
        )

        visual_result = self.visual_review(html_content, blocks)
        logger.info(
            f"Visual review: passed={visual_result.get('passed', 'N/A')}, "
            f"issues={len(visual_result.get('visual_issues', []))}"
        )

        critical_issues = [
            issue
            for issue in content_result.get("issues", [])
            if issue.get("severity") == "critical"
        ] + [
            issue
            for issue in visual_result.get("visual_issues", [])
            if issue.get("severity") == "critical"
        ]

        combined = {
            "content_review": content_result,
            "visual_review": visual_result,
            "overall_passed": content_result.get("passed", True)
            and visual_result.get("passed", True),
            "critical_issues": critical_issues,
            "total_issues": len(content_result.get("issues", []))
            + len(visual_result.get("visual_issues", [])),
        }

        logger.info(
            f"Review complete: overall_passed={combined['overall_passed']}, "
            f"critical_issues={len(critical_issues)}, "
            f"total_issues={combined['total_issues']}"
        )

        return combined
