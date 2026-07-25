"""BDR research agent — gathers and synthesises company intelligence.

Collects external evidence from web search (via Tavily or simulated), then
uses DeepSeek to synthesise a structured evidence-backed intelligence report.

Every claim in the output must reference a source URL — no hallucinated facts.
"""

from __future__ import annotations

import json
import logging
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
from app.intelligence.signal_collector import ResearchSignal, SignalCollector
from app.tools.tool_manager import ToolManager

logger = logging.getLogger(__name__)

_EVIDENCE_SYNTHESIS_PROMPT = """\
You are a senior BDR intelligence analyst.  Below you will find a set of
**collected evidence signals** — real search results and extracted web
content for the target company.  Your job is to **analyse this evidence**
and produce a structured, evidence-backed company intelligence report.

CRITICAL RULES:
1. DO NOT fabricate facts, dates, or sources.  Use ONLY the evidence
   provided in the "Collected Signals" and "Extracted Content" sections.
2. Every claim in your output MUST reference a ``source_url`` that exists
   in the evidence you were given.
3. If the evidence for a particular field is insufficient, set it to
   ``null`` or ``[]`` — do NOT invent data.
4. Categorise signals using the categories present in the evidence.

Return ONLY valid JSON matching this schema — no markdown, no commentary:
{
  "company_name": "Full company name",
  "domain": "Primary domain",
  "industry": "Industry classification (e.g. Mining, Drone Services, SaaS)",
  "employee_count": integer or null,
  "location": "Headquarters location or null",
  "description": "2-3 sentence company overview synthesised from evidence",
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
  "recent_signals": [
    {
      "title": "Signal title from collected evidence",
      "url": "Source URL",
      "date": "Date or null",
      "summary": "Short summary of this signal",
      "category": "company_news|press_release|industry_article|safety_incident|tech_announcement"
    }
  ],
  "sources": ["All unique source URLs used"],
  "evidence": [
    {
      "claim": "Specific claim about the company",
      "source_url": "URL backing this claim"
    }
  ]
}

Analyse the evidence below.  Do NOT invent anything."""

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

        # ── Step 2: Collect structured evidence signals via SignalCollector ─
        self._tm.append_log(
            task_id, "info", "signal_collection_started",
            f"Collecting category-targeted evidence signals for {company_name!r}",
            {"company_name": company_name, "domain": domain},
        )

        collector = SignalCollector(self._tools)
        collected_signals = await collector.collect(
            company_name=company_name,
            domain=domain,
            max_signals_per_category=3,
        )

        all_sources: list[str] = [s.url for s in collected_signals]

        self._tm.append_log(
            task_id, "info", "signal_collection_completed",
            f"Collected {len(collected_signals)} signals from {len(all_sources)} sources",
            {"signal_count": len(collected_signals), "source_count": len(all_sources)},
        )

        logger.info(
            "[RESEARCH] signals_count=%s company=%s",
            len(collected_signals), company_name,
        )

        # ── Step 3: Extract content from signal source URLs ────────────
        self._tm.append_log(
            task_id, "info", "extraction_started",
            f"Extracting content from {len(all_sources)} signal sources",
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

        # ── Step 4: Synthesise into evidence-backed report ──────────────
        self._tm.append_log(
            task_id, "info", "synthesis_started",
            "Synthesising evidence-backed intelligence report via LLM",
        )

        logger.info(
            "[AI SYNTHESIS] started company=%s signals=%s",
            company_name, len(collected_signals),
        )

        findings = await self._synthesize_report(
            company_name=company_name,
            domain=domain,
            collected_signals=collected_signals,
            extracted_content=content_texts,
            task_id=task_id,
        )

        evidence = findings.get("evidence", [])
        sources = findings.get("sources", all_sources)

        # ── Step 7: Build report output ────────────────────────────────
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
            "evidence": findings.get("evidence", []),
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
            # Structured evidence signals
            "recent_signals": [
                {
                    "title": s.get("title", ""),
                    "url": s.get("url", ""),
                    "date": s.get("date"),
                    "summary": s.get("summary", ""),
                    "category": s.get("category", "company_news"),
                }
                for s in findings.get("recent_signals", [])
            ],
            "sources": sources,
        }

        output_data: dict[str, Any] = {
            "report_id": str(report_id),
            "findings": report_data,
            "evidence": evidence,
            "intelligence_metadata": {
                "analysis_version": "3.0",
                "signal_count": len(collected_signals),
                "source_count": len(all_sources),
                "extraction_count": len(content_texts),
                "evidence_count": len(evidence),
            },
            "providers_used": getattr(self._ai, "name", "unknown"),
        }

        # ── Step 8: Complete ────────────────────────────────────────────
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
        collected_signals: list[ResearchSignal],
        extracted_content: list[str],
        task_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Use DeepSeek to synthesise collected evidence signals into a
        structured, evidence-backed intelligence report.

        ``collected_signals`` are ``ResearchSignal`` objects from
        ``SignalCollector``.  They are rendered as formatted text in the
        prompt for analysis.  If the LLM is unavailable or returns
        unparseable output, the collected signals are preserved in a
        structured fallback so no evidence is lost.
        """
        content_summary = "\n\n".join(extracted_content[:5])
        signals_text = SignalCollector.format_signals_for_prompt(collected_signals)

        user_prompt = (
            f"Company: {company_name or 'Unknown'}\n"
            f"Domain: {domain or 'Unknown'}\n\n"
            f"=== Collected Evidence Signals ===\n{signals_text}\n\n"
            f"=== Extracted Web Content ===\n{content_summary}\n\n"
            "Analyse the evidence above.  Synthesise it into a structured "
            "BDR intelligence report.\n"
            "Every claim MUST reference a source URL from the evidence above.\n"
            "Return ONLY valid JSON matching the specified schema."
        )

        # ── Build evidence-preserving fallback ─────────────────────────────
        def _build_fallback() -> dict[str, Any]:
            signal_dicts = [
                {
                    "title": s.title,
                    "url": s.url,
                    "date": s.date,
                    "summary": s.summary,
                    "category": s.category,
                }
                for s in collected_signals
            ]
            # Derive pain points and buying signals from signal categories
            derived_pain_points = [
                {
                    "pain_point": s.summary if len(s.summary) > 20 else s.title,
                    "evidence": s.summary or s.title,
                    "source_url": s.url,
                }
                for s in collected_signals
                if s.url and s.category in (
                    "safety_incident", "industry_article", "company_news",
                )
            ]
            derived_buying_signals = [
                {
                    "signal": s.summary if len(s.summary) > 15 else s.title,
                    "source_url": s.url,
                }
                for s in collected_signals
                if s.url and s.category in (
                    "expansion", "hiring", "funding", "technology",
                    "technology_announcement", "tech_announcement", "partnership",
                )
            ]
            derived_pain_list = list({s["pain_point"]: s for s in derived_pain_points}.values())
            derived_buying_list = list({s["signal"]: s for s in derived_buying_signals}.values())
            return {
                "company_name": company_name,
                "domain": domain,
                "description": f"Research completed for {company_name or domain}. "
                "AI synthesis unavailable; evidence signals preserved.",
                "company_situation": (
                    f"{company_name or domain} is active in their industry based on "
                    f"{len(collected_signals)} recent signals collected from public sources."
                ),
                "operational_pain_points": derived_pain_list,
                "buying_signals": derived_buying_list,
                "business_signals": [
                    {
                        "signal": s.summary or s.title,
                        "category": s.category,
                        "source_url": s.url,
                        "summary": s.summary or "",
                        "date": s.date,
                    }
                    for s in collected_signals
                    if s.url
                ],
                "pain_points": [s.summary for s in collected_signals if s.summary][:5],
                "technology_signals": [
                    s.title for s in collected_signals
                    if s.category in ("technology", "technology_announcement",
                                     "tech_announcement")
                ],
                "why_now": (
                    f"Recent signals indicate activity in automation, expansion, "
                    f"or industry developments relevant to {company_name or domain}."
                ),
                "flytbase_relevance": "Research data collected but AI synthesis unavailable. "
                "Review recent signals for relevance.",
                "flytbase_fit": "",
                "recommended_next_action": "Review research signals and qualify based on evidence.",
                "recommended_sales_angle": "Lead with operational intelligence based on recent "
                "signals.",
                "confidence_score": min(len(collected_signals) * 4, 60),
                "recent_signals": signal_dicts,
                "sources": [s.url for s in collected_signals if s.url],
                "evidence": [
                    {
                        "claim": s.summary or s.title,
                        "source_url": s.url,
                    }
                    for s in collected_signals
                    if s.url
                ],
            }

        try:
            response = await self._ai.generate(
                AIRequest(
                    messages=[
                        AIMessage(role="system", content=_EVIDENCE_SYNTHESIS_PROMPT),
                        AIMessage(role="user", content=user_prompt),
                    ],
                    temperature=0.2,
                    max_tokens=800,
                    metadata={"agent": "research"},
                )
            )
            parsed = _parse_json_object(response.content)
            if parsed is not None:
                logger.info(
                    "[AI SYNTHESIS] success=true company=%s signals=%s",
                    company_name, len(collected_signals),
                )
                return parsed

            # LLM returned unparseable text (e.g. degraded response)
            logger.warning(
                "[AI SYNTHESIS] success=false — unparseable response. "
                "[FALLBACK] preserving evidence signals=%s company=%s",
                len(collected_signals), company_name,
            )
            return _build_fallback()

        except (ProviderError, Exception):
            logger.warning(
                "[AI SYNTHESIS] success=false — provider error. "
                "[FALLBACK] preserving evidence signals=%s company=%s",
                len(collected_signals), company_name,
            )
            return _build_fallback()


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
