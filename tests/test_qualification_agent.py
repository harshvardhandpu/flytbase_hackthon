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

    def __init__(self, evidence_response: str, composite_response: str) -> None:
        self._evidence = evidence_response
        self._composite = composite_response
        self.last_request: AIRequest | None = None

    async def generate(self, request: AIRequest) -> AIResponse:
        self.last_request = request
        # Evidence prompt has "=== Operational Pain Points"; composite has "Scores:"
        last_msg = request.messages[-1].content if request.messages else ""
        is_evidence = "=== Operational Pain Points" in last_msg
        content = self._evidence if is_evidence else self._composite
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
    "company_name": "SkyGrid Drones",
    "domain": "skygrid-drones.com",
    "industry": "Drone Technology / Drone Services",
    "employee_count": 350,
    "location": "Austin, Texas, US",
    "description": (
        "SkyGrid Drones provides enterprise drone fleet management, "
        "remote inspection, and aerial data analytics for industrial clients."
    ),
    "company_situation": (
        "SkyGrid Drones has expanded its enterprise drone fleet operations "
        "across 12 US states and is investing in autonomous flight "
        "capabilities and remote operations centers."
    ),
    "operational_pain_points": [
        {
            "pain_point": "Scaling drone fleet across multiple states",
            "evidence": (
                "SkyGrid recently opened 3 new regional operations centers "
                "to manage growing fleet demand, straining existing manual "
                "fleet coordination processes."
            ),
            "source_url": "https://example.com/skygrid-expansion"
        },
        {
            "pain_point": "Remote monitoring of distributed drone operations",
            "evidence": (
                "Operations team reported challenges maintaining real-time "
                "visibility across 12 state operations from central HQ."
            ),
            "source_url": "https://example.com/skygrid-ops"
        },
        {
            "pain_point": "Manual inspection workflow inefficiency",
            "evidence": (
                "Field inspection reports are manually compiled, causing "
                "2-3 day delays in delivering client reports."
            ),
            "source_url": "https://example.com/skygrid-inspection"
        },
    ],
    "buying_signals": [
        {
            "signal": "Investing in autonomous flight capabilities",
            "source_url": "https://example.com/skygrid-autonomy"
        },
        {
            "signal": "Hiring remote operations engineers",
            "source_url": "https://example.com/skygrid-hiring"
        },
        {
            "signal": "Evaluating drone fleet management platforms",
            "source_url": "https://example.com/skygrid-platform"
        },
    ],
    "business_signals": [
        {
            "signal": "Opened 3 new regional operations centers",
            "category": "expansion",
            "source_url": "https://example.com/skygrid-expansion",
            "summary": "Expanding operations footprint across US",
            "date": "2026-06-15",
        },
        {
            "signal": "$15M Series B funding round",
            "category": "funding",
            "source_url": "https://example.com/skygrid-funding",
            "summary": "Recent funding for autonomous drone tech",
            "date": "2026-04-20",
        },
        {
            "signal": "Partnership with industrial inspection firms",
            "category": "partnership",
            "source_url": "https://example.com/skygrid-partnership",
            "summary": "Collaborating on automated inspection solutions",
            "date": "2026-05-10",
        },
    ],
    "pain_points": [
        "Manual fleet management is time-consuming",
        "Scaling drone operations across regions",
        "Remote monitoring visibility gaps",
    ],
    "technology_signals": [
        "DJI integration",
        "API-first architecture",
        "Cloud-based platform",
    ],
    "flytbase_relevance": (
        "High - SkyGrid fleet scaling challenges directly align with "
        "FlytBase remote fleet management and automation platform."
    ),
    "flytbase_fit": (
        "FlytBase remote drone operations platform directly addresses "
        "SkyGrid need for centralized fleet visibility, automated mission "
        "scheduling, and real-time operational monitoring."
    ),
    "why_now": (
        "SkyGrid is actively scaling operations and evaluating automation "
        "platforms — this is the right time to engage before they commit "
        "to a competing solution."
    ),
    "confidence_score": 85,
    "sources": [
        "https://example.com/skygrid-expansion",
        "https://example.com/skygrid-funding",
        "https://example.com/skygrid-hiring",
    ],
    "evidence": [
        {
            "claim": "SkyGrid expanded to 12 US states and opened 3 regional centers",
            "source_url": "https://example.com/skygrid-expansion"
        },
        {
            "claim": "SkyGrid raised $15M Series B for autonomous drone technology",
            "source_url": "https://example.com/skygrid-funding"
        },
    ],
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
        assert icp.max_employees == 5000


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
        # Drone Technology matches, 350 emp in 10-500, Austin US matches
        assert score == 30  # industry(12) + size(9) + location(9)
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
        assert score < 20  # industry mismatch loses 12, gets 9+9=18
        assert any("outside ICP" in r for r in reasons)

    def test_size_below_minimum(self, agent: QualificationAgent) -> None:
        findings = dict(SAMPLE_FINDINGS, employee_count=5)
        icp = IcpRules(SAMPLE_ICP)
        score, _ = agent._compute_icp_match(findings, icp)
        assert score > 15  # industry(12) + partial size + location(9)

    def test_size_above_maximum(self, agent: QualificationAgent) -> None:
        findings = dict(SAMPLE_FINDINGS, employee_count=2000)
        icp = IcpRules(SAMPLE_ICP)
        score, reasons = agent._compute_icp_match(findings, icp)
        assert score > 10  # industry(12) + size_above(3) + location(9)

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

    def test_score_capped_at_30(self, agent: QualificationAgent) -> None:
        icp = IcpRules({
            "industries": ["Drone Technology"],
            "min_employees": 10,
            "max_employees": 500,
            "locations": ["US"],
        })
        score, reasons = agent._compute_icp_match(SAMPLE_FINDINGS, icp)
        assert score <= 30


