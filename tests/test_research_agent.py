from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.agents.research import ResearchAgent, _parse_json_list, _parse_json_object
from app.config import get_settings
from app.core.contracts import AgentContext, AgentResult, AgentTaskInput, AIRequest, AIResponse
from app.providers.manager import ProviderManager
from app.tools import SimulatedContentExtractorTool, SimulatedWebSearchTool, ToolManager

# ── helpers ────────────────────────────────────────────────────────────


class FakeAIProvider:
    """Returns canned responses for testing."""

    name = "test-provider"

    def __init__(self, planning_response: str, synthesis_response: str) -> None:
        self._planning = planning_response
        self._synthesis = synthesis_response
        self.last_request: AIRequest | None = None

    async def generate(self, request: AIRequest) -> AIResponse:
        self.last_request = request
        is_synthesis = "Synthesise" in request.messages[-1].content if request.messages else False
        content = self._synthesis if is_synthesis else self._planning
        return AIResponse(content=content, provider=self.name)


def logged_event_types(tm: MagicMock) -> set[str]:
    """Extract event_type values from append_log call records."""
    events: set[str] = set()
    for call in tm.append_log.call_args_list:
        # call is a _Call object with .args tuple of positional args
        # append_log(task_id, level, event_type, message, data=None)
        if hasattr(call, "args") and len(call.args) >= 3:
            events.add(str(call.args[2]))
    return events


def make_fake_tm() -> MagicMock:
    tm = MagicMock()
    tm.append_log.return_value = None
    return tm


@pytest.fixture
def task_context() -> AgentContext:
    return AgentContext(task_id=uuid.uuid4(), correlation_id="test-correlation")


@pytest.fixture
def task_input() -> AgentTaskInput:
    return AgentTaskInput(
        id=uuid.uuid4(),
        agent_type="research",
        input_data={"company_name": "FlytBase", "domain": "flytbase.com"},
    )


# ── JSON parsing helpers ───────────────────────────────────────────────


class TestParseJsonList:
    def test_parses_clean_array(self) -> None:
        result = _parse_json_list('["query1", "query2"]')
        assert result == ["query1", "query2"]

    def test_parses_array_in_code_fence(self) -> None:
        result = _parse_json_list('```json\n["q1", "q2"]\n```')
        assert result == ["q1", "q2"]

    def test_returns_empty_for_invalid(self) -> None:
        result = _parse_json_list("not json at all")
        assert result == []

    def test_rejects_non_array_json(self) -> None:
        result = _parse_json_list('{"key": "value"}')
        assert result == []


class TestParseJsonObject:
    def test_parses_clean_object(self) -> None:
        result = _parse_json_object('{"name": "Acme"}')
        assert result == {"name": "Acme"}

    def test_parses_object_in_code_fence(self) -> None:
        result = _parse_json_object('```json\n{"name": "Acme"}\n```')
        assert result == {"name": "Acme"}

    def test_returns_none_for_invalid(self) -> None:
        result = _parse_json_object("not json at all")
        assert result is None

    def test_rejects_non_dict_json(self) -> None:
        result = _parse_json_object("[1, 2, 3]")
        assert result is None


# ── ResearchAgent ──────────────────────────────────────────────────────


