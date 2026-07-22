from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.agents.outreach import OutreachAgent, _parse_json_object
from app.core.contracts import AgentContext, AgentTaskInput, AIRequest, AIResponse

# ── helpers ────────────────────────────────────────────────────────────


def logged_event_types(tm: MagicMock) -> set[str]:
    events: set[str] = set()
    for call in tm.append_log.call_args_list:
        if hasattr(call, "args") and len(call.args) >= 3:
            events.add(str(call.args[2]))
    return events


def make_fake_tm() -> MagicMock:
    tm = MagicMock()
    tm.append_log.return_value = None
    return tm


SAMPLE_RESEARCH = {
    "company_name": "SkyGrid Inc.",
    "domain": "skygrid.io",
    "industry": "Drone Services",
    "employee_count": 180,
    "location": "Austin, TX",
    "description": "Drone fleet management for agriculture inspections.",
    "business_signals": [
        "Series B funding: $15M",
        "Expanding to EU market",
        "Hiring drone operators",
    ],
    "pain_points": [
        "Manual pilot scheduling limits scalability",
        "High operational costs per inspection",
    ],
    "technology_signals": ["DJI SDK integration", "Custom dashboard"],
    "flytbase_relevance": "High: operates drone fleets at scale",
}

SAMPLE_QUALIFICATION = {
    "overall_score": 85,
    "icp_match_score": 90,
    "buying_signal_score": 82,
    "company_fit_score": 80,
    "priority": "HOT",
    "reasoning": "Strong ICP match with buying signals.",
    "reasons": ["+ Industry matches ICP", "+ Series B funding"],
    "risks": ["- No direct purchase intent detected"],
    "recommended_bdr_action": {
        "urgency": "Immediate",
        "suggested_sales_angle": "Lead with automation ROI for agri-drones.",
    },
}

STRATEGY_RESPONSE = (
    '{"recommended_channel": "email", '
    '"urgency": "Immediate", '
    '"reasoning": "Email best for value prop delivery."}'
)

PERSONALIZATION_RESPONSE = (
    '{"company_hook": "SkyGrid EU aligns with FlytBase.", '
    '"detected_pain_point": "Manual pilot scheduling is bottleneck.", '
    '"flytbase_value_proposition": "FlytBase automates fleet ops."}'
)

DRAFT_RESPONSE = (
    '{"subject": "Scaling SkyGrid drone inspections across the EU", '
    '"body": "Hi {{first_name}},\\n\\nI noticed SkyGrid expansion...", '
    '"follow_up_suggestion": "Follow up in 5 days with case study."}'
)


class FakeOutreachAIProvider:
    """Simulates AIProvider with phased responses for strategy/personalization/draft.

    Uses call counter because the agent calls generate() in order:
    1st = strategy, 2nd = personalization, 3rd = draft.
    """

    name = "test-provider"

    def __init__(
        self,
        strategy: str = STRATEGY_RESPONSE,
        personalization: str = PERSONALIZATION_RESPONSE,
        draft: str = DRAFT_RESPONSE,
    ) -> None:
        self._responses = [strategy, personalization, draft]
        self._call_count = 0
        self.last_request: AIRequest | None = None

    async def generate(self, request: AIRequest) -> AIResponse:
        self.last_request = request
        idx = min(self._call_count, 2)
        self._call_count += 1
        return AIResponse(
            content=self._responses[idx],
            provider=self.name,
        )


@pytest.fixture
def task_context() -> AgentContext:
    return AgentContext(task_id=uuid.uuid4(), correlation_id="test-outreach-correlation")


@pytest.fixture
def task_input() -> AgentTaskInput:
    return AgentTaskInput(
        id=uuid.uuid4(),
        agent_type="outreach",
        input_data={
            "company_name": "SkyGrid Inc.",
            "research_findings": SAMPLE_RESEARCH,
            "qualification": SAMPLE_QUALIFICATION,
        },
    )


# ── Full workflow tests ────────────────────────────────────────────────


