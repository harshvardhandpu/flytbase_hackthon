"""BDR research agent — gathers and synthesises company intelligence.

Architecture (unchanged):
  ResearchAgent
    → SignalCollector (category-targeted public web search via ToolManager)
    → WebSearchTool (Tavily + simulated fallback)
    → optional extract_web_content on top URLs
    → LLM synthesis (DeepSeek/provider-neutral AIProvider)
    → evidence-preserving fallback if synthesis fails

Every claim should reference a source URL. LinkedIn is excluded at the
SignalCollector layer (public sources only).
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

# Compact synthesis context — top ranked signals only (no raw page dumps).
_MAX_SYNTHESIS_SIGNALS = 18
_SYNTHESIS_MAX_TOKENS = 1600
_SYNTHESIS_TEMPERATURE = 0.1

# Full enterprise BDR intelligence schema for synthesis.
_EVIDENCE_SYNTHESIS_PROMPT = """\
You are a senior BDR intelligence analyst for FlytBase (enterprise drone fleet
automation and remote operations).

You receive **collected research signals** from public web sources only
(company sites, press releases, industry publications, IR/regulatory pages,
safety reports, technology announcements). LinkedIn/social scrapes are excluded.

Produce a complete, enterprise-grade BDR intelligence report for the company.

CRITICAL RULES:
1. NEVER invent facts, dates, numbers, or URLs.
2. Use ONLY the provided research signals (and optional inbound context).
3. Every pain point and buying signal MUST include a source_url from signals.
4. Every latest_news / recent_signals item MUST include a real url from signals.
5. Do NOT return empty arrays when evidence exists — map signals into the
   closest fields.
6. If a field is unknown from evidence, use null or a short honest statement
   such as "Not found in collected public evidence" — do not fabricate.
7. Prefer themes relevant to FlytBase when present: automation, remote ops,
   inspection, safety, site monitoring, digital transformation, drones.

Return ONLY valid JSON (no markdown, no commentary) matching this schema:
{
  "company_name": "Full company name",
  "domain": "Primary domain if known",
  "description": "2-4 sentence company overview from evidence",
  "industry": "Industry classification or null",
  "business_model": "How they make money / operate, from evidence, or null",
  "major_operations": "Key operations / assets / lines of business, or null",
  "geographic_presence": "HQ and key regions if evidenced, or null",
  "employee_count": null,
  "location": "HQ location if evidenced, or null",
  "company_situation": "2-3 sentences on current business situation",
  "latest_news": [
    {
      "title": "Headline from a signal",
      "url": "URL from signals",
      "date": "Date if known else null",
      "summary": "1-2 sentence summary",
      "category": "company_news"
    }
  ],
  "operational_pain_points": [
    {
      "pain_point": "Specific operational problem",
      "evidence": "Quote or paraphrase from a signal",
      "source_url": "URL from signals"
    }
  ],
  "buying_signals": [
    {
      "signal": "Specific buying / adoption / investment signal",
      "evidence": "Quote or paraphrase from a signal",
      "source_url": "URL from signals"
    }
  ],
  "business_signals": [
    {
      "signal": "Business/growth signal",
      "category": "company_news|expansion|hiring|automation_investment|partnership|press_release",
      "source_url": "URL from signals",
      "summary": "Short summary",
      "date": "Date or null"
    }
  ],
  "recent_signals": [
    {
      "title": "Signal title",
      "url": "URL from signals",
      "date": "Date or null",
      "summary": "Short summary",
      "category": "category from evidence",
      "source_type": "source type if known"
    }
  ],
  "technology_signals": ["Tech / platform signals from evidence"],
  "pain_points": ["Short pain labels derived from evidence"],
  "why_now": "2-3 sentences on outreach urgency from evidence + inbound context",
  "flytbase_relevance": "High/Medium/Low — explanation grounded in evidence",
  "flytbase_fit": "Which FlytBase capabilities map to evidenced needs",
  "recommended_next_action": "Concrete BDR next step",
  "recommended_sales_angle": "Specific sales angle for the BDR",
  "confidence_score": 0,
  "sources": ["Unique source URLs used"],
  "evidence": [
    {"claim": "Specific claim", "source_url": "URL from signals"}
  ]
}