class TestResearchAgent:
    @pytest.mark.asyncio
    async def test_full_workflow_returns_result(
        self, task_context: AgentContext, task_input: AgentTaskInput
    ) -> None:
        fake_ai = FakeAIProvider(
            planning_response='["flytbase overview", "flytbase funding"]',
            synthesis_response=(
                '{"company_name": "FlytBase", "domain": "flytbase.com", '
                '"industry": "Drone Services", "employee_count": 200, '
                '"location": "San Francisco", "description": "A drone platform.", '
                '"business_signals": ["Series A funding"], '
                '"pain_points": ["Scaling operations"], '
                '"technology_signals": ["DJI integration"], '
                '"flytbase_relevance": "High", '
                '"recommended_next_action": "Demo", '
                '"sources": ["https://flytbase.com"]}'
            ),
        )
        tools = ToolManager([SimulatedWebSearchTool(), SimulatedContentExtractorTool()])
        tm = make_fake_tm()

        agent = ResearchAgent(ai_provider=fake_ai, tool_manager=tools, task_manager=tm)
        result = await agent.run(task_context, task_input)

        assert result.summary == "A drone platform."
        assert result.output_data["findings"]["company_name"] == "FlytBase"
        assert result.output_data["findings"]["industry"] == "Drone Services"
        assert result.output_data["findings"]["business_signals"] == ["Series A funding"]
        assert "report_id" in result.output_data
        assert not result.requires_human_approval

        # Verify step logging
        events = logged_event_types(tm)
        for expected in (
            "research_started",
            "planning_started",
            "planning_completed",
            "synthesis_started",
            "report_created",
            "task_completed",
        ):
            assert expected in events, f"Missing log event: {expected}"

    @pytest.mark.asyncio
    async def test_handles_llm_planning_failure(
        self, task_context: AgentContext, task_input: AgentTaskInput
    ) -> None:
        """When LLM fails, agent falls back to default queries and continues."""
        fake_ai = FakeAIProvider(
            planning_response="not valid json at all",
            synthesis_response=(
                '{"company_name": "FlytBase", "description": "Partial result.", '
                '"business_signals": [], "pain_points": [], '
                '"technology_signals": [], "sources": []}'
            ),
        )
        tools = ToolManager([SimulatedWebSearchTool(), SimulatedContentExtractorTool()])
        tm = make_fake_tm()

        agent = ResearchAgent(ai_provider=fake_ai, tool_manager=tools, task_manager=tm)
        result = await agent.run(task_context, task_input)

        assert result.summary == "Partial result."
        assert result.output_data["findings"]["company_name"] == "FlytBase"

        events = logged_event_types(tm)
        assert "task_completed" in events

    @pytest.mark.asyncio
    async def test_handles_synthesis_failure(
        self, task_context: AgentContext, task_input: AgentTaskInput
    ) -> None:
        """When synthesis LLM fails, agent returns fallback report."""
        fake_ai = FakeAIProvider(
            planning_response='["flytbase overview"]',
            synthesis_response="not valid json at all",
        )
        tools = ToolManager([SimulatedWebSearchTool(), SimulatedContentExtractorTool()])
        tm = make_fake_tm()

        agent = ResearchAgent(ai_provider=fake_ai, tool_manager=tools, task_manager=tm)
        result = await agent.run(task_context, task_input)

        # Should still complete with fallback that includes a trailing period
        assert "Research completed for FlytBase" in result.summary
        assert result.output_data["findings"]["company_name"] == "FlytBase"

    @pytest.mark.asyncio
    async def test_requires_company_or_domain(self) -> None:
        """Agent should handle empty input gracefully."""
        fake_ai = FakeAIProvider(
            planning_response='["search query"]',
            synthesis_response=(
                '{"description": "No data.", "business_signals": [], '
                '"pain_points": [], "technology_signals": [], "sources": []}'
            ),
        )
        tools = ToolManager([SimulatedWebSearchTool(), SimulatedContentExtractorTool()])
        tm = make_fake_tm()

        context = AgentContext(task_id=uuid.uuid4(), correlation_id="test")
        task = AgentTaskInput(
            id=uuid.uuid4(),
            agent_type="research",
            input_data={"company_name": "", "domain": ""},
        )

        agent = ResearchAgent(ai_provider=fake_ai, tool_manager=tools, task_manager=tm)
        result = await agent.run(context, task)
        assert result.summary is not None

    @pytest.mark.asyncio
    async def test_tool_failures_logged_and_continued(
        self, task_context: AgentContext, task_input: AgentTaskInput
    ) -> None:
        """If a tool fails, agent logs the error and continues with remaining tools."""
        failing_tools = MagicMock()
        failing_tools.execute.side_effect = ValueError("Connection lost")

        fake_ai = FakeAIProvider(
            planning_response='["flytbase overview"]',
            synthesis_response=(
                '{"description": "Limited data.", "business_signals": [], '
                '"pain_points": [], "technology_signals": [], "sources": []}'
            ),
        )
        tm = make_fake_tm()

        agent = ResearchAgent(ai_provider=fake_ai, tool_manager=failing_tools, task_manager=tm)
        result = await agent.run(task_context, task_input)

        assert result.summary is not None

        events = logged_event_types(tm)
        assert "tool_failed" in events, (
            f"Expected 'tool_failed' in logged events, got: {events}"
        )


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
class TestResearchAgentRealProvider:
    """Integration tests that call the real FreeModelProvider via ProviderManager.

    These tests verify the ResearchAgent full pipeline with a live LLM:
    ProviderManager resolves the correct provider, the agent runs planning,
    search, extraction, intelligence analysis, and synthesis with real LLM
    calls, and the output contains valid structured research.

    Uses simulated search/extraction tools so the LLM has predictable data
    to work with. Even if the freemodel API is unreachable, the agent
    gracefully falls back to deterministic output.
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
    async def test_full_workflow_with_real_provider(self) -> None:
        """Full ResearchAgent workflow with real LLM produces structured output."""
        settings = self._fresh_settings()
        provider = ProviderManager(settings).resolve()
        tools = ToolManager([SimulatedWebSearchTool(), SimulatedContentExtractorTool()])
        tm = make_fake_tm()

        agent = ResearchAgent(ai_provider=provider, tool_manager=tools, task_manager=tm)
        context = AgentContext(task_id=uuid.uuid4(), correlation_id="real-provider-test")
        task = AgentTaskInput(
            id=uuid.uuid4(),
            agent_type="research",
            input_data={"company_name": "FlytBase", "domain": "flytbase.com"},
        )

        result = await agent.run(context, task)

        # Verify result structure — works for both real API and fallback
        assert isinstance(result, AgentResult)
        assert result.summary is not None
        assert len(result.summary) > 0
        assert "report_id" in result.output_data
        assert "findings" in result.output_data
        assert not result.requires_human_approval

        findings = result.output_data["findings"]
        assert "company_name" in findings
        assert "industry" in findings
        assert "description" in findings
        assert isinstance(findings.get("business_signals"), list)
        assert isinstance(findings.get("pain_points"), list)
        assert isinstance(findings.get("technology_signals"), list)
        assert isinstance(findings.get("sources"), list)

        # Account Intelligence enriched fields
        assert "company_situation" in findings
        assert "growth_signals" in findings
        assert "buying_signals" in findings
        assert "operational_risks" in findings
        assert "industry_incidents" in findings

        assert "citations" in result.output_data
        assert isinstance(result.output_data["citations"], list)

    @pytest.mark.asyncio
    async def test_real_provider_logs_expected_events(self) -> None:
        """All expected step events are logged with a real provider."""
        settings = self._fresh_settings()
        provider = ProviderManager(settings).resolve()
        tools = ToolManager([SimulatedWebSearchTool(), SimulatedContentExtractorTool()])
        tm = make_fake_tm()

        agent = ResearchAgent(ai_provider=provider, tool_manager=tools, task_manager=tm)
        context = AgentContext(task_id=uuid.uuid4(), correlation_id="real-provider-logs")
        task = AgentTaskInput(
            id=uuid.uuid4(),
            agent_type="research",
            input_data={"company_name": "FlytBase", "domain": "flytbase.com"},
        )

        await agent.run(context, task)

        events = logged_event_types(tm)
        for expected in (
            "research_started",
            "planning_started",
            "planning_completed",
            "intelligence_analysis_started",
            "intelligence_analysis_completed",
            "synthesis_started",
            "report_created",
            "task_completed",
        ):
            assert expected in events, f"Missing log event: {expected}"
