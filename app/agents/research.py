"""BDR research agent — gathers and synthesises company intelligence.

Collects external evidence from web search (via Tavily or simulated), then
uses DeepSeek to synthesise a structured evidence-backed intelligence report.

Every claim in the output must reference a source URL — no hallucinated facts.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.core.contracts import (
    AgentContext,
    AgentResult,
    AgentTaskInput,
    AIMessage,
    AIProvider,
    AIRequest,
    BaseAgent,
    ProviderError,
)
from app.core.task_manager import TaskManager
from app.tools.tool_manager import ToolManager

_EVIDENCE_SYNTHESIS_PROMPT = """\
You are a senior BDR intelligence analyst. Synthesise the provided web search
results into a structured, **evidence-backed** company intelligence report.

RULES:
1. Every claim MUST reference a source URL from the search results provided.
2. Do NOT fabricate facts or sources. If evidence is insufficient, note it.
3. Categorise signals into the evidence categories below.

Return a JSON object with these EXACT keys:
{
  "company_name": "Full company name",
  "domain": "Primary domain",
  "industry": "Industry classification (e.g. Mining, Drone Services, SaaS)",
  "employee_count": integer or null,
  "location": "Headquarters location or null",
  "description": "2-3 sentence company overview",
  "company_situation": "2-3 sentence summary of current business situation based on evidence",
  "operational_pain_points": [
    {
      "pain_point": "Specific operational problem",
      "evidence": "Evidence supporting this pain point",
      "source_url": "URL backing this claim"
    }
  ],
  "buying_signals": [
    {
      "signal": "Specific buying signal",
      "source_url": "URL backing this claim"
    }
  ],
  "business_signals": [
    {
      "signal": "Business/growth signal description",
      "category": "company_news|expansion|hiring|funding|technology|automation|partnership",
      "source_url": "URL backing this claim",
      "summary": "Short summary of the signal",
      "date": "Date of signal or null"
    }
  ],
  "pain_points": ["Likely pain points this company faces"],
  "technology_signals": ["Technology stack and platform signals"],
  "why_now": "2-3 sentence explanation of why this company should be contacted now",
  "flytbase_relevance": "High/Medium/Low — explanation of why FlytBase fits, with evidence",
  "flytbase_fit": "Specific FlytBase capabilities that address the company's pain points",
  "recommended_next_action": "Recommended BDR next step",
  "recommended_sales_angle": "Specific sales angle for the BDR to lead with",
  "confidence_score": 0-100,
  "sources": ["All source URLs used"],
  "evidence": [
    {
      "claim": "Specific claim about the company",
      "source_url": "URL backing this claim"
    }
  ]
}

