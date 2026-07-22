"""Tests for PipelineAgent — deterministic rules, LLM evaluation, step logging."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.agents.pipeline import PipelineAgent, _compute_stage_health, _compute_stagnation_risk
from app.core.contracts import (
    AgentContext,
    AgentTaskInput,
    AIProvider,
    AIRequest,
    AIResponse,
)
from app.core.task_manager import TaskManager
from app.tools.tool_manager import ToolManager

# ── Fake AI Provider ────────────────────────────────────────────────────


class FakePipelineAIProvider:
    """Fake AI provider that returns canned evaluation responses."""

    name = "fake-pipeline"

    def __init__(self) -> None:
        self.call_count = 0

    async def generate(self, request: AIRequest) -> AIResponse:
        self.call_count += 1
        return AIResponse(
            content=(
                '{\n'
                '  "overall_health": "fair",\n'
                '  "engagement_level": "low",\n'
                '  "signal_decay": "moderate",\n'
                '  "reengagement_needed": true,\n'
                '  "recommended_action": {\n'
                '    "type": "follow_up",\n'
                '    "channel": "email",\n'
                '    "stage_transition": "meeting_scheduled",\n'
                '    "priority": "soon",\n'
                '    "action": "Send a follow-up email with relevant case study.",\n'
                '    "reasoning": "Lead has been in outreach for 14 days without response."\n'
                '  }\n'
                '}'
            ),
            provider="fake-pipeline",
        )


# ── Deterministic rule tests ───────────────────────────────────────────


class TestStageHealth:
    def test_healthy_stage(self):
        assert _compute_stage_health("new", 2) == "healthy"

    def test_stale_stage(self):
        assert _compute_stage_health("outreach", 14) == "stale"

    def test_critical_stage(self):
        assert _compute_stage_health("new", 15) == "critical"

    def test_healthy_negotiation(self):
        assert _compute_stage_health("negotiation", 20) == "healthy"

    def test_stale_qualified(self):
        assert _compute_stage_health("qualified", 5) == "stale"

    def test_unknown_stage_default_timeout(self):
        assert _compute_stage_health("unknown", 15) == "critical"


class TestStagnationRisk:
    def test_low_risk(self):
        assert _compute_stagnation_risk(7, 1) == "low"

    def test_moderate_risk(self):
        assert _compute_stagnation_risk(15, 1) == "moderate"

    def test_high_risk(self):
        assert _compute_stagnation_risk(30, 0) == "high"

    def test_moderate_no_engagement(self):
        assert _compute_stagnation_risk(18, 0) == "moderate"


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def task_id() -> UUID:
    return uuid.uuid4()


@pytest.fixture
def agent() -> PipelineAgent:
    ai: AIProvider = FakePipelineAIProvider()  # type: ignore[assignment]
    tm = MagicMock(spec=TaskManager)
    tools = MagicMock(spec=ToolManager)
    return PipelineAgent(ai_provider=ai, tool_manager=tools, task_manager=tm)


@pytest.fixture
def context(task_id: UUID) -> AgentContext:
    return AgentContext(task_id=task_id, correlation_id=f"test-{task_id}")


# ── Agent tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_workflow_evaluation(agent: PipelineAgent, context: AgentContext):
    """Complete run produces stage health, stagnation risk, and recommendation."""
    task = AgentTaskInput(
        id=context.task_id,
        agent_type="pipeline",
        input_data={
            "lead_id": str(uuid.uuid4()),
            "current_stage": "outreach",
            "days_in_stage": 14,
            "aggregated_data": {
                "research_task": {
                    "status": "completed",
                    "findings": {"industry": "Drone Services"},
                },
                "qualification_results": [
                    {"overall_score": 85, "priority": "HOT"}
                ],
                "outreach_drafts": [
                    {"status": "approved", "urgency": "Immediate"}
                ],
                "inbound_messages": [],
                "conversations": [],
            },
        },
    )

    result = await agent.run(context, task)

    assert result.requires_human_approval is False
    assert result.output_data["evaluation"]["stage_health"] == "stale"
    assert result.output_data["evaluation"]["stagnation_risk"] == "low"
    assert result.output_data["evaluation"]["current_stage"] == "outreach"
    assert result.output_data["recommended_action"]["type"] == "follow_up"


@pytest.mark.asyncio
async def test_healthy_lead_evaluation(agent: PipelineAgent, context: AgentContext):
    """New lead with low days → healthy."""
    task = AgentTaskInput(
        id=context.task_id,
        agent_type="pipeline",
        input_data={
            "lead_id": str(uuid.uuid4()),
            "current_stage": "new",
            "days_in_stage": 2,
            "aggregated_data": {},
        },
    )

    result = await agent.run(context, task)
    assert result.output_data["evaluation"]["stage_health"] == "healthy"
    assert result.output_data["evaluation"]["stagnation_risk"] == "low"


@pytest.mark.asyncio
async def test_critical_lead_evaluation(agent: PipelineAgent, context: AgentContext):
    """Lead stale for very long → critical."""
    task = AgentTaskInput(
        id=context.task_id,
        agent_type="pipeline",
        input_data={
            "lead_id": str(uuid.uuid4()),
            "current_stage": "new",
            "days_in_stage": 30,
            "aggregated_data": {},
        },
    )

    result = await agent.run(context, task)
    assert result.output_data["evaluation"]["stage_health"] == "critical"
    assert result.output_data["evaluation"]["stagnation_risk"] == "high"
    assert result.output_data["lead_health"]["reengagement_needed"] is True


@pytest.mark.asyncio
async def test_llm_evaluation_fallback(agent: PipelineAgent, context: AgentContext):
    """LLM fails → deterministic fallback used."""
    ai = FakePipelineAIProvider()

    async def failing_generate(request: AIRequest) -> AIResponse:
        raise RuntimeError("API unavailable")

    ai.generate = failing_generate  # type: ignore[method-assign]
    agent._ai = ai  # type: ignore[assignment]

    task = AgentTaskInput(
        id=context.task_id,
        agent_type="pipeline",
        input_data={
            "lead_id": str(uuid.uuid4()),
            "current_stage": "outreach",
            "days_in_stage": 5,
            "aggregated_data": {},
        },
    )

    result = await agent.run(context, task)
    assert result.output_data["evaluation"]["stage_health"] == "healthy"
    assert result.output_data["recommended_action"]["type"] in (
        "no_action", "follow_up"
    )


@pytest.mark.asyncio
async def test_no_history_lead(agent: PipelineAgent, context: AgentContext):
    """New lead with no history → sensible default assessment."""
    task = AgentTaskInput(
        id=context.task_id,
        agent_type="pipeline",
        input_data={
            "lead_id": str(uuid.uuid4()),
            "current_stage": "new",
            "days_in_stage": 0,
            "aggregated_data": {},
        },
    )

    result = await agent.run(context, task)
    assert result.output_data["evaluation"]["current_stage"] == "new"
    assert not result.requires_human_approval


@pytest.mark.asyncio
async def test_step_logging_events(agent: PipelineAgent, context: AgentContext):
    """All expected log events recorded during run."""
    task = AgentTaskInput(
        id=context.task_id,
        agent_type="pipeline",
        input_data={
            "lead_id": str(uuid.uuid4()),
            "current_stage": "outreach",
            "days_in_stage": 10,
            "aggregated_data": {},
        },
    )

    await agent.run(context, task)

    assert agent._tm.append_log.call_count >= 3
    call_events = [
        c.args[2] if len(c.args) > 2 else ""
        for c in agent._tm.append_log.call_args_list
    ]
    assert "pipeline_evaluation_started" in call_events
    assert "lead_data_aggregated" in call_events
    assert "deterministic_analysis_completed" in call_events
    assert "llm_evaluation_completed" in call_events
    assert "pipeline_evaluation_completed" in call_events
