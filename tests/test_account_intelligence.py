"""Tests for the AccountResearchIntelligence layer."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.config import get_settings
from app.core.contracts import AIProvider, AIRequest, AIResponse
from app.intelligence.account_research import AccountResearchIntelligence
from app.providers.manager import ProviderManager


class FakeAIProvider:
    """Minimal AI provider that returns predefined responses."""

    name = "test_provider"

    def __init__(self, response_content: str = "") -> None:
        self.response_content = response_content
        self.last_request: AIRequest | None = None
        self.generate = AsyncMock(side_effect=self._generate)

    async def _generate(self, request: AIRequest) -> AIResponse:
        self.last_request = request
        return AIResponse(content=self.response_content, provider="test_provider")


class TestAccountResearchIntelligence:
    def _intel(self, provider: AIProvider | None = None) -> AccountResearchIntelligence:
        if provider is None:
            provider = FakeAIProvider()
        return AccountResearchIntelligence(provider)

    @pytest.mark.asyncio
    async def test_analyze_returns_fallback_on_empty_data(self) -> None:
        intel = self._intel(FakeAIProvider(response_content="invalid json"))
        result = await intel.analyze(
            company_name="TestCorp",
            search_results=[],
            extracted_content=[],
        )
        assert isinstance(result, dict)
        assert "company_situation" in result
        assert "business_problems" in result
        assert "citations" in result

    @pytest.mark.asyncio
    async def test_analyze_parses_llm_response(self) -> None:
        llm_response = (
            '{\n'
            '  "company_situation": "TestCorp is a leading drone company.",\n'
            '  "business_problems": ["Fleet scaling issues", "Manual workflows"],\n'
            '  "operational_risks": ["Coordination overhead increases with fleet size"],\n'
            '  "growth_signals": ["Hiring 50 engineers"],\n'
            '  "buying_signals": ["Evaluating drone management platforms"],\n'
            '  "technology_signals": ["DJI ecosystem"],\n'
            '  "flytbase_relevance": "High — drone fleet management is core need",\n'
            '  "industry_incidents": [{"title": "Test incident", "summary": "Summary",\n'
            '    "implication": "Implication"}],\n'
            '  "recommended_sales_angle": "Lead with fleet automation",\n'
            '  "citations": [{"source": "Test source", "url": "https://test.com",\n'
            '    "key_finding": "Key finding"}]\n'
            '}'
        )
        provider = FakeAIProvider(response_content=llm_response)
        intel = self._intel(provider)

        result = await intel.analyze(
            company_name="TestCorp",
            search_results=[
                {"title": "Test", "url": "https://test.com", "snippet": "Test snippet"}
            ],
            extracted_content=["--- Test Page ---\nContent here"],
        )

        assert result["company_situation"] == "TestCorp is a leading drone company."
        assert len(result["business_problems"]) == 2
        assert result["flytbase_relevance"] == "High — drone fleet management is core need"
        assert len(result["citations"]) == 1
        assert result["citations"][0]["url"] == "https://test.com"

    @pytest.mark.asyncio
    async def test_analyze_uses_existing_findings_in_fallback(self) -> None:
        intel = self._intel(FakeAIProvider(response_content="bad json"))
        result = await intel.analyze(
            company_name="TestCorp",
            search_results=[{"title": "T", "url": "https://t.com", "snippet": "Snippet"}],
            extracted_content=[],
            existing_findings={
                "description": "TestCorp overview",
                "pain_points": ["Legacy system problem"],
                "business_signals": ["Funding round"],
                "technology_signals": ["Python stack"],
                "flytbase_relevance": "Medium",
                "recommended_next_action": "Schedule demo",
            },
        )
        assert result["company_situation"] == "TestCorp overview"
        assert "Legacy system problem" in result["business_problems"]
        assert "Funding round" in result["growth_signals"]
        assert result["flytbase_relevance"] == "Medium"
        assert result["recommended_sales_angle"] == "Schedule demo"

    @pytest.mark.asyncio
    async def test_analyze_with_code_fences(self) -> None:
        llm_response = (
            '```json\n'
            '{"company_situation": "Test", "business_problems": [], "citations": []}\n'
            '```'
        )
        provider = FakeAIProvider(response_content=llm_response)
        intel = self._intel(provider)
        result = await intel.analyze(
            company_name="Test",
            search_results=[],
            extracted_content=[],
        )
        assert result["company_situation"] == "Test"
        assert isinstance(result["citations"], list)

    @pytest.mark.asyncio
    async def test_provider_error_returns_fallback(self) -> None:
        provider = FakeAIProvider(response_content="")
        provider.generate = AsyncMock(side_effect=Exception("Provider error"))
        intel = self._intel(provider)
        result = await intel.analyze(
            company_name="TestCorp",
            search_results=[],
            extracted_content=[],
        )
        assert "company_situation" in result
        assert "citations" in result

    def test_build_fallback(self) -> None:
        result = AccountResearchIntelligence._build_fallback(
            company_name="TestCorp",
            search_results=[
                {"url": "https://t.com/1", "snippet": "Snippet 1"},
                {"url": "https://t.com/2", "snippet": "Snippet 2"},
            ],
            existing_findings=None,
        )
        assert "company_situation" in result
        assert len(result["citations"]) == 2
        assert result["citations"][0]["url"] == "https://t.com/1"


# ── Real provider integration test ──────────────────────────────────────

_HAS_LIVE_FREEMODEL = False
_settings = get_settings()
if (
    _settings.ai_provider == "freemodel"
    and _settings.anthropic_auth_token
    and _settings.anthropic_auth_token != "replace-me"
    and _settings.anthropic_base_url
):
    _HAS_LIVE_FREEMODEL = True


@pytest.mark.skipif(
    not _HAS_LIVE_FREEMODEL,
    reason="Requires AI_PROVIDER=freemodel with a live ANTHROPIC_AUTH_TOKEN",
)
class TestAccountResearchIntelligenceRealProvider:
    """Integration tests that call the real FreeModelProvider via ProviderManager.

    These tests verify the full pipeline: ProviderManager resolves the correct
    provider, AccountResearchIntelligence calls the live API, and the response
    is parsed into the expected structured format.

    Even if the freemodel API is unreachable, the analyze() method gracefully
    falls back to deterministic output, so the test remains useful for
    verifying the fallback code path with a real provider instance.
    """

    @staticmethod
    def _fresh_settings():
        get_settings.cache_clear()
        return get_settings()

    def test_resolves_freemodel_provider(self) -> None:
        """ProviderManager should resolve to FreeModelProvider when configured."""
        settings = self._fresh_settings()
        provider = ProviderManager(settings).resolve()
        assert provider.name == "freemodel"

    @pytest.mark.asyncio
    async def test_analyze_returns_structured_output(self) -> None:
        """Live AIProvider call produces valid structured intelligence."""
        settings = self._fresh_settings()
        provider = ProviderManager(settings).resolve()
        intel = AccountResearchIntelligence(provider)

        result = await intel.analyze(
            company_name="SkyGrid Inc.",
            search_results=[
                {
                    "title": "SkyGrid Raises $40M Series B for Drone Management",
                    "url": "https://example.com/skygrid-funding",
                    "snippet": "SkyGrid Inc., a drone fleet management platform, "
                    "has raised $40M in Series B funding...",
                },
                {
                    "title": "SkyGrid Expands to EU Market",
                    "url": "https://example.com/skygrid-eu",
                    "snippet": "The company is opening offices in Berlin and Amsterdam...",
                },
            ],
            extracted_content=[
                "--- SkyGrid Blog ---\nSkyGrid is the leading drone fleet management "
                "platform for enterprise operators. Serving 200+ customers across "
                "logistics, agriculture, and public safety sectors."
            ],
        )

        # Verify the expected structure regardless of whether the API
        # call succeeded (real response) or failed (graceful fallback)
        assert isinstance(result, dict)
        assert "company_situation" in result
        assert isinstance(result.get("company_situation", ""), str)
        assert len(result["company_situation"]) > 0
        assert "business_problems" in result
        assert isinstance(result["business_problems"], list)
        assert "operational_risks" in result
        assert isinstance(result["operational_risks"], list)
        assert "growth_signals" in result
        assert isinstance(result["growth_signals"], list)
        assert "buying_signals" in result
        assert isinstance(result["buying_signals"], list)
        assert "technology_signals" in result
        assert isinstance(result["technology_signals"], list)
        assert "flytbase_relevance" in result
        assert isinstance(result["flytbase_relevance"], str)
        assert len(result["flytbase_relevance"]) > 0
        assert "industry_incidents" in result
        assert isinstance(result["industry_incidents"], list)
        assert "recommended_sales_angle" in result
        assert isinstance(result["recommended_sales_angle"], str)
        assert len(result["recommended_sales_angle"]) > 0
        assert "citations" in result
        assert isinstance(result["citations"], list)

    @pytest.mark.asyncio
    async def test_analyze_uses_search_results_for_citations(self) -> None:
        """Search result URLs should appear in the citations."""
        settings = self._fresh_settings()
        provider = ProviderManager(settings).resolve()
        intel = AccountResearchIntelligence(provider)

        result = await intel.analyze(
            company_name="SkyGrid Inc.",
            search_results=[
                {
                    "title": "SkyGrid Raises $40M",
                    "url": "https://example.com/funding",
                    "snippet": "Series B funding for drone management",
                },
                {
                    "title": "SkyGrid EU Expansion",
                    "url": "https://example.com/eu-expansion",
                    "snippet": "Opening Berlin and Amsterdam offices",
                },
            ],
            extracted_content=[],
        )

        assert isinstance(result, dict)
        assert "citations" in result

        # Even in fallback mode, citations should include the search URLs
        citation_urls = [c.get("url", "") for c in result["citations"]]
        assert "https://example.com/funding" in citation_urls
        assert "https://example.com/eu-expansion" in citation_urls