Use only information present in the search results. Do NOT fabricate data.
Where data is unavailable, set to null or empty list rather than inventing."""

# Targeted search queries for evidence categories
_DEFAULT_SEARCH_QUERIES = [
    "{query} company overview products services",
    "{query} recent news press releases 2026",
    "{query} expansion new offices locations",
    "{query} hiring careers jobs 2026",
    "{query} funding investment acquisition",
    "{query} technology stack automation platforms",
    "{query} partnerships collaborations",
    "{query} industry challenges pain points",
]


class ResearchAgent(BaseAgent):
    """BDR research agent — evidence-backed company intelligence.

    Workflow:
    1. Execute web searches for each evidence category
    2. Extract content from top URLs
    3. Synthesise findings into structured intelligence via LLM
    4. Every claim references a source URL — no fabricated facts
    5. Persist report with evidence and citations
    """

    agent_type = "research"

    def __init__(
        self,
        ai_provider: AIProvider,
        tool_manager: ToolManager,
        task_manager: TaskManager,
    ) -> None:
        self._ai = ai_provider
        self._tools = tool_manager
        self._tm = task_manager

    async def run(self, context: AgentContext, task: AgentTaskInput) -> AgentResult:
        task_id = context.task_id
        company_name = task.input_data.get("company_name", "")
        domain = task.input_data.get("domain", "")

        # ── Step 1: Start ──────────────────────────────────────────────
        self._tm.append_log(
            task_id, "info", "research_started",
            f"Starting evidence-backed research for {company_name!r} domain={domain!r}",
            {"company_name": company_name, "domain": domain},
        )

        query = company_name or domain

        # ── Step 2: Generate category-targeted search queries ────────────
        search_queries = [q.format(query=query) for q in _DEFAULT_SEARCH_QUERIES]

        self._tm.append_log(
            task_id, "info", "planning_completed",
            f"Using {len(search_queries)} category-targeted research queries",
            {"queries": search_queries},
        )

        # ── Step 3: Execute web searches ───────────────────────────────
        all_results: list[dict[str, Any]] = []
        all_sources: list[str] = []

        for q in search_queries:
            self._tm.append_log(
                task_id, "debug", "search_started",
                f"Executing web_search for query={q!r}",
                {"tool": "web_search", "query": q},
            )

            try:
                result = await self._tools.execute("web_search", {"query": q, "max_results": 5})
                page_results = result.content.get("results", [])
                all_results.extend(page_results)
                all_sources.extend(result.sources)

                self._tm.append_log(
                    task_id, "debug", "search_completed",
                    f"web_search returned {len(page_results)} results for {q!r}",
                    {"tool": "web_search", "query": q, "result_count": len(page_results)},
                )
            except ValueError as exc:
                self._tm.append_log(
                    task_id, "error", "tool_failed",
                    f"web_search failed for {q!r}: {exc}",
                    {"tool": "web_search", "query": q, "error": str(exc)},
                )

        # ── Step 4: Extract content from top URLs ──────────────────────
        self._tm.append_log(
            task_id, "info", "extraction_started",
            f"Extracting content from {len(all_sources)} sources",
            {"source_count": len(all_sources)},
        )

        seen_urls: set[str] = set()
        content_texts: list[str] = []

        for source_url in all_sources:
            if source_url in seen_urls:
                continue
            seen_urls.add(source_url)

            self._tm.append_log(
                task_id, "debug", "tool_called",
                f"Extracting content from {source_url}",
                {"tool": "extract_web_content", "url": source_url},
            )

            try:
                extracted = await self._tools.execute(
                    "extract_web_content", {"url": source_url}
                )
                page = extracted.content
                snippet = f"--- {page.get('title', source_url)} ---\n{page.get('text', '')[:2000]}"
                content_texts.append(snippet)

                self._tm.append_log(
                    task_id, "debug", "tool_completed",
                    f"Extracted content from {source_url}",
                    {"tool": "extract_web_content", "url": source_url},
                )
            except ValueError as exc:
                self._tm.append_log(
                    task_id, "error", "tool_failed",
                    f"extract_web_content failed for {source_url}: {exc}",
                    {"tool": "extract_web_content", "url": source_url, "error": str(exc)},
                )

        # ── Step 5: Synthesise into evidence-backed report ──────────────
        self._tm.append_log(
            task_id, "info", "synthesis_started",
            "Synthesising evidence-backed intelligence report via LLM",
        )

        findings = await self._synthesize_report(
            company_name=company_name,
            domain=domain,
            search_results=all_results,
            extracted_content=content_texts,
            task_id=task_id,
        )

        evidence = findings.get("evidence", [])
        sources = findings.get("sources", all_sources)

        # ── Step 6: Build report output ────────────────────────────────
        report_id = uuid.uuid4()

        self._tm.append_log(
            task_id, "info", "report_created",
            f"Research report created (id={report_id}) with {len(evidence)} evidence items",
            {"report_id": str(report_id), "evidence_count": len(evidence)},
        )

        summary = findings.get("description", f"Research completed for {company_name or domain}")
        report_data = {
            "company_name": findings.get("company_name", company_name),
            "domain": findings.get("domain", domain),
            "industry": findings.get("industry"),
            "employee_count": findings.get("employee_count"),
            "location": findings.get("location"),
            "description": findings.get("description"),
            # Evidence-backed intelligence
            "company_situation": findings.get("company_situation", ""),
            "operational_pain_points": findings.get("operational_pain_points", []),
            "buying_signals": findings.get("buying_signals", []),
            "business_signals": findings.get("business_signals", []),
            "pain_points": findings.get("pain_points", []),
            "technology_signals": findings.get("technology_signals", []),
            "why_now": findings.get("why_now", ""),
            "flytbase_relevance": findings.get("flytbase_relevance", ""),
            "flytbase_fit": findings.get("flytbase_fit", ""),
            "recommended_next_action": findings.get("recommended_next_action", ""),
            "recommended_sales_angle": findings.get("recommended_sales_angle", ""),
            "confidence_score": findings.get("confidence_score", 0),
            "sources": sources,
        }

        output_data: dict[str, Any] = {
            "report_id": str(report_id),
            "findings": report_data,
            "evidence": evidence,
            "intelligence_metadata": {
                "analysis_version": "2.0",
                "search_count": len(search_queries),
                "source_count": len(all_sources),
                "extraction_count": len(content_texts),
                "evidence_count": len(evidence),
            },
            "providers_used": getattr(self._ai, "name", "unknown"),
        }

        # ── Step 7: Complete ────────────────────────────────────────────
        self._tm.append_log(
            task_id, "info", "task_completed",
            f"Evidence-backed intelligence research completed for {company_name or domain}",
            {
                "report_id": str(report_id),
                "source_count": len(all_sources),
                "evidence_count": len(evidence),
            },
        )

        return AgentResult(
            output_data=output_data,
            summary=summary,
            requires_human_approval=False,
        )

    # ── internal helpers ───────────────────────────────────────────────

    async def _synthesize_report(
        self,
        company_name: str,
        domain: str,
        search_results: list[dict[str, Any]],
        extracted_content: list[str],
        task_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Use DeepSeek to synthesise search data into a structured,
        evidence-backed intelligence report."""
        search_summary = json.dumps(search_results[:15], indent=2)
        content_summary = "\n\n".join(extracted_content[:5])

        user_prompt = (
            f"Company: {company_name or 'Unknown'}\n"
            f"Domain: {domain or 'Unknown'}\n\n"
            f"=== Search Results ===\n{search_summary}\n\n"
            f"=== Extracted Content ===\n{content_summary}\n\n"
            "Synthesise the above into a structured BDR intelligence report.\n"
            "Every claim MUST reference a source URL from the data above.\n"
            "Return ONLY valid JSON matching the specified schema."
        )

        fallback: dict[str, Any] = {
            "company_name": company_name,
            "domain": domain,
            "description": f"Research completed for {company_name or domain}.",
            "company_situation": "",
            "operational_pain_points": [],
            "buying_signals": [],
            "business_signals": [],
            "pain_points": [],
            "technology_signals": [],
            "why_now": "",
            "flytbase_relevance": "",
            "flytbase_fit": "",
            "recommended_next_action": "",
            "recommended_sales_angle": "",
            "confidence_score": 0,
            "sources": [],
            "evidence": [],
        }

        try:
            response = await self._ai.generate(
                AIRequest(
                    messages=[
                        AIMessage(role="system", content=_EVIDENCE_SYNTHESIS_PROMPT),
                        AIMessage(role="user", content=user_prompt),
                    ],
                    temperature=0.3,
                )
            )
            parsed = _parse_json_object(response.content)
            if parsed is not None:
                return parsed
            return fallback
        except (ProviderError, Exception):
            return fallback


# ── JSON parsing helpers ───────────────────────────────────────────────


def _parse_json_object(text: str) -> dict[str, Any] | None:
    """Best-effort parse of a JSON object from LLM output."""
    cleaned = _strip_code_fences(text).strip()
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(cleaned[start: end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return None


def _strip_code_fences(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` code fences from LLM output."""
    lines = text.split("\n")
    cleaned = [line for line in lines if not line.strip().startswith("```")]
    return "\n".join(cleaned)
