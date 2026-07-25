"""BDR research agent — gathers and synthesises company intelligence.

Upgraded with Account Intelligence Engine integration for deeper,
more structured company analysis with citation tracking.
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

_SYNTHESIS_SYSTEM_PROMPT = """\
You are a senior BDR intelligence analyst. Synthesize the provided research data
into a comprehensive company intelligence profile.

Return a JSON object with these EXACT keys:
{
  "company_name": "Full company name",
  "domain": "Primary domain",
  "industry": "Industry classification (e.g. Drone Services, SaaS, Mining)",
  "employee_count": integer or null,
  "location": "Headquarters location or null",
  "description": "2-3 sentence company overview",
  "company_situation": "2-3 sentence summary of current business situation",
  "business_problems": ["Specific operational problem 1", "Specific problem 2"],
  "operational_risks": ["Risk of not solving problem 1", "Risk of not solving problem 2"],
  "business_signals": ["Growth signals — hiring, funding, expansion, partnerships"],
  "buying_signals": ["Buying signals — tech stack changes, vendor evaluations, leadership changes"],
  "pain_points": ["Likely pain points this company faces"],
  "technology_signals": ["Technology stack and platform signals"],
  "flytbase_relevance": "Relevance to FlytBase — High/Medium/Low + rationale",
  "recommended_next_action": "Recommended BDR next step",
  "recommended_sales_angle": "Specific sales angle for the BDR to lead with",
  "industry_incidents": [
    {
      "title": "Incident title",
      "summary": "What happened and why it matters",
      "implication": "Why this creates urgency for the prospect"
    }
  ],
  "sources": ["URLs used in this analysis"],
  "citations": [
    {"source": "Source description", "url": "URL", "key_finding": "Key finding from this source"}
  ]
}

Use only information present in the search results. Do NOT fabricate data.
Where data is unavailable, note it as \"Insufficient data\" rather than inventing."""

# Default fallback search queries when LLM-based planning is unavailable
_DEFAULT_SEARCH_QUERIES = [
    "{query} company overview products services",
    "{query} recent news funding 2026",
    "{query} technology stack platforms",
    "{query} team size locations leadership",
    "{query} business challenges pain points",
]


