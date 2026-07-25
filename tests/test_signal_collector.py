"""Tests for SignalCollector filtering, ranking, and LinkedIn exclusion."""

from __future__ import annotations

from typing import Any

import pytest

from app.core.contracts import ToolResult
from app.intelligence.signal_collector import (
    ResearchSignal,
    SignalCollector,
    is_blocked_url,
    rank_signals,
)
from app.tools.base import BaseTool
from app.tools.tool_manager import ToolManager


class _StubWebSearch(BaseTool):
    name = "web_search"
    description = "stub"

    def __init__(self, results_by_query_substr: dict[str, list[dict[str, str]]]) -> None:
        self._map = results_by_query_substr

    async def execute(self, payload: dict[str, Any]) -> ToolResult:
        query = (payload.get("query") or "").lower()
        results: list[dict[str, str]] = []
        for key, items in self._map.items():
            if key in query:
                results = items
                break
        if not results:
            results = [
                {
                    "title": "Generic",
                    "url": "https://www.example.com/about",
                    "snippet": "placeholder",
                }
            ]
        return ToolResult(
            content={"query": query, "results": results, "result_count": len(results)},
            sources=[r["url"] for r in results],
        )


class TestCategoryQueries:
    def test_includes_company_overview_category(self) -> None:
        from app.intelligence.signal_collector import _CATEGORY_QUERIES

        assert "company_overview" in _CATEGORY_QUERIES
        assert "company_news" in _CATEGORY_QUERIES


class TestUrlBlocking:
    def test_blocks_linkedin(self) -> None:
        assert is_blocked_url("https://www.linkedin.com/company/bhp")
        assert is_blocked_url("https://lnkd.in/abc")

    def test_blocks_social(self) -> None:
        assert is_blocked_url("https://twitter.com/bhp")
        assert is_blocked_url("https://x.com/bhp")
        assert is_blocked_url("https://facebook.com/bhp")
        assert is_blocked_url("https://www.youtube.com/watch?v=abc")

    def test_blocks_example_placeholder(self) -> None:
        assert is_blocked_url("https://www.example.com/about")
        assert is_blocked_url("https://news.example.com/company-updates")

    def test_allows_public_sources(self) -> None:
        assert not is_blocked_url("https://www.bhp.com/news")
        assert not is_blocked_url("https://www.mining.com/story")
        assert not is_blocked_url("https://www.sec.gov/Archives/edgar/data/1")


class TestSignalCollectorFiltering:
    @pytest.mark.asyncio
    async def test_rejects_linkedin_and_example_keeps_public(self) -> None:
        stub = _StubWebSearch(
            {
                "press release": [
                    {
                        "title": "BHP LinkedIn post",
                        "url": "https://www.linkedin.com/company/bhp/posts",
                        "snippet": "Should be rejected",
                    },
                    {
                        "title": "BHP safety report",
                        "url": "https://www.bhp.com/safety/report-2026",
                        "snippet": "Safety improvements at mine sites",
                    },
                    {
                        "title": "Placeholder",
                        "url": "https://www.example.com/about",
                        "snippet": "fake",
                    },
                ],
                "automation": [
                    {
                        "title": "BHP invests in autonomous haulage",
                        "url": "https://www.mining-technology.com/bhp-autonomous",
                        "snippet": "Automation investment across Pilbara operations",
                    },
                ],
            }
        )
        collector = SignalCollector(ToolManager([stub]))
        signals = await collector.collect(company_name="BHP", max_signals_per_category=3)

        urls = [s.url for s in signals]
        assert all("linkedin.com" not in u for u in urls)
        assert all("example.com" not in u for u in urls)
        assert any("bhp.com" in u or "mining-technology.com" in u for u in urls)
        assert all(s.source_type for s in signals)

    @pytest.mark.asyncio
    async def test_dedupes_urls(self) -> None:
        shared = {
            "title": "BHP expansion",
            "url": "https://www.bhp.com/news/expansion",
            "snippet": "New project approved",
        }
        stub = _StubWebSearch(
            {
                "company news": [shared],
                "press release": [shared],
                "expansion": [shared],
            }
        )
        collector = SignalCollector(ToolManager([stub]))
        signals = await collector.collect(company_name="BHP")
        matching = [s for s in signals if "expansion" in s.url]
        assert len(matching) == 1

    def test_rank_prefers_automation_over_hiring(self) -> None:
        signals = [
            ResearchSignal(
                title="Hiring",
                url="https://www.bhp.com/careers",
                summary="Jobs",
                category="hiring",
                source_type="official_website",
            ),
            ResearchSignal(
                title="Automation",
                url="https://www.bhp.com/automation",
                summary="Autonomous trucks and drone inspection programs",
                category="automation_investment",
                source_type="technology_announcement",
            ),
        ]
        ranked = rank_signals(signals)
        assert ranked[0].category == "automation_investment"