class TestOutreachAgent:
    @pytest.mark.asyncio
    async def test_full_workflow_generates_draft(
        self, task_context: AgentContext, task_input: AgentTaskInput
    ) -> None:
        fake_ai = FakeOutreachAIProvider()
        tools = MagicMock()
        tm = make_fake_tm()

        agent = OutreachAgent(ai_provider=fake_ai, tool_manager=tools, task_manager=tm)
        result = await agent.run(task_context, task_input)
        output = result.output_data

        # Strategy
        assert "outreach_strategy" in output
        strat = output["outreach_strategy"]
        assert strat["recommended_channel"] in ("email", "linkedin", "phone")
        assert strat["urgency"] in ("Immediate", "This week", "This month")
        assert strat["reasoning"]

        # Personalization
        assert "personalization" in output
        pers = output["personalization"]
        assert pers["company_hook"]
        assert pers["detected_pain_point"]
        assert pers["flytbase_value_proposition"]

        # Email draft
        assert "email_draft" in output
        draft = output["email_draft"]
        assert draft["subject"]
        assert draft["body"]
        assert draft["follow_up_suggestion"]

        # Approval boundary
        assert result.requires_human_approval is True

    @pytest.mark.asyncio
    async def test_step_logging_events(
        self, task_context: AgentContext, task_input: AgentTaskInput
    ) -> None:
        fake_ai = FakeOutreachAIProvider()
        tm = make_fake_tm()

        agent = OutreachAgent(
            ai_provider=fake_ai, tool_manager=MagicMock(), task_manager=tm
        )
        await agent.run(task_context, task_input)

        events = logged_event_types(tm)
        for expected in (
            "outreach_started",
            "context_loaded",
            "strategy_generation_started",
            "strategy_generation_completed",
            "personalization_started",
            "personalization_completed",
            "draft_generation_started",
            "draft_generation_completed",
            "outreach_completed",
        ):
            assert expected in events, f"Missing log event: {expected}"

    @pytest.mark.asyncio
    async def test_requires_human_approval(
        self, task_context: AgentContext, task_input: AgentTaskInput
    ) -> None:
        fake_ai = FakeOutreachAIProvider()
        agent = OutreachAgent(
            ai_provider=fake_ai, tool_manager=MagicMock(), task_manager=make_fake_tm()
        )
        result = await agent.run(task_context, task_input)
        assert result.requires_human_approval is True

    @pytest.mark.asyncio
    async def test_handles_missing_context(
        self, task_context: AgentContext
    ) -> None:
        """Agent should still produce output with empty research/qualification."""
        empty_input = AgentTaskInput(
            id=uuid.uuid4(),
            agent_type="outreach",
            input_data={
                "company_name": "Unknown Corp",
                "research_findings": {},
                "qualification": {},
            },
        )

        fake_ai = FakeOutreachAIProvider()
        agent = OutreachAgent(
            ai_provider=fake_ai, tool_manager=MagicMock(), task_manager=make_fake_tm()
        )
        result = await agent.run(task_context, empty_input)
        assert result.requires_human_approval is True
        assert "outreach_strategy" in result.output_data
        assert "personalization" in result.output_data
        assert "email_draft" in result.output_data

    @pytest.mark.asyncio
    async def test_llm_strategy_failure_fallback(
        self, task_context: AgentContext, task_input: AgentTaskInput
    ) -> None:
        """When LLM returns invalid JSON for strategy, agent uses fallback."""
        failing_ai = FakeOutreachAIProvider(
            strategy="not valid json",
            personalization=PERSONALIZATION_RESPONSE,
            draft=DRAFT_RESPONSE,
        )
        agent = OutreachAgent(
            ai_provider=failing_ai, tool_manager=MagicMock(), task_manager=make_fake_tm()
        )
        result = await agent.run(task_context, task_input)
        output = result.output_data
        strat = output["outreach_strategy"]
        assert strat["recommended_channel"] == "email"  # fallback
        assert strat["urgency"] == "This week"  # fallback

    @pytest.mark.asyncio
    async def test_llm_draft_failure_fallback(
        self, task_context: AgentContext, task_input: AgentTaskInput
    ) -> None:
        """When LLM returns invalid JSON for draft, agent uses fallback."""
        failing_ai = FakeOutreachAIProvider(
            strategy=STRATEGY_RESPONSE,
            personalization=PERSONALIZATION_RESPONSE,
            draft="not valid json",
        )
        agent = OutreachAgent(
            ai_provider=failing_ai, tool_manager=MagicMock(), task_manager=make_fake_tm()
        )
        result = await agent.run(task_context, task_input)
        output = result.output_data
        draft = output["email_draft"]
        assert draft["subject"] == "Introduction: SkyGrid Inc."  # fallback
        assert draft["body"] == ""  # fallback

    @pytest.mark.asyncio
    async def test_generates_valid_structured_output(
        self, task_context: AgentContext, task_input: AgentTaskInput
    ) -> None:
        fake_ai = FakeOutreachAIProvider()
        agent = OutreachAgent(
            ai_provider=fake_ai, tool_manager=MagicMock(), task_manager=make_fake_tm()
        )
        result = await agent.run(task_context, task_input)
        output = result.output_data

        # Verify output has the full structure expected by API
        assert isinstance(output["outreach_strategy"], dict)
        assert isinstance(output["personalization"], dict)
        assert isinstance(output["email_draft"], dict)
        assert output["requires_human_approval"] is True
        assert output["providers_used"] == "test-provider"


