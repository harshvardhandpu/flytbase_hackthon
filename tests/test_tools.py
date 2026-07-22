from __future__ import annotations

import pytest

from app.tools import SimulatedContentExtractorTool, SimulatedWebSearchTool, ToolManager


class TestSimulatedWebSearchTool:
    @pytest.mark.asyncio
    async def test_returns_results_for_query(self) -> None:
        tool = SimulatedWebSearchTool()
        result = await tool.execute({"query": "FlytBase drone", "max_results": 3})
        assert result.content["result_count"] > 0
        assert len(result.sources) > 0
        assert all(url.startswith("http") for url in result.sources)

    @pytest.mark.asyncio
    async def test_returns_default_results_for_unknown_query(self) -> None:
        tool = SimulatedWebSearchTool()
        result = await tool.execute({"query": "some obscure company name"})
        assert result.content["result_count"] > 0
        assert "example.com" in result.sources[0]

    @pytest.mark.asyncio
    async def test_respects_max_results(self) -> None:
        tool = SimulatedWebSearchTool()
        result = await tool.execute({"query": "drone inspection", "max_results": 1})
        assert result.content["result_count"] == 1

    @pytest.mark.asyncio
    async def test_includes_sources_in_result(self) -> None:
        tool = SimulatedWebSearchTool()
        result = await tool.execute({"query": "flytbase", "max_results": 5})
        for r in result.content["results"]:
            assert "url" in r
            assert "title" in r
            assert "snippet" in r

    def test_name_and_description(self) -> None:
        tool = SimulatedWebSearchTool()
        assert tool.name == "web_search"
        assert len(tool.description) > 0


class TestSimulatedContentExtractorTool:
    @pytest.mark.asyncio
    async def test_returns_content_for_known_url(self) -> None:
        tool = SimulatedContentExtractorTool()
        result = await tool.execute({"url": "https://www.flytbase.com/about"})
        content = result.content
        assert content["title"] == "FlytBase — Drone Fleet Management Platform"
        assert "drone" in content["text"].lower()
        assert content["url"] == "https://www.flytbase.com/about"
        assert "extracted_at" in content

    @pytest.mark.asyncio
    async def test_returns_default_content_for_unknown_url(self) -> None:
        tool = SimulatedContentExtractorTool()
        result = await tool.execute({"url": "https://random-startup.io"})
        content = result.content
        assert "About Us" in content["title"]
        assert len(content["text"]) > 50

    @pytest.mark.asyncio
    async def test_empty_url_returns_empty_sources(self) -> None:
        tool = SimulatedContentExtractorTool()
        result = await tool.execute({"url": ""})
        assert result.sources == []

    def test_name_and_description(self) -> None:
        tool = SimulatedContentExtractorTool()
        assert tool.name == "extract_web_content"
        assert len(tool.description) > 0


class TestToolManager:
    @pytest.mark.asyncio
    async def test_execute_known_tool(self) -> None:
        tm = ToolManager([SimulatedWebSearchTool(), SimulatedContentExtractorTool()])
        result = await tm.execute("web_search", {"query": "flytbase", "max_results": 2})
        assert result.content["result_count"] == 2

    @pytest.mark.asyncio
    async def test_execute_unknown_tool_raises(self) -> None:
        tm = ToolManager([])
        with pytest.raises(ValueError, match="Unknown tool"):
            await tm.execute("nonexistent", {})

    def test_tool_descriptions(self) -> None:
        tm = ToolManager([SimulatedWebSearchTool()])
        descs = tm.tool_descriptions
        assert len(descs) == 1
        assert descs[0]["name"] == "web_search"
        assert len(descs[0]["description"]) > 0
