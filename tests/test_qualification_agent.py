from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.agents.qualification import IcpRules, QualificationAgent, _parse_json_object
from app.config import get_settings
from app.core.contracts import AgentContext, AgentResult, AgentTaskInput, AIRequest, AIResponse
from app.providers.manager import ProviderManager

# ── helpers ────────────────────────────────────────────────────────────


class FakeAIProvider:
    name = "test-provider"

    def __init__(self, signal_response: str, composite_response: str) -> None:
        self._signal = signal_response
        self._composite = composite_response
        self.last_request: AIRequest | None = None

    async def generate(self, request: AIRequest) -> AIResponse:
        self.last_request = request
        is_composite = "ICP Match Score" in request.messages[-1].content \
            if request.messages else False
        content = self._composite if is_composite else self._signal
        return AIResponse(content=content, provider=self.name)


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


SAMPLE_FINDINGS = {
    "company_name": "FlytBase",
    "domain": "flytbase.com",
    "industry": "Drone Technology",
    "employee_count": 200,
    "location": "San Francisco, US",
    "description": "Drone fleet management platform for enterprise.",
    "business_signals": [
        "Series A funding",
        "Hiring robotics engineers",
        "Expanding to EU market",
    ],
    "pain_points": [
        "Manual fleet management is time-consuming",
        "Scaling drone operations across regions",
    ],
    "technology_signals": [
        "DJI integration",
        "API-first architecture",
        "Cloud-based platform",
    ],
    "flytbase_relevance": "High - direct fit for FlytBase platform",
}

SAMPLE_ICP = {
    "industries": ["Drone Technology", "SaaS", "Automation"],
    "min_employees": 10,
    "max_employees": 500,
    "locations": ["US", "EU"],
}


@pytest.fixture
def task_context() -> AgentContext:
    return AgentContext(task_id=uuid.uuid4(), correlation_id="test-qual-correlation")


@pytest.fixture
def task_input() -> AgentTaskInput:
    return AgentTaskInput(
        id=uuid.uuid4(),
        agent_type="qualification",
        input_data={
            "report_id": str(uuid.uuid4()),
            "company_name": "FlytBase",
            "findings": SAMPLE_FINDINGS,
            "icp_config": SAMPLE_ICP,
        },
    )


# ── IcpRules ───────────────────────────────────────────────────────────


class TestIcpRules:
    def test_creates_from_config(self) -> None:
        icp = IcpRules(SAMPLE_ICP)
        assert icp.industries == ["Drone Technology", "SaaS", "Automation"]
        assert icp.min_employees == 10
        assert icp.max_employees == 500
        assert icp.locations == ["US", "EU"]

    def test_default_config(self) -> None:
        icp = IcpRules.default()
        assert len(icp.industries) > 0
        assert icp.min_employees == 10
        assert icp.max_employees == 500


# ── Deterministic scoring tests ────────────────────────────────────────


class TestDeterministicScoring:
    @pytest.fixture
    def agent(self) -> QualificationAgent:
        return QualificationAgent(
            ai_provider=MagicMock(),
            tool_manager=MagicMock(),
            task_manager=make_fake_tm(),
        )

    def test_full_industry_match(self, agent: QualificationAgent) -> None:
        icp = IcpRules(SAMPLE_ICP)
        score, reasons = agent._compute_icp_match(SAMPLE_FINDINGS, icp)
        assert score >= 70  # industry(40) + size(30) + location(30)
        assert any("Industry" in r for r in reasons)
        assert any("size" in r for r in reasons)

    def test_industry_mismatch(self, agent: QualificationAgent) -> None:
        icp = IcpRules({
            "industries": ["Healthcare", "Biotech"],
            "min_employees": 10,
            "max_employees": 500,
            "locations": ["US"],
        })
        score, reasons = agent._compute_icp_match(SAMPLE_FINDINGS, icp)
        assert score < 70  # industry mismatch loses 40
        assert any("outside ICP" in r for r in reasons)

    def test_size_below_minimum(self, agent: QualificationAgent) -> None:
        findings = dict(SAMPLE_FINDINGS, employee_count=5)
        icp = IcpRules(SAMPLE_ICP)
        score, _ = agent._compute_icp_match(findings, icp)
        assert score > 40  # industry + location = 70, size partial

    def test_size_above_maximum(self, agent: QualificationAgent) -> None:
        findings = dict(SAMPLE_FINDINGS, employee_count=2000)
        icp = IcpRules(SAMPLE_ICP)
        score, _ = agent._compute_icp_match(findings, icp)
        assert score > 50  # industry(40) + size(10) + location(30)? or partial

    def test_location_mismatch(self, agent: QualificationAgent) -> None:
        findings = dict(SAMPLE_FINDINGS, location="Tokyo, JP")
        icp = IcpRules(SAMPLE_ICP)
        score, reasons = agent._compute_icp_match(findings, icp)
        assert any("outside ICP" in r for r in reasons)

    def test_unknown_employee_count(self, agent: QualificationAgent) -> None:
        findings = dict(SAMPLE_FINDINGS, employee_count=None)
        icp = IcpRules(SAMPLE_ICP)
        score, reasons = agent._compute_icp_match(findings, icp)
        assert any("unknown" in r.lower() for r in reasons)

    def test_score_capped_at_100(self, agent: QualificationAgent) -> None:
        icp = IcpRules({
            "industries": ["Drone Technology"],
            "min_employees": 10,
            "max_employees": 500,
            "locations": ["US"],
        })
        score, reasons = agent._compute_icp_match(SAMPLE_FINDINGS, icp)
        assert score <= 100


