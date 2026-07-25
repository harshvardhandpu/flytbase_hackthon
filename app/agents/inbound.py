from __future__ import annotations

import json
import uuid
from typing import Any

from app.core.contracts import (  # noqa: I001
    AgentContext,
    AgentResult,
    AgentTaskInput,
    AIMessage,
    AIProvider,
    AIRequest,
    BaseAgent,
    ProviderError,
)
from app.core.task_manager import TaskManager
from app.tools.tool_manager import ToolManager

_INTENT_PROMPT = """\
You are a BDR inbound message analyst. Classify the incoming message
by intent, sentiment, and urgency.

Intent options:
- question: The sender is asking a question about the product/service
- objection: The sender has concerns or objections
- purchase_intent: The sender is expressing purchase interest
- support_request: The sender needs help with an existing product
- meeting_request: The sender wants to schedule a meeting or demo
- unsubscribe: The sender wants to opt out of communications
- other: None of the above

Sentiment options: positive | neutral | negative
Urgency options: high | medium | low

Also extract structured details from the message.

Return ONLY a JSON object with these exact keys:
{
  "intent": "string",
  "sentiment": "string",
  "urgency": "string",
  "confidence": 0.0-1.0,
  "extracted_details": {
    "topics": ["topic1", "topic2"],
    "pain_points": ["pain point"],
    "interest_signals": ["signal"],
    "contact_role": "string or null",
    "company_size_hint": "string or null",
    "timeline_hint": "string or null"
  }
}
"""

_ACTION_PROMPT = """\
You are a BDR lead routing specialist. Determine the appropriate action
for this inbound message based on the intent analysis and lead context.

If the message requires a response, generate a suggested reply.
The reply should be professional, personalized, and include a clear CTA.

Rules:
- If sender is asking a question: suggest a helpful, informative reply
- If sender has an objection: address the concern directly
- If sender wants a meeting: suggest confirming with specific options
- If sender shows purchase intent: suggest a call-to-action
- If sender is unsubscribing: no reply needed
- If purely informational: no reply needed

lead_action options:
- create_lead: New prospect, needs a lead record
- update_lead: Existing lead, update status or notes
- no_action: No BDR action needed

Return ONLY a JSON object with these exact keys:
{
  "lead_action": "create_lead | update_lead | no_action",
  "suggested_status": "new | researching | qualified | meeting_requested | disqualified | null",
  "suggested_reply": {
    "subject": "string or null",
    "body": "string or null"
  },
  "follow_up_suggestion": "string or null",
  "needs_human_review": true | false,
  "notes": "string"
}
"""