# ── JSON parsing tests ────────────────────────────────────────────────


class TestParseJsonObject:
    def test_parses_clean_object(self) -> None:
        result = _parse_json_object('{"channel": "email"}')
        assert result == {"channel": "email"}

    def test_parses_object_in_code_fence(self) -> None:
        result = _parse_json_object('```json\n{"channel": "email"}\n```')
        assert result == {"channel": "email"}

    def test_returns_none_for_invalid(self) -> None:
        result = _parse_json_object("not json at all")
        assert result is None

    def test_rejects_non_dict_json(self) -> None:
        result = _parse_json_object("[1, 2, 3]")
        assert result is None

    def test_parses_nested_object(self) -> None:
        result = _parse_json_object(
            '{"subject": "Hello", "body": "World", "data": {"key": "val"}}'
        )
        assert result == {"subject": "Hello", "body": "World", "data": {"key": "val"}}


# ── Strategy generation tests ──────────────────────────────────────────


class TestStrategyGeneration:
    @pytest.mark.asyncio
    async def test_strategy_has_required_fields(
        self, task_context: AgentContext, task_input: AgentTaskInput
    ) -> None:
        fake_ai = FakeOutreachAIProvider()
        agent = OutreachAgent(
            ai_provider=fake_ai, tool_manager=MagicMock(), task_manager=make_fake_tm()
        )
        result = await agent.run(task_context, task_input)
        strat = result.output_data["outreach_strategy"]
        assert "recommended_channel" in strat
        assert "urgency" in strat
        assert "reasoning" in strat


class TestPersonalizationGeneration:
    @pytest.mark.asyncio
    async def test_personalization_has_required_fields(
        self, task_context: AgentContext, task_input: AgentTaskInput
    ) -> None:
        fake_ai = FakeOutreachAIProvider()
        agent = OutreachAgent(
            ai_provider=fake_ai, tool_manager=MagicMock(), task_manager=make_fake_tm()
        )
        result = await agent.run(task_context, task_input)
        pers = result.output_data["personalization"]
        assert "company_hook" in pers
        assert "detected_pain_point" in pers
        assert "flytbase_value_proposition" in pers


class TestDraftGeneration:
    @pytest.mark.asyncio
    async def test_draft_has_required_fields(
        self, task_context: AgentContext, task_input: AgentTaskInput
    ) -> None:
        fake_ai = FakeOutreachAIProvider()
        agent = OutreachAgent(
            ai_provider=fake_ai, tool_manager=MagicMock(), task_manager=make_fake_tm()
        )
        result = await agent.run(task_context, task_input)
        draft = result.output_data["email_draft"]
        assert "subject" in draft
        assert "body" in draft
        assert "follow_up_suggestion" in draft