confidence_score is 0-100 based on evidence quality and coverage.
Include up to 10 latest_news items and up to 15 recent_signals when evidence supports it.
latest_news should prioritize company announcements, press, IR, industry and tech news.
"""


class ResearchAgent(BaseAgent):
    """BDR research agent — evidence-backed company intelligence.

    Workflow:
    1. Collect category-targeted public web signals (no LinkedIn)
    2. Light extraction from top URLs
    3. Synthesise full BDR report via LLM
    4. On failure, preserve collected Tavily evidence in structured fallback
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
        inbound_context = (
            task.input_data.get("inbound_message")
            or task.input_data.get("message_content")
            or task.input_data.get("message")
            or ""
        )
        if isinstance(inbound_context, dict):
            inbound_context = inbound_context.get("body") or inbound_context.get("content") or ""

        # ── Step 1: Start ──────────────────────────────────────────────
        self._tm.append_log(
            task_id, "info", "research_started",
            f"Starting evidence-backed research for {company_name!r} domain={domain!r}",
            {"company_name": company_name, "domain": domain},
        )

        # ── Step 2: Collect structured evidence signals ────────────────
        self._tm.append_log(
            task_id, "info", "signal_collection_started",
            f"Collecting category-targeted public evidence signals for {company_name!r}",
            {"company_name": company_name, "domain": domain},
        )

        collector = SignalCollector(self._tools)
        collected_signals = await collector.collect(
            company_name=company_name,
            domain=domain,
            max_signals_per_category=3,
            max_total_signals=_MAX_SYNTHESIS_SIGNALS,
        )

        all_sources: list[str] = [s.url for s in collected_signals]

        self._tm.append_log(
            task_id, "info", "signal_collection_completed",
            f"Collected {len(collected_signals)} signals from {len(all_sources)} sources",
            {"signal_count": len(collected_signals), "source_count": len(all_sources)},
        )

        logger.info(
            "[RESEARCH] signals_received=%s company=%s",
            len(collected_signals),
            company_name,
        )

        # ── Step 3: Light extraction from top sources ──────────────────
        self._tm.append_log(
            task_id, "info", "extraction_started",
            "Extracting content from top signal sources (cap=5)",
            {"source_count": min(5, len(all_sources))},
        )

        seen_urls: set[str] = set()
        content_texts: list[str] = []

        for source_url in all_sources[:5]:
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
                text = (page.get("text") or "")[:500]
                if text.strip():
                    snippet = f"--- {page.get('title', source_url)} ---\n{text}"
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

        # ── Step 4: Synthesise full BDR intelligence report ─────────────
        self._tm.append_log(
            task_id, "info", "synthesis_started",
            "Synthesising enterprise BDR intelligence report via LLM",
        )

        findings = await self._synthesize_report(
            company_name=company_name,
            domain=domain,
            collected_signals=collected_signals,
            inbound_context=str(inbound_context)[:800] if inbound_context else "",
            task_id=task_id,
        )

        evidence = findings.get("evidence", [])
        sources = findings.get("sources") or all_sources

        # ── Step 5: Build report output ────────────────────────────────
        report_id = uuid.uuid4()

        self._tm.append_log(
            task_id, "info", "report_created",
            f"Research report created (id={report_id}) with {len(evidence)} evidence items",
            {"report_id": str(report_id), "evidence_count": len(evidence)},
        )

        summary = findings.get(
            "description", f"Research completed for {company_name or domain}"
        )
        recent_raw = findings.get("recent_signals", [])
        recent_signals = [_normalize_recent_signal(s) for s in recent_raw]
        latest_news = [
            _normalize_news_item(n)
            for n in (findings.get("latest_news") or [])
        ]
        # If model omitted latest_news, derive from recent company/press signals
        if not latest_news and recent_signals:
            latest_news = [
                {
                    "title": s.get("title", ""),
                    "url": s.get("url", ""),
                    "date": s.get("date"),
                    "summary": s.get("summary", ""),
                    "category": "company_news",
                }
                for s in recent_signals
                if s.get("category") in (
                    "company_news",
                    "press_release",
                    "company_overview",
                    "industry_article",
                    "technology_announcement",
                )
            ][:10]
            if not latest_news:
                latest_news = [
                    {
                        "title": s.get("title", ""),
                        "url": s.get("url", ""),
                        "date": s.get("date"),
                        "summary": s.get("summary", ""),
                        "category": "company_news",
                    }
                    for s in recent_signals[:8]
                ]

        report_data = {
            "company_name": findings.get("company_name", company_name),
            "domain": findings.get("domain", domain),
            "industry": findings.get("industry"),
            "business_model": findings.get("business_model"),
            "major_operations": findings.get("major_operations"),
            "geographic_presence": findings.get("geographic_presence"),
            "employee_count": findings.get("employee_count"),
            "location": findings.get("location"),
            "description": findings.get("description"),
            "company_overview": {
                "description": findings.get("description"),
                "industry": findings.get("industry"),
                "business_model": findings.get("business_model"),
                "major_operations": findings.get("major_operations"),
                "geographic_presence": findings.get("geographic_presence"),
                "employee_count": findings.get("employee_count"),
                "location": findings.get("location"),
            },
            "latest_news": latest_news,
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
            "recommended_next_action": findings.get("recommended_next_action", "")
            or findings.get("next_action", ""),
            "next_action": findings.get("next_action")
            or findings.get("recommended_next_action", ""),
            "recommended_sales_angle": findings.get("recommended_sales_angle", ""),
            "confidence_score": findings.get("confidence_score", 0),
            "recent_signals": recent_signals,
            "sources": sources,
        }

        output_data: dict[str, Any] = {
            "report_id": str(report_id),
            "findings": report_data,
            "evidence": evidence,
            "intelligence_metadata": {
                "analysis_version": "3.2",
                "signal_count": len(collected_signals),
                "source_count": len(all_sources),
                "extraction_count": len(content_texts),
                "evidence_count": len(evidence),
                "latest_news_count": len(latest_news),
            },
            "providers_used": getattr(self._ai, "name", "unknown"),
        }

        # ── Step 6: Complete ────────────────────────────────────────────
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
        inbound_context: str,
        task_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Synthesise collected evidence into a full BDR intelligence report.

        Sends only top ranked signals (compact fields) to the LLM to reduce
        truncation/parse failures.  On any failure, falls back to a report
        that preserves all collected Tavily evidence.
        """
        del task_id  # reserved for future step logging inside synthesis
        ranked = SignalCollector.signals_as_compact_dicts(
            collected_signals, max_signals=_MAX_SYNTHESIS_SIGNALS
        )
        signals_text = SignalCollector.format_signals_for_prompt(
            collected_signals, max_signals=_MAX_SYNTHESIS_SIGNALS
        )

        inbound_block = ""
        if inbound_context.strip():
            inbound_block = (
                "\n=== Inbound lead context (use for why_now / sales angle only; "
                "do not invent facts beyond signals) ===\n"
                f"{inbound_context.strip()}\n"
            )

        user_prompt = (
            f"Company: {company_name or 'Unknown'}\n"
            f"Domain: {domain or 'Unknown'}\n"
            f"Signal count: {len(ranked)}\n"
            f"{inbound_block}\n"
            f"=== Research Signals (ONLY evidence you may use) ===\n"
            f"{signals_text}\n"
            "Synthesise a complete BDR intelligence report as specified JSON.\n"
            "Include company overview fields, latest_news, operational_pain_points, "
            "buying_signals, and recent_signals whenever evidence exists.\n"
            "Do not invent facts. Return ONLY valid JSON."
        )

        logger.info(
            "[AI SYNTHESIS] started=true company=%s signals=%s max_tokens=%s",
            company_name,
            len(ranked),
            _SYNTHESIS_MAX_TOKENS,
        )

        try:
            response = await self._ai.generate(
                AIRequest(
                    messages=[
                        AIMessage(role="system", content=_EVIDENCE_SYNTHESIS_PROMPT),
                        AIMessage(role="user", content=user_prompt),
                    ],
                    temperature=_SYNTHESIS_TEMPERATURE,
                    max_tokens=_SYNTHESIS_MAX_TOKENS,
                    metadata={"agent": "research"},
                )
            )
            # Provider may return a degraded text body after exhausted retries
            is_degraded = (response.raw_metadata or {}).get("status") == "degraded"
            parsed = None if is_degraded else _parse_json_object(response.content)
            if parsed is not None:
                logger.info(
                    "[AI SYNTHESIS] provider=%s success=true fallback=false company=%s",
                    getattr(self._ai, "name", "unknown"),
                    company_name,
                )
                return _merge_synthesis_with_evidence(
                    parsed,
                    company_name=company_name,
                    domain=domain,
                    collected_signals=collected_signals,
                    inbound_context=inbound_context,
                )

            reason = "degraded_provider" if is_degraded else "unparseable"
            logger.warning(
                "[AI SYNTHESIS] provider=%s success=false fallback=true "
                "reason=%s company=%s",
                getattr(self._ai, "name", "unknown"),
                reason,
                company_name,
            )
            logger.info(
                "[FALLBACK] preserving_evidence count=%s company=%s",
                len(collected_signals),
                company_name,
            )
            return _build_fallback(
                company_name=company_name,
                domain=domain,
                collected_signals=collected_signals,
                inbound_context=inbound_context,
            )

        except (ProviderError, Exception) as exc:
            logger.warning(
                "[AI SYNTHESIS] provider=%s success=false fallback=true "
                "reason=%s company=%s",
                getattr(self._ai, "name", "unknown"),
                type(exc).__name__,
                company_name,
            )
            logger.info(
                "[FALLBACK] preserving_evidence count=%s company=%s",
                len(collected_signals),
                company_name,
            )
            return _build_fallback(
                company_name=company_name,
                domain=domain,
                collected_signals=collected_signals,
                inbound_context=inbound_context,
            )


# ── synthesis helpers ──────────────────────────────────────────────────


_PAIN_CATEGORIES = frozenset(
    {
        "safety_incident",
        "industry_article",
        "company_news",
        "technology_announcement",
        "company_overview",
    }
)
_BUYING_CATEGORIES = frozenset(
    {
        "expansion",
        "hiring",
        "partnership",
        "automation_investment",
        "technology_announcement",
        "tech_announcement",
        "funding",
        "technology",
        "press_release",
        "company_news",
    }
)
_NEWS_CATEGORIES = frozenset(
    {
        "company_news",
        "press_release",
        "industry_article",
        "technology_announcement",
        "company_overview",
        "expansion",
        "partnership",
        "automation_investment",
    }
)


def _build_fallback(
    *,
    company_name: str,
    domain: str,
    collected_signals: list[ResearchSignal],
    inbound_context: str = "",
) -> dict[str, Any]:
    """Evidence-preserving fallback when LLM synthesis is unavailable."""
    signal_dicts = [
        {
            "title": s.title,
            "url": s.url,
            "source_url": s.url,
            "date": s.date,
            "summary": s.summary,
            "category": s.category,
            "source_type": s.source_type,
        }
        for s in collected_signals
    ]

    derived_pain = _derive_pain_points(collected_signals)
    derived_buying = _derive_buying_signals(collected_signals)
    latest_news = _derive_latest_news(collected_signals)

    # Never leave empty arrays when we have evidence
    if not derived_pain and collected_signals:
        for s in collected_signals[:5]:
            if s.url:
                derived_pain.append(
                    {
                        "pain_point": s.summary if len(s.summary) > 20 else s.title,
                        "evidence": s.summary or s.title,
                        "source_url": s.url,
                    }
                )
    if not derived_buying and collected_signals:
        for s in collected_signals[:5]:
            if s.url and s.category in _BUYING_CATEGORIES:
                derived_buying.append(
                    {
                        "signal": s.summary if len(s.summary) > 15 else s.title,
                        "evidence": s.summary or s.title,
                        "source_url": s.url,
                    }
                )
        if not derived_buying:
            for s in collected_signals[:3]:
                if s.url:
                    derived_buying.append(
                        {
                            "signal": s.title,
                            "evidence": s.summary or s.title,
                            "source_url": s.url,
                        }
                    )

    sources = [s.url for s in collected_signals if s.url]
    evidence = [
        {"claim": s.summary or s.title, "source_url": s.url}
        for s in collected_signals
        if s.url
    ]

    # Build a richer description from overview / news signal snippets
    overview_bits = [
        s.summary or s.title
        for s in collected_signals
        if s.category in ("company_overview", "company_news", "press_release") and s.summary
    ][:3]
    if overview_bits:
        description = " ".join(overview_bits)[:600]
    else:
        description = (
            f"Research completed for {company_name or domain} using "
            f"{len(collected_signals)} public evidence signals. "
            "AI synthesis unavailable; collected signals preserved."
        )

    why_now = (
        f"Public signals indicate automation, safety, expansion, or technology "
        f"activity relevant to {company_name or domain}."
    )
    if inbound_context.strip():
        why_now = (
            f"Inbound interest plus {len(collected_signals)} public signals suggest "
            f"timely outreach for {company_name or domain} around automation and "
            "operational improvement themes."
        )

    return {
        "company_name": company_name,
        "domain": domain,
        "description": description,
        "industry": None,
        "business_model": None,
        "major_operations": None,
        "geographic_presence": None,
        "employee_count": None,
        "location": None,
        "company_situation": (
            f"{company_name or domain} shows recent public activity across "
            f"{len(collected_signals)} signals from company, industry, and "
            "regulatory sources."
        ),
        "latest_news": latest_news,
        "operational_pain_points": derived_pain,
        "buying_signals": derived_buying,
        "business_signals": [
            {
                "signal": s.summary or s.title,
                "category": s.category,
                "source_url": s.url,
                "url": s.url,
                "summary": s.summary or "",
                "date": s.date,
                "source_type": s.source_type,
            }
            for s in collected_signals
            if s.url
        ],
        "pain_points": [p["pain_point"] for p in derived_pain][:5],
        "technology_signals": [
            s.title
            for s in collected_signals
            if s.category in (
                "technology",
                "technology_announcement",
                "tech_announcement",
                "automation_investment",
            )
        ],
        "why_now": why_now,
        "flytbase_relevance": (
            "Review preserved public signals for drone automation and remote "
            "operations fit."
        ),
        "flytbase_fit": (
            "Autonomous inspection, remote operations, and fleet orchestration "
            "when signals mention monitoring, safety, or automation."
        ),
        "recommended_next_action": "Review research signals and qualify based on evidence.",
        "next_action": "Review research signals and qualify based on evidence.",
        "recommended_sales_angle": (
            "Lead with operational intelligence grounded in recent public signals."
        ),
        "confidence_score": min(
            max(len(collected_signals) * 4, 20) if collected_signals else 0,
            70,
        ),
        "recent_signals": signal_dicts,
        "sources": sources,
        "evidence": evidence,
    }


def _derive_latest_news(signals: list[ResearchSignal]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for s in signals:
        if not s.url or s.category not in _NEWS_CATEGORIES:
            continue
        key = s.url.lower().rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        if s.category in ("company_news", "press_release"):
            news_cat = s.category
        else:
            news_cat = "company_news"
        out.append(
            {
                "title": s.title,
                "url": s.url,
                "date": s.date,
                "summary": s.summary or s.title,
                "category": news_cat,
            }
        )
        if len(out) >= 10:
            break
    if not out:
        for s in signals[:8]:
            if not s.url:
                continue
            out.append(
                {
                    "title": s.title,
                    "url": s.url,
                    "date": s.date,
                    "summary": s.summary or s.title,
                    "category": "company_news",
                }
            )
    return out


def _derive_pain_points(signals: list[ResearchSignal]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for s in signals:
        if not s.url or s.category not in _PAIN_CATEGORIES:
            continue
        key = (s.summary or s.title)[:120]
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "pain_point": s.summary if len(s.summary) > 20 else s.title,
                "evidence": s.summary or s.title,
                "source_url": s.url,
            }
        )
    return out


def _derive_buying_signals(signals: list[ResearchSignal]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for s in signals:
        if not s.url or s.category not in _BUYING_CATEGORIES:
            continue
        key = (s.summary or s.title)[:120]
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "signal": s.summary if len(s.summary) > 15 else s.title,
                "evidence": s.summary or s.title,
                "source_url": s.url,
            }
        )
    return out


def _merge_synthesis_with_evidence(
    parsed: dict[str, Any],
    *,
    company_name: str,
    domain: str,
    collected_signals: list[ResearchSignal],
    inbound_context: str = "",
) -> dict[str, Any]:
    """Fill empty LLM fields from collected signals so evidence is never dropped."""
    fallback = _build_fallback(
        company_name=company_name,
        domain=domain,
        collected_signals=collected_signals,
        inbound_context=inbound_context,
    )

    for key in (
        "description",
        "why_now",
        "recommended_sales_angle",
        "company_situation",
        "flytbase_relevance",
        "flytbase_fit",
        "recommended_next_action",
        "industry",
        "location",
        "business_model",
        "major_operations",
        "geographic_presence",
    ):
        if not parsed.get(key) and fallback.get(key):
            parsed[key] = fallback[key]

    if not parsed.get("company_name"):
        parsed["company_name"] = company_name
    if not parsed.get("domain"):
        parsed["domain"] = domain

    for arr_key in (
        "operational_pain_points",
        "buying_signals",
        "recent_signals",
        "latest_news",
        "sources",
        "evidence",
        "business_signals",
        "pain_points",
        "technology_signals",
    ):
        if not parsed.get(arr_key) and fallback.get(arr_key):
            parsed[arr_key] = fallback[arr_key]

    # Normalize buying_signals
    normalized_buying: list[dict[str, Any]] = []
    for item in parsed.get("buying_signals") or []:
        if isinstance(item, str):
            normalized_buying.append(
                {"signal": item, "evidence": item, "source_url": ""}
            )
        elif isinstance(item, dict):
            normalized_buying.append(
                {
                    "signal": item.get("signal") or item.get("title") or "",
                    "evidence": (
                        item.get("evidence")
                        or item.get("summary")
                        or item.get("signal")
                        or ""
                    ),
                    "source_url": item.get("source_url") or item.get("url") or "",
                }
            )
    parsed["buying_signals"] = normalized_buying

    # Normalize latest_news
    normalized_news: list[dict[str, Any]] = []
    for item in parsed.get("latest_news") or []:
        normalized_news.append(_normalize_news_item(item))
    if not normalized_news:
        normalized_news = fallback.get("latest_news") or []
    parsed["latest_news"] = normalized_news

    try:
        score = int(parsed.get("confidence_score") or 0)
    except (TypeError, ValueError):
        score = 0
    if score <= 0 and collected_signals:
        score = min(len(collected_signals) * 4, 75)
    parsed["confidence_score"] = max(0, min(score, 100))

    return parsed


def _normalize_recent_signal(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {
            "title": str(raw) if raw else "",
            "url": "",
            "date": None,
            "summary": "",
            "category": "company_news",
        }
    url = raw.get("url") or raw.get("source_url") or ""
    return {
        "title": raw.get("title", ""),
        "url": url,
        "date": raw.get("date"),
        "summary": raw.get("summary", ""),
        "category": raw.get("category", "company_news"),
        "source_type": raw.get("source_type", "public_web"),
    }


def _normalize_news_item(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {
            "title": str(raw) if raw else "",
            "url": "",
            "date": None,
            "summary": "",
            "category": "company_news",
        }
    return {
        "title": raw.get("title", "") or "",
        "url": raw.get("url") or raw.get("source_url") or "",
        "date": raw.get("date"),
        "summary": raw.get("summary", "") or "",
        "category": raw.get("category") or "company_news",
    }


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