# ── Full workflow tests ────────────────────────────────────────────────


class TestQualificationAgent:
    @pytest.mark.asyncio
    async def test_full_workflow_returns_scores(
        self, task_context: AgentContext, task_input: AgentTaskInput
    ) -> None:
        # Evidence scoring returns 0-100; composite returns final reasoning
        fake_ai = FakeAIProvider(
            evidence_response=(
                '{"pain_alignment_score": 75, "buying_intent_score": 80, '
                '"company_fit_score": 90, '
                '"evidence_based_reasons": ["Fleet expansion indicates scaling needs"], '
                '"reasons": ["Strong pain alignment"], '
                '"risks": ["Competing platform in evaluation"], '
                '"reasoning": "Strong evidence of fleet scaling challenges."}'
            ),
            composite_response=(
                '{"sales_angle": "Lead with fleet scaling and visibility", '
                '"qualification_summary": "SkyGrid qualifies as HOT with strong pain alignment.", '
                '"reasons": ["Automation investment aligns with FlytBase"], '
                '"reasoning": "High priority lead with fleet scaling signals."}'
            ),
        )
        tools = MagicMock()
        tm = make_fake_tm()

        agent = QualificationAgent(
            ai_provider=fake_ai, tool_manager=tools, task_manager=tm
        )
        result = await agent.run(task_context, task_input)
        output = result.output_data

        # ICP match should be max (industry=Drone Tech, size=350, location=US)
        assert output["icp_match_score"] == 30
        # Pain alignment from AI response
        expected_pain = round(75 * 0.30)  # 23
        expected_intent = round(80 * 0.25)  # 20
        expected_fit = round(90 * 0.15)  # 14
        expected_overall = 30 + expected_pain + expected_intent + expected_fit
        assert output["overall_score"] == expected_overall
        assert output["pain_alignment_score"] == 75
        assert output["buying_signal_score"] == 80
        assert output["company_fit_score"] == 90
        assert output["priority"] in ("HOT", "WARM", "COLD")
        assert "recommended_bdr_action" in output
        assert "urgency" in output["recommended_bdr_action"]
        assert "suggested_sales_angle" in output["recommended_bdr_action"]
        assert len(output.get("reasons", [])) > 0
        assert len(output.get("evidence_based_reasons", [])) > 0
        assert len(output.get("qualification_summary", "")) > 0

    @pytest.mark.asyncio
    async def test_step_logging_events(
        self, task_context: AgentContext, task_input: AgentTaskInput
    ) -> None:
        fake_ai = FakeAIProvider(
            evidence_response=(
                '{"pain_alignment_score": 60, "buying_intent_score": 70, '
                '"company_fit_score": 75, '
                '"evidence_based_reasons": ["Evidence shows scaling needs"], '
                '"reasons": [], "risks": [], '
                '"reasoning": "Moderate fit."}'
            ),
            composite_response=(
                '{"sales_angle": "Test angle", '
                '"qualification_summary": "Qual summary test", '
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
    async def test_handles_missing_evidence(
        self, task_context: AgentContext, task_input: AgentTaskInput
    ) -> None:
        """When research has no operational_pain_points or buying_signals,
        scores default to 0 with explainable reasons."""
        empty_findings = dict(SAMPLE_FINDINGS)
        empty_findings["operational_pain_points"] = []
        empty_findings["buying_signals"] = []
        empty_findings["business_signals"] = []
        empty_findings["evidence"] = []
        empty_findings["company_situation"] = ""
        empty_findings["flytbase_fit"] = ""

        task_input.input_data["findings"] = empty_findings

        # AI will still be called with empty lists — should return low scores
        fake_ai = FakeAIProvider(
            evidence_response='{"pain_alignment_score": 0, "buying_intent_score": 0, '
            '"company_fit_score": 0, "evidence_based_reasons": [], '
            '"reasons": ["No evidence found"], "risks": ["No signals"], '
            '"reasoning": "No data available for scoring."}',
            composite_response='{"sales_angle": "Generic pitch", '
            '"qualification_summary": "Limited intelligence", '
            '"reasons": [], "reasoning": "Limited data."}',
        )
        tm = make_fake_tm()

        agent = QualificationAgent(
            ai_provider=fake_ai, tool_manager=MagicMock(), task_manager=tm
        )
        result = await agent.run(task_context, task_input)
        # ICP match still computed deterministically, but AI scores are 0
        assert result.output_data["overall_score"] <= 30  # only ICP contributes
        assert result.output_data["pain_alignment_score"] == 0
        assert result.output_data["buying_signal_score"] == 0

    @pytest.mark.asyncio
    async def test_handles_llm_failure_gracefully(
        self, task_context: AgentContext, task_input: AgentTaskInput
    ) -> None:
        """When LLM returns invalid JSON, agent falls back gracefully."""
        failing_ai = FakeAIProvider(
            evidence_response="not valid json at all",
            composite_response="also not valid json",
        )
        tm = make_fake_tm()

        agent = QualificationAgent(
            ai_provider=failing_ai, tool_manager=MagicMock(), task_manager=tm
        )
        result = await agent.run(task_context, task_input)
        output = result.output_data

        # ICP match still computed (30 pts), AI scores fallback to 0
        assert output["overall_score"] >= 0
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

        # HOT: good industry match (max 30)
        hot_score, hot_reasons = agent._compute_icp_match(SAMPLE_FINDINGS, icp_hot)
        assert hot_score == 30  # industry(12) + size(9) + location(9)

        # COLD: no match
        cold_score, _ = agent._compute_icp_match(SAMPLE_FINDINGS, icp_cold)
        assert cold_score < 15


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
