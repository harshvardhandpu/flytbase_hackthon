"""Signal collection layer — runs targeted web searches for specific evidence
categories and structures the results as typed ``ResearchSignal`` objects.

The ``SignalCollector`` is designed to be called **before** the LLM
synthesis step so that DeepSeek receives structured, categorised evidence
instead of raw search results.  Every signal carries a source URL — no
hallucinated facts.

Usage from ResearchAgent::

    collector = SignalCollector(tool_manager)
    signals = await collector.collect(company_name="Rio Tinto")

    # signals is a list[ResearchSignal] with title, url, date, summary, category

    # Pass into DeepSeek prompt:
    prompt = json.dumps([s.model_dump() for s in signals], indent=2)
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.tools.tool_manager import ToolManager


class ResearchSignal(BaseModel):
    """A single piece of evidence collected during company research.

    Every signal has a ``source_url`` that backs the claim — agents must
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
            "One of: company_news, press_release, industry_article, "
            "safety_incident, technology_announcement, expansion, "
            "hiring, funding, partnership"
        )
    )
    """Evidence category for downstream qualification weighting."""


# ── Category-targeted search templates ─────────────────────────────────
# Each category maps to a search query template.  The ``{query}``
# placeholder is replaced with the company name or domain.

_CATEGORY_QUERIES: dict[str, str] = {
    "company_news": "{query} company news press release 2026",
    "press_release": "{query} press release announcement 2026",
    "industry_article": "{query} industry report analysis 2026",
    "safety_incident": "{query} safety incident accident violation",
    "technology_announcement": "{query} technology platform automation launch 2026",
    "expansion": "{query} expansion new office market entry 2026",
    "hiring": "{query} hiring careers jobs 2026",
    "funding": "{query} funding investment acquisition round",
    "partnership": "{query} partnership collaboration alliance 2026",
}


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
    ) -> list[ResearchSignal]:
        """Run targeted searches for each signal category.

        Args:
            company_name: Target company name.
            domain: Optional company domain (used as fallback query).
            max_signals_per_category: Max signals to return per category.

        Returns:
            A flat list of ``ResearchSignal`` objects sorted by category.
        """
        query = company_name or domain or ""
        if not query:
            return []

        signals: list[ResearchSignal] = []
        seen_urls: set[str] = set()

        for category, query_template in _CATEGORY_QUERIES.items():
            search_query = query_template.format(query=query)

            try:
                result = await self._tools.execute(
                    "web_search",
                    {"query": search_query, "max_results": max_signals_per_category},
                )
                page_results = result.content.get("results", [])
            except ValueError:
                page_results = []

            for item in page_results[:max_signals_per_category]:
                url = item.get("url", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                signals.append(
                    ResearchSignal(
                        title=item.get("title", "Untitled"),
                        url=url,
                        date=None,  # Demos do not parse article dates
                        summary=item.get("snippet", "")[:300],
                        category=category,
                    )
                )

        return signals

    # ── Convenience helpers ────────────────────────────────────────────

    @staticmethod
    def signals_by_category(signals: list[ResearchSignal]) -> dict[str, list[ResearchSignal]]:
        """Group signals by their ``category`` field."""
        grouped: dict[str, list[ResearchSignal]] = {}
        for s in signals:
            grouped.setdefault(s.category, []).append(s)
        return grouped

    @staticmethod
    def format_signals_for_prompt(signals: list[ResearchSignal]) -> str:
        """Format signals as a readable block for an LLM prompt.

        Each signal is rendered as::

            [category] title
            URL: url
            Summary: summary
            Date: date
        """
        if not signals:
            return "No signals collected."

        lines: list[str] = []
        for s in signals:
            lines.append(f"[{s.category}] {s.title}")
            lines.append(f"  URL:     {s.url}")
            lines.append(f"  Summary: {s.summary[:200]}")
            lines.append(f"  Date:    {s.date or 'N/A'}")
            lines.append("")
        return "\n".join(lines)