# ── Full workflow tests ────────────────────────────────────────────────


class TestQualificationAgent:
    @pytest.mark.asyncio
    async def test_full_workflow_returns_scores(
        self, task_context: AgentContext, task_input: AgentTaskInput
    ) -> None:
        fake_ai = FakeAIProvider(
            signal_response=(
                '{"buying_signal_score": 85, "company_fit_score": 90, '
                '"reasons": ["Strong signals"], "risks": ["No direct intent"], '
                '"reasoning": "Good fit for drone platform."}'
            ),
            composite_response=(
                '{"overall_score": 88, "priority": "HOT", '
                '"urgency": "Immediate", "sales_angle": "Lead with drone automation", '
                '"reasons": ["Great ICP match"], '
                '"reasoning": "High priority lead with strong signals."}'
            ),
        )
        tools = MagicMock()
        tm = make_fake_tm()

        agent = QualificationAgent(
            ai_provider=fake_ai, tool_manager=tools, task_manager=tm
        )
        result = await agent.run(task_context, task_input)
        output = result.output_data

        assert output["overall_score"] > 0
        assert output["icp_match_score"] > 0
        assert output["buying_signal_score"] > 0
        assert output["company_fit_score"] > 0
        assert output["priority"] in ("HOT", "WARM", "COLD")
        assert "recommended_bdr_action" in output
        assert "urgency" in output["recommended_bdr_action"]
        assert "suggested_sales_angle" in output["recommended_bdr_action"]
        assert len(output.get("reasons", [])) > 0

    @pytest.mark.asyncio
    async def test_step_logging_events(
        self, task_context: AgentContext, task_input: AgentTaskInput
    ) -> None:
        fake_ai = FakeAIProvider(
            signal_response=(
                '{"buying_signal_score": 70, "company_fit_score": 75, '
                '"reasons": [], "risks": [], "reasoning": "Moderate fit."}'
            ),
            composite_response=(
                '{"overall_score": 72, "priority": "HOT", '
                '"urgency": "Immediate", "sales_angle": "Test angle", '
                '"reasons": [], "reasoning": "Good fit."}'
            ),
        )
        tools = MagicMock()
        tm = make_fake_tm()

        agent = QualificationAgent(
            ai_provider=fake_ai, tool_manager=tools, task_manager=tm
        )
        await agent.run(task_context, task_input)

        events = logged_event_types(tm)
        for expected in (
            "qualification_started",
            "icp_config_loaded",
            "deterministic_scoring_started",
            "deterministic_scoring_completed",
            "ai_scoring_started",
            "ai_scoring_completed",
            "composite_scoring_started",
            "priority_assigned",
            "qualification_completed",
        ):
            assert expected in events, f"Missing log event: {expected}"

    @pytest.mark.asyncio
    async def test_handles_missing_signals(
        self, task_context: AgentContext, task_input: AgentTaskInput
    ) -> None:
        empty_findings = dict(SAMPLE_FINDINGS)
        empty_findings["business_signals"] = []
        empty_findings["pain_points"] = []
        empty_findings["technology_signals"] = []

        task_input.input_data["findings"] = empty_findings

        fake_ai = FakeAIProvider(
            signal_response='{"buying_signal_score": 40, "company_fit_score": 50, '
            '"reasons": [], "risks": ["No signals"], "reasoning": "No data."}',
            composite_response='{"overall_score": 45, "priority": "WARM", '
            '"urgency": "This week", "sales_angle": "Generic pitch", '
            '"reasons": [], "reasoning": "Limited data."}',
        )
        tm = make_fake_tm()

        agent = QualificationAgent(
            ai_provider=fake_ai, tool_manager=MagicMock(), task_manager=tm
        )
        result = await agent.run(task_context, task_input)
        assert result.output_data["overall_score"] >= 0

    @pytest.mark.asyncio
    async def test_handles_llm_failure_gracefully(
        self, task_context: AgentContext, task_input: AgentTaskInput
    ) -> None:
        """When LLM returns invalid JSON, agent falls back to deterministic scoring."""
        failing_ai = FakeAIProvider(
            signal_response="not valid json at all",
            composite_response="also not valid json",
        )
        tm = make_fake_tm()

        agent = QualificationAgent(
            ai_provider=failing_ai, tool_manager=MagicMock(), task_manager=tm
        )
        result = await agent.run(task_context, task_input)
        output = result.output_data

        # Should fall back to deterministic composite
        assert output["overall_score"] > 0
        assert output["priority"] in ("HOT", "WARM", "COLD")

        events = logged_event_types(tm)
        assert "qualification_completed" in events

    @pytest.mark.asyncio
    async def test_priority_thresholds(self) -> None:
        icp_hot = IcpRules({
            "industries": ["Drone Technology", "SaaS"],
            "min_employees": 10,
            "max_employees": 500,
            "locations": ["US"],
        })
        icp_cold = IcpRules({
            "industries": ["Retail", "Hospitality"],
            "min_employees": 1000,
            "max_employees": 10000,
            "locations": ["JP"],
        })

        agent = QualificationAgent(
            ai_provider=MagicMock(), tool_manager=MagicMock(),
            task_manager=make_fake_tm(),
        )

        # HOT: good industry match
        hot_score, hot_reasons = agent._compute_icp_match(SAMPLE_FINDINGS, icp_hot)
        assert hot_score >= 70  # industry(40) + size(30) + location(30)

        # COLD: no match
        cold_score, _ = agent._compute_icp_match(SAMPLE_FINDINGS, icp_cold)
        assert cold_score < 40


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
class TestQualificationAgentRealProvider:
    """Integration tests for QualificationAgent with live FreeModelProvider.

    These tests verify the full qualification pipeline with a real LLM:
    ProviderManager resolves the correct provider, the agent runs
    deterministic ICP scoring + AI signal evaluation + composite scoring
    with real LLM calls, and the output contains valid structured scores.

    Uses sample research findings and ICP config as input. Even if the
    freemodel API is unreachable, the agent falls back gracefully.
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
        """Full QualificationAgent workflow with real LLM produces valid scores."""
        settings = self._fresh_settings()
        provider = ProviderManager(settings).resolve()
        tm = make_fake_tm()

        agent = QualificationAgent(
            ai_provider=provider, tool_manager=MagicMock(), task_manager=tm
        )
        context = AgentContext(task_id=uuid.uuid4(), correlation_id="real-qual-test")
        task = AgentTaskInput(
            id=uuid.uuid4(),
            agent_type="qualification",
            input_data={
                "report_id": str(uuid.uuid4()),
                "company_name": "FlytBase",
                "findings": SAMPLE_FINDINGS,
                "icp_config": SAMPLE_ICP,
            },
        )

        result = await agent.run(context, task)
        output = result.output_data

        # Verify result structure — works for both real API and fallback
        assert isinstance(result, AgentResult)
        assert output["overall_score"] > 0
        assert output["icp_match_score"] > 0
        assert output["buying_signal_score"] > 0
        assert output["company_fit_score"] > 0
        assert output["priority"] in ("HOT", "WARM", "COLD")
        assert "recommended_bdr_action" in output
        assert "urgency" in output["recommended_bdr_action"]
        assert "suggested_sales_angle" in output["recommended_bdr_action"]
        assert isinstance(output.get("reasons", []), list)
        assert isinstance(output.get("risks", []), list)
        assert output["providers_used"] == "freemodel"

    @pytest.mark.asyncio
    async def test_real_provider_logs_expected_events(self) -> None:
        """All expected step events are logged with a real provider."""
        settings = self._fresh_settings()
        provider = ProviderManager(settings).resolve()
        tm = make_fake_tm()

        agent = QualificationAgent(
            ai_provider=provider, tool_manager=MagicMock(), task_manager=tm
        )
        context = AgentContext(task_id=uuid.uuid4(), correlation_id="real-qual-logs")
        task = AgentTaskInput(
            id=uuid.uuid4(),
            agent_type="qualification",
            input_data={
                "report_id": str(uuid.uuid4()),
                "company_name": "FlytBase",
                "findings": SAMPLE_FINDINGS,
                "icp_config": SAMPLE_ICP,
            },
        )

        await agent.run(context, task)

        events = logged_event_types(tm)
        for expected in (
            "qualification_started",
            "icp_config_loaded",
            "deterministic_scoring_completed",
            "ai_scoring_started",
            "ai_scoring_completed",
            "priority_assigned",
            "qualification_completed",
        ):
            assert expected in events, f"Missing log event: {expected}"


# ── JSON parsing helper tests ──────────────────────────────────────────


class TestParseJsonObject:
    def test_parses_clean_object(self) -> None:
        result = _parse_json_object('{"score": 85}')
        assert result == {"score": 85}

    def test_parses_object_in_code_fence(self) -> None:
        result = _parse_json_object('```json\n{"score": 85}\n```')
        assert result == {"score": 85}

    def test_returns_none_for_invalid(self) -> None:
        result = _parse_json_object("not json at all")
        assert result is None

    def test_rejects_non_dict_json(self) -> None:
        result = _parse_json_object("[1, 2, 3]")
        assert result is None
