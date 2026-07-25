"""Tests for research synthesis normalization / quality gates."""

from __future__ import annotations

from app.intelligence.signal_collector import ResearchSignal
from app.intelligence.synthesis_normalize import (
    clean_text,
    evidence_based_extraction,
    looks_like_article_dump,
    normalize_and_validate_findings,
    normalize_buying_signals,
    normalize_company_overview,
    normalize_pain_points,
    validate_synthesis_quality,
)


def _sig(
    title: str,
    url: str,
    summary: str,
    category: str = "company_news",
) -> ResearchSignal:
    return ResearchSignal(
        title=title,
        url=url,
        summary=summary,
        category=category,
        source_type="public_web",
    )


class TestCleanText:
    def test_strips_markdown_heading(self) -> None:
        assert not clean_text("## Future Outlook: BHP").startswith("##")

    def test_rejects_article_dump_heuristic(self) -> None:
        dump = "## Future Outlook: Translating BHP AI Infrastructure " + ("word " * 80)
        assert looks_like_article_dump(dump) is True


class TestNormalizeCompanyOverview:
    def test_does_not_merge_multiple_articles(self) -> None:
        signals = [
            _sig(
                "About BHP",
                "https://www.bhp.com/about",
                "BHP is a global resources company producing iron ore and copper.",
                "company_overview",
            ),
            _sig(
                "Forbes feature",
                "https://www.forbes.com/bhp",
                "Forbes long narrative about market dynamics " + ("x " * 50),
                "industry_article",
            ),
        ]
        dirty = {
            "description": (
                "BHP is a global resources company. "
                "## Future Outlook: Translating BHP AI Infrastructure into "
                "Operational Excellence across sites with detailed Forbes analysis "
                + ("paragraph " * 40)
            ),
            "industry": "Mining",
        }
        overview = normalize_company_overview(
            dirty,
            company_name="BHP",
            domain="bhp.com",
            findings=dirty,
            signals=signals,
        )
        assert overview["description"]
        assert "##" not in overview["description"]
        assert "Forbes" not in overview["description"]
        assert "industry" in overview
        assert "size_location" in overview or overview.get("location") is not None


class TestPainAndBuying:
    def test_rejects_description_like_pain(self) -> None:
        raw = [
            {
                "pain_point": (
                    "BHP is a leading global miner headquartered in Melbourne "
                    "founded in the 1800s with diversified assets worldwide."
                ),
                "evidence": "about page",
                "source_url": "https://www.bhp.com/about",
            }
        ]
        signals = [
            _sig(
                "Manual inspections remain high risk",
                "https://www.bhp.com/safety",
                "Safety programs aim to reduce manual inspection exposure.",
                "safety_incident",
            )
        ]
        pains = normalize_pain_points(raw, signals)
        assert pains
        assert all("is a leading" not in p["pain_point"].lower() for p in pains)
        assert all(p.get("source_url") for p in pains)

    def test_rejects_article_buying_signal(self) -> None:
        raw = [
            {
                "signal": "## Market Analysis\n\n" + ("long article body " * 40),
                "evidence": "dump",
                "source_url": "https://www.bhp.com/news",
            }
        ]
        signals = [
            _sig(
                "BHP invests in autonomous haulage",
                "https://www.bhp.com/news/auto",
                "Automation investment across Pilbara operations.",
                "automation_investment",
            )
        ]
        buying = normalize_buying_signals(raw, signals)
        assert buying
        assert all("##" not in b["signal"] for b in buying)
        assert all(len(b["signal"]) < 250 for b in buying)


class TestValidateAndRebuild:
    def test_invalid_llm_output_rebuilt_from_evidence(self) -> None:
        signals = [
            _sig(
                "BHP global mining overview",
                "https://www.bhp.com/about",
                "BHP is a global resources company with iron ore and copper operations.",
                "company_overview",
            ),
            _sig(
                "Manual inspections risk",
                "https://www.bhp.com/safety",
                "Reducing manual inspection exposure improves safety.",
                "safety_incident",
            ),
            _sig(
                "Autonomy investment",
                "https://www.bhp.com/auto",
                "BHP invests in autonomous haulage and remote operations.",
                "automation_investment",
            ),
        ]
        dirty = {
            "description": "## Future Outlook\n\n" + ("article " * 100),
            "operational_pain_points": [
                {
                    "pain_point": "## Future Outlook: Translating BHP AI Infrastructure "
                    + ("x " * 80),
                    "evidence": "dump",
                    "source_url": "https://www.bhp.com",
                }
            ],
            "buying_signals": [
                {
                    "signal": "### Market\n\n" + ("long " * 80),
                    "source_url": "https://www.bhp.com",
                }
            ],
            "latest_news": [],
            "recent_signals": [],
            "evidence": [],
        }
        assert validate_synthesis_quality(dirty)  # has problems before normalize

        clean = normalize_and_validate_findings(
            dirty,
            company_name="BHP",
            domain="bhp.com",
            collected_signals=signals,
            inbound_context="exploring drone automation",
        )
        assert clean["company_overview"]["description"]
        assert "##" not in clean["company_overview"]["description"]
        assert clean["operational_pain_points"]
        for p in clean["operational_pain_points"]:
            assert "pain_point" in p and "source_url" in p
        assert clean["buying_signals"]
        assert all("signal" in b and "source_url" in b for b in clean["buying_signals"])
        assert clean["latest_news"]
        assert clean["evidence"]
        assert clean.get("next_action") or clean.get("recommended_next_action")

    def test_evidence_based_extraction_complete_schema(self) -> None:
        signals = [
            _sig(
                "About",
                "https://www.bhp.com/about",
                "BHP produces iron ore and copper globally.",
                "company_overview",
            ),
            _sig(
                "Safety automation",
                "https://www.bhp.com/safety",
                "Automation reduces manual inspection risk.",
                "safety_incident",
            ),
            _sig(
                "Digital investment",
                "https://www.bhp.com/digital",
                "Investment in digital transformation and AI.",
                "technology_announcement",
            ),
        ]
        out = evidence_based_extraction(
            company_name="BHP",
            domain="bhp.com",
            collected_signals=signals,
            inbound_context="drone automation for mining",
        )
        for key in (
            "company_overview",
            "latest_news",
            "operational_pain_points",
            "buying_signals",
            "recent_signals",
            "evidence",
            "why_now",
            "recommended_sales_angle",
            "flytbase_fit",
            "next_action",
        ):
            assert key in out
        assert out["evidence"]
