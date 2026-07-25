"""Tests for stale ResearchReport detection (cache invalidation)."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.intelligence.research_quality import (
    is_stale_research_report,
    stale_reason,
)


def _fresh_findings(**overrides: object) -> dict:
    base: dict = {
        "company_overview": {
            "description": "Global mining company",
            "industry": "Mining",
        },
        "description": "Global mining company",
        "latest_news": [
            {
                "title": "Autonomy expansion",
                "url": "https://www.bhp.com/news/autonomy",
                "summary": "Autonomous trucks deployed",
                "category": "company_news",
            }
        ],
        "operational_pain_points": [
            {
                "pain_point": "Manual site inspections",
                "evidence": "Safety strategy reduces exposure",
                "source_url": "https://www.bhp.com/safety",
            }
        ],
        "buying_signals": [
            {
                "signal": "Autonomy investment",
                "evidence": "Pilbara program expansion",
                "source_url": "https://www.bhp.com/news/autonomy",
            }
        ],
        "recent_signals": [
            {
                "title": "Autonomy expansion",
                "url": "https://www.bhp.com/news/autonomy",
                "summary": "Autonomous trucks",
                "category": "automation_investment",
            }
        ],
        "evidence": [
            {
                "claim": "Expanding autonomous operations",
                "source_url": "https://www.bhp.com/news/autonomy",
            }
        ],
        "sources": ["https://www.bhp.com/news/autonomy", "https://www.bhp.com/safety"],
    }
    base.update(overrides)
    return base


def _report(findings: dict, sources: list | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        findings=findings,
        sources=sources if sources is not None else [],
        created_at=None,
    )


class TestIsStaleResearchReport:
    def test_fresh_enterprise_report_not_stale(self) -> None:
        report = _report(_fresh_findings())
        assert is_stale_research_report(report) is False

    def test_linkedin_source_is_stale(self) -> None:
        report = _report(
            _fresh_findings(
                sources=["https://au.linkedin.com/company/bhp"],
            )
        )
        assert is_stale_research_report(report) is True
        assert "blocked_sources" in stale_reason(report)
        assert "linkedin.com" in stale_reason(report)

    def test_x_com_source_is_stale(self) -> None:
        report = _report(
            _fresh_findings(sources=["https://x.com/bhp?lang=en"])
        )
        assert is_stale_research_report(report) is True
        assert "x.com" in stale_reason(report)

    def test_twitter_source_is_stale(self) -> None:
        report = _report(
            _fresh_findings(sources=["https://twitter.com/bhp"])
        )
        assert is_stale_research_report(report) is True

    def test_example_com_source_is_stale(self) -> None:
        report = _report(
            _fresh_findings(sources=["https://www.example.com/about"])
        )
        assert is_stale_research_report(report) is True

    def test_box_com_not_false_positive_for_x_com(self) -> None:
        """Host-aware matching must not treat box.com as x.com."""
        report = _report(
            _fresh_findings(sources=["https://www.box.com/s/file"])
        )
        assert is_stale_research_report(report) is False

    def test_missing_company_overview_is_stale(self) -> None:
        findings = _fresh_findings()
        del findings["company_overview"]
        report = _report(findings)
        assert is_stale_research_report(report) is True
        assert "missing_schema" in stale_reason(report)

    def test_missing_latest_news_is_stale(self) -> None:
        findings = _fresh_findings()
        del findings["latest_news"]
        report = _report(findings)
        assert is_stale_research_report(report) is True

    def test_missing_evidence_is_stale(self) -> None:
        findings = _fresh_findings()
        del findings["evidence"]
        report = _report(findings)
        assert is_stale_research_report(report) is True

    def test_long_pain_point_is_stale(self) -> None:
        long_text = "A" * 300
        report = _report(
            _fresh_findings(
                operational_pain_points=[
                    {
                        "pain_point": long_text,
                        "evidence": "x",
                        "source_url": "https://www.bhp.com",
                    }
                ]
            )
        )
        assert is_stale_research_report(report) is True
        assert "raw_pain_points" in stale_reason(report)

    def test_markdown_heading_pain_is_stale(self) -> None:
        report = _report(
            _fresh_findings(
                operational_pain_points=[
                    {
                        "pain_point": "## Future Outlook: Translating BHP AI Infrastructure",
                        "evidence": "dump",
                        "source_url": "https://www.bhp.com",
                    }
                ]
            )
        )
        assert is_stale_research_report(report) is True

    def test_markdown_buying_signal_is_stale(self) -> None:
        report = _report(
            _fresh_findings(
                buying_signals=[
                    {
                        "signal": "## Article dump\n\n**long** markdown body "
                        + ("word " * 80),
                        "source_url": "https://www.bhp.com",
                    }
                ]
            )
        )
        assert is_stale_research_report(report) is True
        assert "dump_buying_signals" in stale_reason(report)

    def test_recent_signal_linkedin_is_stale(self) -> None:
        report = _report(
            _fresh_findings(
                sources=["https://www.bhp.com"],
                recent_signals=[
                    {
                        "title": "Post",
                        "url": "https://www.linkedin.com/posts/1",
                        "summary": "social",
                    }
                ],
            )
        )
        assert is_stale_research_report(report) is True

    def test_evidence_x_com_is_stale(self) -> None:
        report = _report(
            _fresh_findings(
                sources=["https://www.bhp.com"],
                evidence=[
                    {
                        "claim": "tweet",
                        "source_url": "https://x.com/bhp/status/1",
                    }
                ],
            )
        )
        assert is_stale_research_report(report) is True

    def test_report_sources_column_linkedin_is_stale(self) -> None:
        """Blocked URL only in report.sources column must still invalidate."""
        findings = _fresh_findings(sources=["https://www.bhp.com"])
        report = _report(
            findings,
            sources=[{"url": "https://au.linkedin.com/company/bhp"}],
        )
        assert is_stale_research_report(report) is True


class TestProductionStaleBhpShape:
    """Shape matching the production stale report symptoms."""

    def test_production_like_report_is_stale(self) -> None:
        report = _report(
            {
                # old schema — no company_overview / latest_news
                "description": "BHP is a miner",
                "sources": [
                    "https://x.com/bhp?lang=en",
                    "https://au.linkedin.com/company/bhp",
                    "https://www.bhp.com",
                ],
                "pain_points": [
                    "## Future Outlook: Translating BHP AI Infrastructure "
                    "into Operational Excellence across mining sites with "
                    "detailed article body " + ("para " * 40)
                ],
                "buying_signals": [
                    "### Market Analysis\n\n" + ("long article text " * 30)
                ],
                "recent_signals": [],
            }
        )
        assert is_stale_research_report(report) is True
        reason = stale_reason(report)
        assert "blocked_sources" in reason
        assert "missing_schema" in reason