class InboundAgent(BaseAgent):
    """BDR inbound message agent that classifies intent and generates replies.

    Workflow:
    1. Classify message intent, sentiment, urgency via LLM
    2. Extract structured details from the message
    3. Determine lead action and generate suggested reply via LLM
    4. Mark requires_human_approval if a reply was generated
    """

    agent_type = "inbound"

    def __init__(
        self,
        ai_provider: AIProvider,
        tool_manager: ToolManager,
        task_manager: TaskManager,
    ) -> None:
        self._ai = ai_provider
        self._tools = tool_manager
        self._tm = task_manager

    async def run(self, context: AgentContext, task: AgentTaskInput) -> AgentResult:
        task_id = context.task_id
        input_data = task.input_data
        message = input_data.get("message", {})
        lead_context = input_data.get("lead_context", {})

        # ── Step 1: Start ──────────────────────────────────────────────
        from_email = message.get("from_email", "unknown")
        channel = message.get("channel", "email")

        self._tm.append_log(
            task_id, "info", "inbound_started",
            f"Processing inbound message from {from_email} via {channel}",
            {"from_email": from_email, "channel": channel},
        )

        # ── Step 2: Intent analysis ────────────────────────────────────
        self._tm.append_log(
            task_id, "info", "intent_analysis_started",
            "Classifying message intent, sentiment, and urgency via LLM",
        )

        analysis = await self._analyze_intent(message, task_id)

        self._tm.append_log(
            task_id, "info", "intent_analysis_completed",
            f"Intent={analysis['intent']} sentiment={analysis['sentiment']} "
            f"urgency={analysis['urgency']} confidence={analysis['confidence']}",
            {
                "intent": analysis["intent"],
                "sentiment": analysis["sentiment"],
                "urgency": analysis["urgency"],
                "confidence": analysis["confidence"],
            },
        )

        # ── Step 3: Lead action + reply generation ─────────────────────
        self._tm.append_log(
            task_id, "info", "reply_generation_started",
            "Determining lead action and generating suggested reply via LLM",
        )

        action = await self._determine_action(
            message=message,
            analysis=analysis,
            lead_context=lead_context,
            task_id=task_id,
        )

        self._tm.append_log(
            task_id, "info", "reply_generation_completed",
            f"Lead action={action['lead_action']} "
            f"needs_human_review={action['needs_human_review']}",
            {"lead_action": action["lead_action"]},
        )

        # ── Step 4: Assemble output ──────────────────────────────────
        needs_approval = action.get("needs_human_review", False)
        if action.get("suggested_reply") and action["suggested_reply"].get("body"):
            needs_approval = True

        output_data: dict[str, Any] = {
            "analysis": {
                "intent": analysis.get("intent", "other"),
                "sentiment": analysis.get("sentiment", "neutral"),
                "urgency": analysis.get("urgency", "low"),
                "confidence": analysis.get("confidence", 0.0),
                "extracted_details": analysis.get("extracted_details", {}),
            },
            "lead_action": {
                "action": action.get("lead_action", "no_action"),
                "suggested_status": action.get("suggested_status"),
                "notes": action.get("notes", ""),
            },
            "suggested_reply": action.get("suggested_reply", {}),
            "follow_up_suggestion": action.get("follow_up_suggestion"),
            "requires_human_approval": needs_approval,
            "providers_used": getattr(self._ai, "name", "unknown"),
        }

        # ── Step 5: Complete ───────────────────────────────────────────
        summary = (
            f"Inbound message from {from_email}: "
            f"intent={analysis.get('intent', '?')} "
            f"sentiment={analysis.get('sentiment', '?')} "
            f"lead_action={action.get('lead_action', '?')}"
        )

        self._tm.append_log(
            task_id, "info", "inbound_completed",
            summary,
            {
                "requires_human_approval": needs_approval,
                "intent": analysis.get("intent"),
                "lead_action": action.get("lead_action"),
            },
        )

        return AgentResult(
            output_data=output_data,
            summary=summary,
            requires_human_approval=needs_approval,
        )

    # ── Intent analysis ─────────────────────────────────────────────────

    async def _analyze_intent(
        self,
        message: dict[str, Any],
        task_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Use LLM to classify intent, sentiment, and urgency."""
        fallback: dict[str, Any] = {
            "intent": "other",
            "sentiment": "neutral",
            "urgency": "low",
            "confidence": 0.0,
            "extracted_details": {
                "topics": [],
                "pain_points": [],
                "interest_signals": [],
                "contact_role": None,
                "company_size_hint": None,
                "timeline_hint": None,
            },
        }

        body = message.get("body", "")
        subject = message.get("subject", "")
        from_name = message.get("from_name", "")

        if not body:
            return fallback

        prompt = (
            f"From: {from_name}\n"
            f"Subject: {subject}\n"
            f"Body: {body}\n\n"
            "Classify this message and extract details.\n"
            "Return ONLY valid JSON matching the specified schema."
        )

        try:
            response = await self._ai.generate(
                AIRequest(
                    messages=[
                        AIMessage(role="system", content=_INTENT_PROMPT),
                        AIMessage(role="user", content=prompt),
                    ],
                    temperature=0.3,
                    max_tokens=500,
                    metadata={"agent": "inbound"},
                )
            )
            parsed = _parse_json_object(response.content)
            if parsed and isinstance(parsed, dict):
                return {
                    "intent": str(parsed.get("intent", "other")),
                    "sentiment": str(parsed.get("sentiment", "neutral")),
                    "urgency": str(parsed.get("urgency", "low")),
                    "confidence": float(parsed.get("confidence", 0.0)),
                    "extracted_details": parsed.get("extracted_details", {}),
                }
            return fallback
        except (ProviderError, Exception) as exc:
            self._tm.append_log(
                task_id, "error", "inbound_intent_failed",
                f"Intent analysis failed: {exc}",
                {"error": str(exc)},
            )
            return fallback

    # ── Lead action + reply generation ──────────────────────────────────

    async def _determine_action(
        self,
        message: dict[str, Any],
        analysis: dict[str, Any],
        lead_context: dict[str, Any],
        task_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Use LLM to determine lead action and generate suggested reply."""
        fallback: dict[str, Any] = {
            "lead_action": "no_action",
            "suggested_status": None,
            "suggested_reply": {},
            "follow_up_suggestion": None,
            "needs_human_review": False,
            "notes": "AI analysis unavailable — determined by fallback logic.",
        }

        body = message.get("body", "")
        subject = message.get("subject", "")
        from_name = message.get("from_name", "")

        intent = analysis.get("intent", "other")
        sentiment = analysis.get("sentiment", "neutral")
        urgency = analysis.get("urgency", "low")
        has_existing_lead = bool(lead_context.get("lead_id"))

        # Simple deterministic fallback for common cases
        if intent == "unsubscribe":
            return {
                "lead_action": "update_lead",
                "suggested_status": "disqualified",
                "suggested_reply": {},
                "follow_up_suggestion": None,
                "needs_human_review": False,
                "notes": "Unsubscribe request — marking lead as disqualified.",
            }

        if intent == "other" and not body:
            return {
                "lead_action": "no_action",
                "suggested_status": None,
                "suggested_reply": {},
                "follow_up_suggestion": None,
                "needs_human_review": False,
                "notes": "Empty or unrecognized message — no action taken.",
            }

        prompt = (
            f"From: {from_name}\n"
            f"Subject: {subject}\n"
            f"Body: {body}\n\n"
            f"Intent: {intent}\n"
            f"Sentiment: {sentiment}\n"
            f"Urgency: {urgency}\n"
            f"Has existing lead: {has_existing_lead}\n"
            f"Lead context: {json.dumps(lead_context, default=str)}\n\n"
            "Determine the lead action and generate a suggested reply if appropriate.\n"
            "Return ONLY valid JSON matching the specified schema."
        )

        try:
            response = await self._ai.generate(
                AIRequest(
                    messages=[
                        AIMessage(role="system", content=_ACTION_PROMPT),
                        AIMessage(role="user", content=prompt),
                    ],
                    temperature=0.3,
                    max_tokens=500,
                    metadata={"agent": "inbound"},
                )
            )
            parsed = _parse_json_object(response.content)
            if parsed and isinstance(parsed, dict):
                return {
                    "lead_action": str(parsed.get("lead_action", "no_action")),
                    "suggested_status": parsed.get("suggested_status"),
                    "suggested_reply": parsed.get("suggested_reply", {}),
                    "follow_up_suggestion": parsed.get("follow_up_suggestion"),
                    "needs_human_review": bool(
                        parsed.get("needs_human_review", False)
                    ),
                    "notes": str(parsed.get("notes", "")),
                }
            return fallback
        except (ProviderError, Exception) as exc:
            self._tm.append_log(
                task_id, "error", "inbound_reply_failed",
                f"Reply generation failed: {exc}",
                {"error": str(exc)},
            )
            return fallback


# ── JSON parsing helper ────────────────────────────────────────────────


def _parse_json_object(text: str) -> dict[str, Any] | None:
    """Best-effort parse of a JSON object from LLM output."""
    cleaned = text.strip()
    lines = cleaned.split("\n")
    cleaned = "\n".join(
        line for line in lines if not line.strip().startswith("```")
    ).strip()
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(cleaned[start: end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return None
