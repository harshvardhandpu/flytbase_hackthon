"""Tests for InboundAgent — intent analysis, reply generation, step logging."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.agents.inbound import InboundAgent
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


class FakeInboundAIProvider:
    """Fake AI provider that returns canned responses for inbound tests."""

    name = "fake-inbound"

    def __init__(self) -> None:
        self.call_count = 0

    async def generate(self, request: AIRequest) -> AIResponse:
        self.call_count += 1
        if self.call_count == 1:
            # Intent analysis response
            return AIResponse(
                content=(
                    '{\n'
                    '  "intent": "meeting_request",\n'
                    '  "sentiment": "positive",\n'
                    '  "urgency": "high",\n'
                    '  "confidence": 0.92,\n'
                    '  "extracted_details": {\n'
                    '    "topics": ["demo", "fleet management"],\n'
                    '    "pain_points": ["manual workflows"],\n'
                    '    "interest_signals": ["requested demo"],\n'
                    '    "contact_role": "Operations Director",\n'
                    '    "company_size_hint": "50+ drones",\n'
                    '    "timeline_hint": "this quarter"\n'
                    '  }\n'
                    '}'
                ),
                provider="fake-inbound",
            )
        else:
            # Reply generation response
            return AIResponse(
                content=(
                    '{\n'
                    '  "lead_action": "update_lead",\n'
                    '  "suggested_status": "meeting_requested",\n'
                    '  "suggested_reply": {\n'
                    '    "subject": "Re: Demo Request",\n'
                    '    "body": "Hi, thanks for reaching out!"\n'
                    '  },\n'
                    '  "follow_up_suggestion": "Follow up in 3 days",\n'
                    '  "needs_human_review": true,\n'
                    '  "notes": "High intent lead"\n'
                    '}'
                ),
                provider="fake-inbound",
            )


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def task_id() -> UUID:
    return uuid.uuid4()


@pytest.fixture
def agent() -> InboundAgent:
    ai: AIProvider = FakeInboundAIProvider()  # type: ignore[assignment]
    tm = MagicMock(spec=TaskManager)
    tools = MagicMock(spec=ToolManager)
    return InboundAgent(ai_provider=ai, tool_manager=tools, task_manager=tm)


@pytest.fixture
def context(task_id: UUID) -> AgentContext:
    return AgentContext(task_id=task_id, correlation_id=f"test-{task_id}")


# ── Tests ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_workflow_new_inquiry(agent: InboundAgent, context: AgentContext):
    """Complete run: classifies intent, determines lead action, generates reply."""
    task = AgentTaskInput(
        id=context.task_id,
        agent_type="inbound",
        input_data={
            "message": {
                "from_email": "john@skygrid.io",
                "from_name": "John Smith",
                "subject": "Demo Request",
                "body": "Hi, we'd like to schedule a demo of your platform.",
                "channel": "email",
            },
            "lead_context": {},
        },
    )

    result = await agent.run(context, task)

    assert result.requires_human_approval is True
    assert result.output_data["analysis"]["intent"] == "meeting_request"
    assert result.output_data["analysis"]["sentiment"] == "positive"
    assert result.output_data["analysis"]["urgency"] == "high"
    assert result.output_data["lead_action"]["action"] == "update_lead"
    assert "suggested_reply" in result.output_data


@pytest.mark.asyncio
async def test_intent_classification_meeting_request(
    agent: InboundAgent, context: AgentContext
):
    """'Can we schedule a demo?' → intent = meeting_request."""
    task = AgentTaskInput(
        id=context.task_id,
        agent_type="inbound",
        input_data={
            "message": {
                "from_email": "lead@example.com",
                "subject": "Demo",
                "body": "Can we schedule a demo for next week?",
                "channel": "email",
            },
            "lead_context": {},
        },
    )

    result = await agent.run(context, task)
    assert result.output_data["analysis"]["intent"] == "meeting_request"


@pytest.mark.asyncio
async def test_intent_classification_objection(
    agent: InboundAgent, context: AgentContext
):
    """'Your pricing is too high' → intent = objection."""
    # Override the fake to return objection
    ai = FakeInboundAIProvider()

    async def objection_generate(request: AIRequest) -> AIResponse:
        ai.call_count += 1
        if ai.call_count == 1:
            return AIResponse(
                content=(
                    '{"intent": "objection", "sentiment": "negative", '
                    '"urgency": "medium", "confidence": 0.85, '
                    '"extracted_details": {}}'
                ),
                provider="fake-inbound",
            )
        return AIResponse(
            content='{"lead_action": "no_action", "needs_human_review": true, "suggested_reply": {"body": "Let me address your concerns."}}',  # noqa: E501
            provider="fake-inbound",
        )

    ai.generate = objection_generate  # type: ignore[method-assign]
    agent._ai = ai  # type: ignore[assignment]

    task = AgentTaskInput(
        id=context.task_id,
        agent_type="inbound",
        input_data={
            "message": {
                "from_email": "objector@example.com",
                "body": "Your pricing is too high for our budget.",
                "channel": "email",
            },
            "lead_context": {},
        },
    )

    result = await agent.run(context, task)
    assert result.output_data["analysis"]["intent"] == "objection"


@pytest.mark.asyncio
async def test_sentiment_detection_positive(
    agent: InboundAgent, context: AgentContext
):
    """Positive language → sentiment = positive."""
    task = AgentTaskInput(
        id=context.task_id,
        agent_type="inbound",
        input_data={
            "message": {
                "from_email": "happy@example.com",
                "body": "Love your platform! Very interested.",
                "channel": "email",
            },
            "lead_context": {},
        },
    )

    result = await agent.run(context, task)
    assert result.output_data["analysis"]["sentiment"] == "positive"


@pytest.mark.asyncio
async def test_handles_existing_lead(agent: InboundAgent, context: AgentContext):
    """lead_id provided → uses existing context, doesn't create new."""
    task = AgentTaskInput(
        id=context.task_id,
        agent_type="inbound",
        input_data={
            "message": {
                "from_email": "existing@example.com",
                "body": "Following up on my previous message.",
                "channel": "email",
            },
            "lead_context": {"lead_id": "existing-lead-uuid"},
        },
    )

    result = await agent.run(context, task)
    assert result.output_data["analysis"]["intent"] is not None
    assert "suggested_reply" in result.output_data


