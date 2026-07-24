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
from app.intelligence.account_research import AccountResearchIntelligence
from app.tools.tool_manager import ToolManager

_PLANNING_SYSTEM_PROMPT = """\
You are a BDR research planner. Given a company name and/or domain,
generate 3-5 web search queries that will help build a complete
company intelligence profile.

Focus on:
- Company overview, products, and services
- Recent news, funding, and strategic moves
- Technology stack and platform signals
- Team size, locations, and key personnel
- Pain points and business challenges

Return ONLY a JSON array of query strings. No explanation, no markdown."""

_SYNTHESIS_SYSTEM_PROMPT = """\
You are a BDR intelligence analyst. Synthesize the provided research data
into a structured company profile.

Return a JSON object with these EXACT keys:
{
  "company_name": "Full company name",
  "domain": "Primary domain",
  "industry": "Industry classification (e.g. Drone Services, SaaS)",
  "employee_count": integer or null,
  "location": "Headquarters location or null",
  "description": "2-3 sentence company overview",
  "business_signals": ["Business signals — hiring, funding, expansion"],
  "pain_points": ["Likely pain points this company faces"],
  "technology_signals": ["Technology stack and platform signals"],
  "flytbase_relevance": "Relevance to FlytBase — High/Medium/Low + rationale",
  "recommended_next_action": "Recommended BDR next step",
  "sources": ["URLs used in this analysis"]
}

Use only information present in the search results. Do NOT fabricate data."""


class ResearchAgent(BaseAgent):
    """BDR research agent with Account Intelligence Engine integration.

    Workflow:
    1. Plan search queries via LLM
    2. Execute web search for each query
    3. Extract content from top URLs
    4. Generate account intelligence via AIProvider
    5. Synthesize findings into structured BDR report
    6. Persist report with citations and metadata
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
        self._intelligence = AccountResearchIntelligence(ai_provider)

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

        # ── Step 2: Plan search queries via LLM ─────────────────────────
        self._tm.append_log(
            task_id, "info", "planning_started",
            "Generating research queries via LLM",
        )

        search_queries = await self._plan_queries(query, task_id)
        if not search_queries:
            search_queries = [f"{query} company overview", f"{query} news 2026"]

        self._tm.append_log(
            task_id, "info", "planning_completed",
            f"Generated {len(search_queries)} search queries",
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

        # ── Step 5: Generate Account Intelligence ───────────────────────
        self._tm.append_log(
            task_id, "info", "intelligence_analysis_started",
            "Generating structured account intelligence via AIProvider",
        )

        intelligence = await self._intelligence.analyze(
            company_name=company_name,
            search_results=all_results,
            extracted_content=content_texts,
        )

        self._tm.append_log(
            task_id, "info", "intelligence_analysis_completed",
            "Account intelligence analysis complete",
            {
                "business_problems": len(intelligence.get("business_problems", [])),
                "growth_signals": len(intelligence.get("growth_signals", [])),
                "citations": len(intelligence.get("citations", [])),
            },
        )

        # ── Step 6: Synthesize via LLM ─────────────────────────────────
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

        # Merge account intelligence into findings for richer output
        findings.setdefault("business_signals", intelligence.get("growth_signals", []))
        findings.setdefault("pain_points", intelligence.get("business_problems", []))
        findings.setdefault("technology_signals", intelligence.get("technology_signals", []))
        if not findings.get("flytbase_relevance"):
            findings["flytbase_relevance"] = intelligence.get("flytbase_relevance")
        if not findings.get("recommended_next_action"):
            findings["recommended_next_action"] = intelligence.get("recommended_sales_angle")

        citations = intelligence.get("citations", [])

        # ── Step 7: Persist report ─────────────────────────────────────
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
            "business_signals": findings.get("business_signals", []),
            "pain_points": findings.get("pain_points", []),
            "technology_signals": findings.get("technology_signals", []),
            "flytbase_relevance": findings.get("flytbase_relevance"),
            "recommended_next_action": findings.get("recommended_next_action"),
            "sources": findings.get("sources", all_sources),
            # Account Intelligence enriched fields
            "company_situation": intelligence.get("company_situation", ""),
            "growth_signals": intelligence.get("growth_signals", []),
            "buying_signals": intelligence.get("buying_signals", []),
            "operational_risks": intelligence.get("operational_risks", []),
            "industry_incidents": intelligence.get("industry_incidents", []),
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

        # ── Step 8: Complete ────────────────────────────────────────────
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

    async def _plan_queries(self, query: str, task_id: uuid.UUID) -> list[str]:
        """Use LLM to generate targeted search queries for this company."""
        prompt = (
            f"Company: {query}\n\n"
            "Generate 3-5 web search queries to research this company for BDR outreach. "
            "Return ONLY a JSON array of strings."
        )

        try:
            response = await self._ai.generate(
                AIRequest(
                    messages=[
                        AIMessage(role="system", content=_PLANNING_SYSTEM_PROMPT),
                        AIMessage(role="user", content=prompt),
                    ],
                    temperature=0.3,
                )
            )
            return _parse_json_list(response.content)
        except ProviderError as exc:
            self._tm.append_log(
                task_id, "error", "llm_planning_failed",
                f"LLM planning failed: {exc}",
                {"error": str(exc)},
            )
            return []
        except Exception as exc:
            self._tm.append_log(
                task_id, "error", "llm_planning_error",
                f"Unexpected planning error: {exc}",
                {"error": str(exc)},
            )
            return []

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
            "business_signals": [],
            "pain_points": [],
            "technology_signals": [],
            "sources": [],
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


def _parse_json_list(text: str) -> list[str]:
    """Best-effort parse of a JSON array from LLM output."""
    cleaned = _strip_code_fences(text).strip()
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            return [str(item) for item in parsed if item]
    except json.JSONDecodeError:
        pass
    # Fallback: try to find array boundaries
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start != -1 and end > start:
        try:
            parsed = json.loads(cleaned[start: end + 1])
            if isinstance(parsed, list):
                return [str(item) for item in parsed if item]
        except json.JSONDecodeError:
            pass
    return []


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
