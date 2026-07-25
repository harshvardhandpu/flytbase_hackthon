"""Signal collection layer — runs targeted web searches for specific evidence
categories and structures the results as typed ``ResearchSignal`` objects.

The ``SignalCollector`` is designed to be called **before** the LLM
synthesis step so that DeepSeek receives structured, categorised evidence
instead of raw search results.  Every signal carries a source URL — no
hallucinated facts.

LinkedIn and other social scrapes are intentionally excluded (hackathon-safe
public sources only).
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from app.tools.tool_manager import ToolManager

logger = logging.getLogger(__name__)

# ── Blocked host patterns (LinkedIn + generic social scrapes) ──────────
_BLOCKED_HOST_FRAGMENTS: tuple[str, ...] = (
    "linkedin.com",
    "lnkd.in",
    "twitter.com",
    "x.com",
    "facebook.com",
    "fb.com",
    "instagram.com",
    "tiktok.com",
    "threads.net",
    "reddit.com",
    "youtube.com",
    "youtu.be",
)

_PLACEHOLDER_HOST_FRAGMENTS: tuple[str, ...] = (
    "example.com",
    "example.org",
    "example.net",
    "placeholder.",
)

# Prefer public, citable sources over thin pages
_SOURCE_TYPE_HINTS: list[tuple[str, str]] = [
    (r"(investors?|ir\.|/investor)", "investor_relations"),
    (r"(sec\.gov|asx\.com|edgar|regulatory|filing)", "regulatory_filing"),
    (r"(safety|incident|accident|msahs|osha)", "safety_report"),
    (
        r"(press|newsroom|media-release|newswire|prnewswire|businesswire|"
        r"globenewswire)",
        "press_release",
    ),
    (r"(technology|automation|digital|robotics|drone)", "technology_announcement"),
    (
        r"(mining\.com|mining-technology|reuters|bloomberg|ft\.com|wsj\.com|"
        r"afr\.com)",
        "industry_publication",
    ),
]


class ResearchSignal(BaseModel):
    """A single piece of evidence collected during company research.

    Every signal has a ``url`` that backs the claim — agents must
    not fabricate signals.
    """

    title: str
    """Headline / article title."""

    url: str
    """Source URL for the signal."""

    date: str | None = None
    """Date of the signal (YYYY-MM-DD or free text like \"June 2026\")."""

    summary: str
    """Short 1-2 sentence summary of the signal."""

    category: str = Field(
        description=(
            "One of: company_overview, company_news, press_release, "
            "industry_article, safety_incident, technology_announcement, "
            "automation_investment, expansion, hiring, partnership"
        )
    )
    """Evidence category for downstream qualification weighting."""

    source_type: str = "public_web"
    """Source class: official_website, investor_relations, press_release, etc."""


# ── Category-targeted search templates (public sources only) ───────────
# Intentionally avoid LinkedIn / social. Prefer company sites, IR, press,
# industry pubs, regulatory filings, safety reports, tech announcements.

_CATEGORY_QUERIES: dict[str, str] = {
    # Overview first — grounds company description / industry / ops
    "company_overview": (
        "{query} company overview OR about OR operations OR headquarters "
        "OR business model -site:linkedin.com -site:twitter.com"
    ),
    "company_news": (
        "{query} company news OR newsroom 2025 OR 2026 "
        "-site:linkedin.com -site:twitter.com"
    ),
    "press_release": (
        "{query} press release OR announcement OR newsroom "
        "-site:linkedin.com -site:facebook.com"
    ),
    "industry_article": (
        "{query} industry report OR analysis OR operations technology "
        "-site:linkedin.com"
    ),
    "safety_incident": (
        "{query} safety incident OR accident OR safety report OR fatality "
        "OR regulatory -site:linkedin.com"
    ),
    "technology_announcement": (
        "{query} technology platform OR automation launch OR digital "
        "transformation OR drone OR remote operations -site:linkedin.com"
    ),
    "automation_investment": (
        "{query} automation investment OR autonomous OR AI operations OR "
        "fleet automation OR robotics investment -site:linkedin.com"
    ),
    "expansion": (
        "{query} expansion OR new project OR market entry OR operations "
        "growth -site:linkedin.com"
    ),
    "hiring": (
        "{query} careers OR hiring OR jobs automation OR robotics engineer "
        "-site:linkedin.com"
    ),
    "partnership": (
        "{query} partnership OR collaboration OR alliance OR joint venture "
        "-site:linkedin.com"
    ),
}

# Rank categories for synthesis (higher first)
_CATEGORY_RANK: dict[str, int] = {
    "company_overview": 105,
    "automation_investment": 100,
    "technology_announcement": 95,
    "safety_incident": 90,
    "expansion": 85,
    "partnership": 80,
    "press_release": 75,
    "company_news": 72,
    "industry_article": 65,
    "hiring": 60,
}


def _host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:  # noqa: BLE001
        return ""


def is_blocked_url(url: str) -> bool:
    """True for LinkedIn, social-only, or placeholder domains."""
    if not url or not isinstance(url, str):
        return True
    host = _host_of(url)
    if not host:
        return True
    for frag in _BLOCKED_HOST_FRAGMENTS:
        if frag in host:
            return True
    for frag in _PLACEHOLDER_HOST_FRAGMENTS:
        if frag in host:
            return True
    # Reject bare example-style simulated hosts
    if host.endswith(".example") or ".example." in host:
        return True
    return False


def infer_source_type(url: str, category: str) -> str:
    """Classify a public URL into a source_type bucket."""
    lower = (url or "").lower()
    for pattern, source_type in _SOURCE_TYPE_HINTS:
        if re.search(pattern, lower):
            return source_type
    # Category-based defaults
    if category == "press_release":
        return "press_release"
    if category == "safety_incident":
        return "safety_report"
    if category in ("technology_announcement", "automation_investment"):
        return "technology_announcement"
    if category == "industry_article":
        return "industry_publication"
    host = _host_of(url)
    if host and not any(x in host for x in ("news", "media", "tech", "report")):
        # Likely company domain pages (about, IR, blog)
        return "official_website"
    return "public_web"


def is_empty_result(item: dict) -> bool:
    """Reject empty / useless search hits."""
    title = (item.get("title") or "").strip()
    snippet = (item.get("snippet") or item.get("content") or "").strip()
    url = (item.get("url") or "").strip()
    if not url:
        return True
    if not title and not snippet:
        return True
    if len(title) < 3 and len(snippet) < 20:
        return True
    return False


def rank_signals(signals: list[ResearchSignal]) -> list[ResearchSignal]:
    """Rank signals for synthesis: high-value categories first, then denser summaries."""

    def _score(s: ResearchSignal) -> tuple[int, int, int]:
        cat = _CATEGORY_RANK.get(s.category, 50)
        summary_len = min(len(s.summary or ""), 300)
        # Prefer investor / regulatory / press over generic
        type_bonus = {
            "investor_relations": 30,
            "regulatory_filing": 28,
            "safety_report": 26,
            "press_release": 24,
            "technology_announcement": 22,
            "industry_publication": 18,
            "official_website": 15,
        }.get(s.source_type, 0)
        return (cat + type_bonus, summary_len, 0)

    return sorted(signals, key=_score, reverse=True)


class SignalCollector:
    """Run targeted searches across signal categories and return structured
    evidence.

    The collector encapsulates the search-and-structure logic so the
    ResearchAgent (and future agents) can reuse it without duplicating
    query templates or category logic.
    """

    def __init__(self, tool_manager: ToolManager) -> None:
        self._tools = tool_manager

    async def collect(
        self,
        *,
        company_name: str,
        domain: str | None = None,
        max_signals_per_category: int = 3,
        max_total_signals: int = 20,
    ) -> list[ResearchSignal]:
        """Run targeted searches for each signal category.

        Args:
            company_name: Target company name.
            domain: Optional company domain (used as fallback query).
            max_signals_per_category: Max signals to keep per category.
            max_total_signals: Cap after ranking (for synthesis context).

        Returns:
            Ranked list of ``ResearchSignal`` objects (LinkedIn filtered out).
        """
        query = company_name or domain or ""
        if not query:
            logger.warning("[SEARCH] SignalCollector skipped — empty company_name/domain")
            return []

        signals: list[ResearchSignal] = []
        seen_urls: set[str] = set()
        rejected = {"linkedin": 0, "placeholder": 0, "empty": 0, "duplicate": 0}

        for category, query_template in _CATEGORY_QUERIES.items():
            search_query = query_template.format(query=query)

            try:
                result = await self._tools.execute(
                    "web_search",
                    {"query": search_query, "max_results": max_signals_per_category + 2},
                )
                page_results = result.content.get("results", [])
                logger.info(
                    "[SEARCH] category=%s results_count=%s simulated=%s",
                    category,
                    len(page_results),
                    bool(result.content.get("simulated")),
                )
            except ValueError as exc:
                logger.warning(
                    "[SEARCH] category=%s tool_error reason=%s",
                    category,
                    str(exc)[:160],
                )
                page_results = []

            kept_for_category = 0
            for item in page_results:
                if kept_for_category >= max_signals_per_category:
                    break

                url = (item.get("url") or "").strip()
                if not url:
                    rejected["empty"] += 1
                    continue

                # Normalize for dedupe (strip trailing slash / fragment)
                url_key = url.split("#")[0].rstrip("/").lower()
                if url_key in seen_urls:
                    rejected["duplicate"] += 1
                    continue

                if is_blocked_url(url):
                    host = _host_of(url)
                    if any(f in host for f in ("linkedin", "lnkd")):
                        rejected["linkedin"] += 1
                    else:
                        rejected["placeholder"] += 1
                    continue

                if is_empty_result(item):
                    rejected["empty"] += 1
                    continue

                seen_urls.add(url_key)
                source_type = infer_source_type(url, category)
                signals.append(
                    ResearchSignal(
                        title=(item.get("title") or "Untitled").strip()[:300],
                        url=url,
                        date=item.get("published_date") or item.get("date"),
                        summary=(item.get("snippet") or item.get("content") or "")[:300],
                        category=category,
                        source_type=source_type,
                    )
                )
                kept_for_category += 1

        ranked = rank_signals(signals)[:max_total_signals]
        logger.info(
            "[SEARCH] SignalCollector complete company=%s signals_count=%s "
            "unique_sources=%s rejected=%s",
            company_name or domain,
            len(ranked),
            len(seen_urls),
            rejected,
        )
        return ranked

    # ── Convenience helpers ────────────────────────────────────────────

    @staticmethod
    def signals_by_category(signals: list[ResearchSignal]) -> dict[str, list[ResearchSignal]]:
        """Group signals by their ``category`` field."""
        grouped: dict[str, list[ResearchSignal]] = {}
        for s in signals:
            grouped.setdefault(s.category, []).append(s)
        return grouped

    @staticmethod
    def format_signals_for_prompt(
        signals: list[ResearchSignal],
        *,
        max_signals: int = 20,
    ) -> str:
        """Format top ranked signals compactly for an LLM prompt.

        Each signal is rendered as a short block with title, category,
        summary, and URL only (no long page dumps).
        """
        if not signals:
            return "No signals collected."

        lines: list[str] = []
        for i, s in enumerate(rank_signals(signals)[:max_signals], start=1):
            lines.append(f"{i}. [{s.category}] {s.title}")
            lines.append(f"   URL: {s.url}")
            lines.append(f"   Summary: {(s.summary or '')[:200]}")
            if s.source_type:
                lines.append(f"   Source type: {s.source_type}")
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def signals_as_compact_dicts(
        signals: list[ResearchSignal],
        *,
        max_signals: int = 20,
    ) -> list[dict[str, str | None]]:
        """Top signals as compact dicts for synthesis (title/summary/category/url)."""
        out: list[dict[str, str | None]] = []
        for s in rank_signals(signals)[:max_signals]:
            out.append(
                {
                    "title": s.title,
                    "url": s.url,
                    "date": s.date,
                    "summary": (s.summary or "")[:200],
                    "category": s.category,
                    "source_type": s.source_type,
                }
            )
        return out