@pytest.mark.asyncio
async def test_requires_approval_for_reply(
    agent: InboundAgent, context: AgentContext
):
    """Reply generated → requires_human_approval = True."""
    task = AgentTaskInput(
        id=context.task_id,
        agent_type="inbound",
        input_data={
            "message": {
                "from_email": "reply@example.com",
                "body": "I'm interested in learning more about your product.",
                "channel": "email",
            },
            "lead_context": {},
        },
    )

    result = await agent.run(context, task)
    assert result.requires_human_approval is True


@pytest.mark.asyncio
async def test_step_logging_events(agent: InboundAgent, context: AgentContext):
    """All expected log events recorded during run."""
    task = AgentTaskInput(
        id=context.task_id,
        agent_type="inbound",
        input_data={
            "message": {
                "from_email": "logtest@example.com",
                "body": "I'd like to learn more.",
                "channel": "email",
            },
            "lead_context": {},
        },
    )

    await agent.run(context, task)

    # Verify TaskManager.append_log was called
    assert agent._tm.append_log.call_count >= 4
    call_events = [
        c.args[2] if len(c.args) > 2 else ""
        for c in agent._tm.append_log.call_args_list
    ]
    assert "inbound_started" in call_events
    assert "intent_analysis_started" in call_events
    assert "intent_analysis_completed" in call_events
    assert "reply_generation_started" in call_events
    assert "reply_generation_completed" in call_events
    assert "inbound_completed" in call_events


@pytest.mark.asyncio
async def test_handles_empty_message_gracefully(
    agent: InboundAgent, context: AgentContext
):
    """Empty body → fallback with no_action."""
    ai = FakeInboundAIProvider()

    async def empty_generate(request: AIRequest) -> AIResponse:
        ai.call_count += 1
        return AIResponse(
            content='{"intent": "other", "sentiment": "neutral", "urgency": "low", "confidence": 0.0, "extracted_details": {}}',  # noqa: E501
            provider="fake-inbound",
        )

    ai.generate = empty_generate  # type: ignore[method-assign]
    agent._ai = ai  # type: ignore[assignment]

    task = AgentTaskInput(
        id=context.task_id,
        agent_type="inbound",
        input_data={
            "message": {
                "from_email": "empty@example.com",
                "body": "",
                "channel": "email",
            },
            "lead_context": {},
        },
    )

    result = await agent.run(context, task)
    assert result.output_data["analysis"]["intent"] in ("other", "unknown")
    assert result.requires_human_approval is False


@pytest.mark.asyncio
async def test_llm_intent_fallback(agent: InboundAgent, context: AgentContext):
    """LLM fails → fallback response used."""
    ai = FakeInboundAIProvider()

    async def failing_generate(request: AIRequest) -> AIResponse:
        raise RuntimeError("API unavailable")

    ai.generate = failing_generate  # type: ignore[method-assign]
    agent._ai = ai  # type: ignore[assignment]

    task = AgentTaskInput(
        id=context.task_id,
        agent_type="inbound",
        input_data={
            "message": {
                "from_email": "fail@example.com",
                "body": "Test message for fallback.",
                "channel": "email",
            },
            "lead_context": {},
        },
    )

    result = await agent.run(context, task)
    assert result.output_data["analysis"]["intent"] == "other"
    assert result.output_data["analysis"]["sentiment"] == "neutral"


@pytest.mark.asyncio
async def test_extracted_details_in_output(
    agent: InboundAgent, context: AgentContext
):
    """Extracted details should be present in output."""
    task = AgentTaskInput(
        id=context.task_id,
        agent_type="inbound",
        input_data={
            "message": {
                "from_email": "details@example.com",
                "body": "We operate 50+ drones for infrastructure inspection.",
                "channel": "email",
            },
            "lead_context": {},
        },
    )

    result = await agent.run(context, task)
    details = result.output_data["analysis"].get("extracted_details", {})
    assert isinstance(details, dict)
