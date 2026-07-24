"""Tests for the WebContentExtractorTool."""

from __future__ import annotations

import pytest

from app.tools.web_extractor import WebContentExtractorTool, _extract_title, _html_to_text


class TestWebContentExtractorTool:
    """Tests for the simulated fallback path of WebContentExtractorTool."""

    @pytest.fixture
    def tool(self) -> WebContentExtractorTool:
        return WebContentExtractorTool(force_simulated=True)

    @pytest.mark.asyncio
    async def test_simulated_extract_known_domain(self, tool: WebContentExtractorTool) -> None:
        result = await tool.execute({"url": "https://www.flytbase.com/about"})
        assert result.content["title"] == "FlytBase — Drone Fleet Management Platform"
        assert "drone fleet management" in result.content["text"].lower()
        assert result.content.get("simulated") is True

    @pytest.mark.asyncio
    async def test_simulated_extract_unknown_domain(self, tool: WebContentExtractorTool) -> None:
        result = await tool.execute({"url": "https://unknown-example.com/page"})
        assert result.content["title"] == "About Us"
        assert "enterprise solutions" in result.content["text"].lower()
        assert result.content.get("simulated") is True

    @pytest.mark.asyncio
    async def test_simulated_extract_empty_url(self, tool: WebContentExtractorTool) -> None:
        result = await tool.execute({"url": ""})
        assert "error" in result.content

    @pytest.mark.asyncio
    async def test_tool_metadata(self, tool: WebContentExtractorTool) -> None:
        assert tool.name == "extract_web_content"
        assert "URL" in tool.description

    @pytest.mark.asyncio
    async def test_extract_has_timestamp(self, tool: WebContentExtractorTool) -> None:
        result = await tool.execute({"url": "https://www.flytbase.com"})
        assert "extracted_at" in result.content


class TestHtmlHelpers:
    """Tests for the HTML extraction helper functions."""

    def test_extract_title_found(self) -> None:
        html = "<html><head><title>Test Page</title></head><body><p>Hello</p></body></html>"
        assert _extract_title(html) == "Test Page"

    def test_extract_title_not_found(self) -> None:
        html = "<html><body><p>No title here</p></body></html>"
        assert _extract_title(html) is None

    def test_html_to_text_strips_tags(self) -> None:
        html = "<p>Hello <b>world</b></p>"
        text = _html_to_text(html)
        assert "Hello" in text
        assert "world" in text
        assert "<b>" not in text

    def test_html_to_text_handles_scripts(self) -> None:
        html = "<p>Visible</p><script>var x = 1;</script><p>Still visible</p>"
        text = _html_to_text(html)
        assert "Visible" in text
        assert "var" not in text


class TestWebContentExtractorRealHttp:
    """Integration tests that perform real HTTP extraction.

    Uses ``https://example.com`` as the test URL — a stable, predictable
    page maintained by IANA that has been online since 1999.
    When the URL is unreachable (no internet / offline), the tool
    gracefully falls back to simulated content; the tests verify
    that at minimum a valid response is returned.
    """

    @pytest.fixture
    def tool(self) -> WebContentExtractorTool:
        # Default mode — tries real HTTP first, falls back to simulated on error
        return WebContentExtractorTool(force_simulated=False)

    @pytest.mark.asyncio
    async def test_real_extract_returns_content(self, tool: WebContentExtractorTool) -> None:
        """Real HTTP extraction should return real content from example.com."""
        result = await tool.execute({"url": "https://example.com"})

        assert result.content["title"]
        assert result.content["text"]
        assert "extracted_at" in result.content
        # If we got a real response, simulated flag should be absent
        if not result.content.get("simulated"):
            assert result.content["title"] == "Example Domain"
            assert result.sources == ["https://example.com"]

    @pytest.mark.asyncio
    async def test_real_extract_has_timestamp(self, tool: WebContentExtractorTool) -> None:
        """Real or fallback, the response should always have an ISO timestamp."""
        result = await tool.execute({"url": "https://example.com"})
        assert "extracted_at" in result.content
        assert "T" in result.content["extracted_at"]  # ISO 8601 format check

    @pytest.mark.asyncio
    async def test_real_extract_fallback_on_bad_url(self) -> None:
        """When the URL is unreachable, the tool should gracefully fall back to simulated."""
        tool = WebContentExtractorTool(force_simulated=False)
        result = await tool.execute({"url": "https://this-domain-does-not-exist-12345.com/page"})
        # Should return content via fallback (not crash) and flag it as simulated
        assert result.content["title"]
        assert result.content["text"]
        assert "extracted_at" in result.content
        assert result.content.get("simulated") is True

    @pytest.mark.asyncio
    async def test_real_extract_respects_empty_url(self, tool: WebContentExtractorTool) -> None:
        """Empty URL should return an error regardless of mode."""
        result = await tool.execute({"url": ""})
        assert "error" in result.content