class ResearchAgent(BaseAgent):
    """BDR research agent — single LLM call per task.

    Workflow:
    1. Use pre-defined search queries (no LLM call)
    2. Execute web search for each query
    3. Extract content from top URLs
    4. Synthesize findings + account intelligence in a single LLM call
    5. Persist report with citations and metadata

    LLM calls reduced from 3 → 1 per task:
    - Planning (removed): hardcoded default queries cover all BDR dimensions
    - Intelligence analysis (merged): synthesis prompt now includes all
      intelligence fields (company_situation, business_problems,
      operational_risks, buying_signals, citations, etc.)
    - Synthesis (kept): produces the structured BDR report
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
            f"Starting account intelligence research for {company_name!r} domain={domain!r}",
            {"company_name": company_name, "domain": domain},
        )

        query = company_name or domain

        # ── Step 2: Use default search queries (no LLM call) ────────────
        # Planning via LLM is skipped to reduce unnecessary calls since
        # search tools run in simulated mode by default. The hardcoded
        # queries cover all relevant dimensions for BDR research.
        search_queries = [q.format(query=query) for q in _DEFAULT_SEARCH_QUERIES]

        self._tm.append_log(
            task_id, "info", "planning_completed",
            f"Using {len(search_queries)} default research queries",
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

        # ── Step 5: Synthesize into comprehensive report (single LLM call) ──
        # Both account intelligence analysis and structured report generation
        # are done in a single LLM call to reduce API overhead. The synthesis
        # prompt includes all intelligence fields (business problems,
        # operational risks, growth signals, buying signals, citations, etc.)
        self._tm.append_log(
            task_id, "info", "synthesis_started",
            "Synthesising research data into structured report via LLM",
        )

        findings = await self._synthesize_report(
            company_name=company_name,
            domain=domain,
            search_results=all_results,
            extracted_content=content_texts,
            task_id=task_id,
        )

        citations = findings.get("citations", [])

        # ── Step 6: Build report output ────────────────────────────────
        report_id = uuid.uuid4()

        self._tm.append_log(
            task_id, "info", "report_created",
            f"Research report created (id={report_id}) with {len(citations)} citations",
            {"report_id": str(report_id), "citation_count": len(citations)},
        )

        summary = findings.get("description", f"Research completed for {company_name or domain}")
        report_data = {
            "company_name": findings.get("company_name", company_name),
            "domain": findings.get("domain", domain),
            "industry": findings.get("industry"),
            "employee_count": findings.get("employee_count"),
            "location": findings.get("location"),
            "description": findings.get("description"),
            "company_situation": findings.get("company_situation", ""),
            "business_problems": findings.get("business_problems", []),
            "operational_risks": findings.get("operational_risks", []),
            "business_signals": findings.get("business_signals", []),
            "buying_signals": findings.get("buying_signals", []),
            "pain_points": findings.get("pain_points", []),
            "technology_signals": findings.get("technology_signals", []),
            "growth_signals": findings.get("business_signals", []),
            "flytbase_relevance": findings.get("flytbase_relevance"),
            "recommended_next_action": findings.get("recommended_next_action"),
            "recommended_sales_angle": findings.get("recommended_sales_angle"),
            "industry_incidents": findings.get("industry_incidents", []),
            "sources": findings.get("sources", all_sources),
        }

        output_data: dict[str, Any] = {
            "report_id": str(report_id),
            "findings": report_data,
            "citations": citations,
            "intelligence_metadata": {
                "analysis_version": "1.0",
                "search_count": len(search_queries),
                "source_count": len(all_sources),
                "extraction_count": len(content_texts),
            },
            "providers_used": getattr(self._ai, "name", "unknown"),
        }

        # ── Step 7: Complete ────────────────────────────────────────────
        self._tm.append_log(
            task_id, "info", "task_completed",
            f"Account intelligence research completed for {company_name or domain}",
            {
                "report_id": str(report_id),
                "source_count": len(all_sources),
                "citation_count": len(citations),
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
        """Use LLM to synthesise search data into a structured BDR report."""
        search_summary = json.dumps(search_results[:10], indent=2)
        content_summary = "\n\n".join(extracted_content[:5])

        user_prompt = (
            f"Company: {company_name or 'Unknown'}\n"
            f"Domain: {domain or 'Unknown'}\n\n"
            f"=== Search Results ===\n{search_summary}\n\n"
            f"=== Extracted Content ===\n{content_summary}\n\n"
            "Synthesise the above into a structured BDR intelligence report. "
            "Return ONLY valid JSON matching the specified schema."
        )

        fallback: dict[str, Any] = {
            "company_name": company_name,
            "domain": domain,
            "description": f"Research completed for {company_name or domain}.",
            "company_situation": "",
            "business_problems": [],
            "operational_risks": [],
            "business_signals": [],
            "buying_signals": [],
            "pain_points": [],
            "technology_signals": [],
            "flytbase_relevance": "",
            "recommended_next_action": "",
            "recommended_sales_angle": "",
            "industry_incidents": [],
            "sources": [],
            "citations": [],
        }

        try:
            response = await self._ai.generate(
                AIRequest(
                    messages=[
                        AIMessage(role="system", content=_SYNTHESIS_SYSTEM_PROMPT),
                        AIMessage(role="user", content=user_prompt),
                    ],
                    temperature=0.3,
                )
            )
            parsed = _parse_json_object(response.content)
            if parsed is not None:
                return parsed
            return fallback
        except ProviderError as exc:
            self._tm.append_log(
                task_id, "error", "llm_synthesis_failed",
                f"LLM synthesis failed: {exc}",
                {"error": str(exc)},
            )
            return fallback
        except Exception as exc:
            self._tm.append_log(
                task_id, "error", "llm_synthesis_error",
                f"Unexpected synthesis error: {exc}",
                {"error": str(exc)},
            )
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
