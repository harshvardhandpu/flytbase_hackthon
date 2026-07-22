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

# ── Deterministic stage health rules ────────────────────────────────────

_STAGE_TIMEOUTS: dict[str, int] = {
    "new": 7,
    "researching": 5,
    "qualified": 3,
    "outreach": 7,
    "meeting_scheduled": 14,
    "negotiation": 30,
    "closed_won": 999,
    "closed_lost": 999,
}


def _compute_stage_health(current_stage: str, days_in_stage: int) -> str:
    """Determine stage health based on time in current stage."""
    timeout = _STAGE_TIMEOUTS.get(current_stage, 7)
    if days_in_stage > timeout * 2:
        return "critical"
    if days_in_stage > timeout:
        return "stale"
    return "healthy"


def _compute_stagnation_risk(days_in_stage: int, engagement_count: int) -> str:
    """Determine stagnation risk based on time and engagement."""
    if days_in_stage > 21 and engagement_count == 0:
        return "high"
    if days_in_stage > 14:
        return "moderate"
    return "low"


# ── LLM prompt ─────────────────────────────────────────────────────────


_EVALUATION_PROMPT = """\
You are a BDR pipeline analyst. Evaluate a lead's pipeline position and
recommend the next best action for the BDR team.

Consider:
- Current stage and days spent in it
- Stage health (healthy / stale / critical)
- Stagnation risk (low / moderate / high)
- Engagement signals from the lead's history
- Overall lead health from research and qualification data

Return ONLY a JSON object with these exact keys:
{
  "overall_health": "good | fair | poor",
  "engagement_level": "high | medium | low | none",
  "signal_decay": "low | moderate | high",
  "reengagement_needed": true | false,
  "recommended_action": {
    "type": "advance | follow_up | nurture | re_qualify | close | no_action",
    "channel": "email | phone | linkedin | none",
    "stage_transition": "string (target stage name or null)",
    "priority": "urgent | soon | monitor",
    "action": "1-2 sentence specific action recommendation",
    "reasoning": "2-3 sentence explanation of the recommendation"
  }
}
"""


class PipelineAgent(BaseAgent):
    """BDR pipeline agent that evaluates lead position and recommends actions.

    Workflow:
    1. Load aggregated lead data from task input
    2. Compute deterministic stage health and stagnation risk
    3. Use LLM to evaluate pipeline position and recommend next action
    4. Return recommendations (no auto-transition — BDR decides)
    """

    agent_type = "pipeline"

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

        # ── Step 1: Start ──────────────────────────────────────────────
        lead_id = str(input_data.get("lead_id", ""))
        current_stage = input_data.get("current_stage", "new")
        days_in_stage = input_data.get("days_in_stage", 0)
        aggregated = input_data.get("aggregated_data", {})

        self._tm.append_log(
            task_id, "info", "pipeline_evaluation_started",
            f"Starting pipeline evaluation for lead={lead_id} "
            f"stage={current_stage} days_in_stage={days_in_stage}",
            {"lead_id": lead_id, "current_stage": current_stage},
        )

        # ── Step 2: Aggregate lead data ────────────────────────────────
        engagement_count = self._count_engagements(aggregated)

        self._tm.append_log(
            task_id, "info", "lead_data_aggregated",
            f"Aggregated {engagement_count} engagement signals for lead",
            {"engagement_count": engagement_count},
        )

        # ── Step 3: Deterministic analysis ─────────────────────────────
        self._tm.append_log(
            task_id, "debug", "deterministic_analysis_started",
            "Computing stage health and stagnation risk",
        )

        stage_health = _compute_stage_health(current_stage, days_in_stage)
        stagnation_risk = _compute_stagnation_risk(days_in_stage, engagement_count)
        reengagement_needed = stage_health in ("stale", "critical")

        self._tm.append_log(
            task_id, "info", "deterministic_analysis_completed",
            f"Stage health={stage_health} stagnation_risk={stagnation_risk}",
            {
                "stage_health": stage_health,
                "stagnation_risk": stagnation_risk,
                "reengagement_needed": reengagement_needed,
            },
        )

        # ── Step 4: LLM evaluation ─────────────────────────────────────
        self._tm.append_log(
            task_id, "info", "llm_evaluation_started",
            "Evaluating pipeline position and recommending next action via LLM",
        )

        evaluation = await self._evaluate_pipeline(
            lead_id=lead_id,
            current_stage=current_stage,
            days_in_stage=days_in_stage,
            stage_health=stage_health,
            stagnation_risk=stagnation_risk,
            engagement_count=engagement_count,
            aggregated=aggregated,
            task_id=task_id,
        )

        self._tm.append_log(
            task_id, "info", "llm_evaluation_completed",
            f"Overall health={evaluation.get('overall_health', '?')} "
            f"recommended={evaluation.get('recommended_action', {}).get('type', '?')}",
            evaluation,
        )

        # ── Step 5: Assemble output ──────────────────────────────────
        output_data: dict[str, Any] = {
            "lead_id": lead_id,
            "evaluation": {
                "current_stage": current_stage,
                "stage_health": stage_health,
                "days_in_stage": days_in_stage,
                "stagnation_risk": stagnation_risk,
            },
            "lead_health": {
                "overall_health": evaluation.get("overall_health", "fair"),
                "engagement_level": evaluation.get("engagement_level", "low"),
                "signal_decay": evaluation.get("signal_decay", "moderate"),
                "reengagement_needed": reengagement_needed,
            },
            "recommended_action": evaluation.get("recommended_action", {}),
            "providers_used": getattr(self._ai, "name", "unknown"),
        }

        # ── Step 6: Complete ───────────────────────────────────────────
        summary = (
            f"Pipeline evaluation for lead={lead_id}: "
            f"stage={current_stage} health={stage_health} "
            f"recommended={evaluation.get('recommended_action', {}).get('type', '?')}"
        )

        self._tm.append_log(
            task_id, "info", "pipeline_evaluation_completed",
            summary,
            {"stage_health": stage_health, "stagnation_risk": stagnation_risk},
        )

        return AgentResult(
            output_data=output_data,
            summary=summary,
            requires_human_approval=False,
        )

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _count_engagements(aggregated: dict[str, Any]) -> int:
        """Count total engagement signals from lead history."""
        count = 0
        for key in ("inbound_messages", "conversations"):
            items = aggregated.get(key, [])
            if isinstance(items, list):
                count += len(items)
        tasks = aggregated.get("research_task", {})
        if tasks.get("status") == "completed":
            count += 1
        qual_results = aggregated.get("qualification_results", [])
        if isinstance(qual_results, list):
            count += len(qual_results)
        drafts = aggregated.get("outreach_drafts", [])
        if isinstance(drafts, list):
            for d in drafts:
                if d.get("status") == "approved":
                    count += 1
        return count

    # ── LLM pipeline evaluation ─────────────────────────────────────────

    async def _evaluate_pipeline(
        self,
        lead_id: str,
        current_stage: str,
        days_in_stage: int,
        stage_health: str,
        stagnation_risk: str,
        engagement_count: int,
        aggregated: dict[str, Any],
        task_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Use LLM to evaluate pipeline position and recommend next action."""
        # Determine reengagement need from deterministic rules
        needs_reengagement = stage_health in ("stale", "critical")

        # Build a concise summary of aggregated data for the LLM
        data_summary = self._build_data_summary(aggregated)

        fallback: dict[str, Any] = {
            "overall_health": "fair",
            "engagement_level": "low",
            "signal_decay": "moderate",
            "reengagement_needed": needs_reengagement,
            "recommended_action": {
                "type": "follow_up" if stage_health in ("stale", "critical")
                else "no_action",
                "channel": "email",
                "stage_transition": None,
                "priority": "urgent" if stage_health == "critical"
                else "soon" if stage_health == "stale" else "monitor",
                "action": f"Lead is in {current_stage} for {days_in_stage} days "
                f"(health: {stage_health}). Recommend BDR review.",
                "reasoning": "LLM evaluation unavailable — deterministic fallback.",
            },
        }

        prompt = (
            f"Lead ID: {lead_id}\n"
            f"Current Stage: {current_stage}\n"
            f"Days in Stage: {days_in_stage}\n"
            f"Stage Health: {stage_health}\n"
            f"Stagnation Risk: {stagnation_risk}\n"
            f"Engagement Count: {engagement_count}\n\n"
            f"Aggregated Lead Data:\n{data_summary}\n\n"
            "Evaluate this lead's pipeline position and recommend the next best action.\n"
            "Return ONLY valid JSON matching the specified schema."
        )

        try:
            response = await self._ai.generate(
                AIRequest(
                    messages=[
                        AIMessage(role="system", content=_EVALUATION_PROMPT),
                        AIMessage(role="user", content=prompt),
                    ],
                    temperature=0.3,
                )
            )
            parsed = _parse_json_object(response.content)
            if parsed and isinstance(parsed, dict):
                return {
                    "overall_health": str(
                        parsed.get("overall_health", "fair")
                    ),
                    "engagement_level": str(
                        parsed.get("engagement_level", "low")
                    ),
                    "signal_decay": str(parsed.get("signal_decay", "moderate")),
                    "reengagement_needed": bool(
                        parsed.get("reengagement_needed", needs_reengagement)
                    ),
                    "recommended_action": parsed.get("recommended_action", {}),
                }
            return fallback
        except (ProviderError, Exception) as exc:
            self._tm.append_log(
                task_id, "error", "pipeline_evaluation_failed",
                f"LLM evaluation failed: {exc}",
                {"error": str(exc)},
            )
            return fallback

    @staticmethod
    def _build_data_summary(aggregated: dict[str, Any]) -> str:
        """Build a concise text summary of aggregated lead data."""
        parts: list[str] = []

        research = aggregated.get("research_task", {})
        if research.get("status") == "completed":
            findings = research.get("findings", {})
            parts.append(
                f"Research: {findings.get('industry', '?')}, "
                f"relevance={findings.get('flytbase_relevance', '?')}"
            )

        quals = aggregated.get("qualification_results", [])
        if quals and isinstance(quals, list):
            qual = quals[-1] if quals else {}
            parts.append(
                f"Qualification: score={qual.get('overall_score', '?')}/100 "
                f"priority={qual.get('priority', '?')}"
            )

        drafts = aggregated.get("outreach_drafts", [])
        if drafts and isinstance(drafts, list):
            latest = drafts[-1] if drafts else {}
            parts.append(
                f"Outreach: status={latest.get('status', '?')} "
                f"urgency={latest.get('urgency', '?')}"
            )

        messages = aggregated.get("inbound_messages", [])
        if messages and isinstance(messages, list):
            latest_msg = messages[-1] if messages else {}
            parts.append(
                f"Last inbound: intent={latest_msg.get('intent', '?')} "
                f"sentiment={latest_msg.get('sentiment', '?')}"
            )

        conversations = aggregated.get("conversations", [])
        if conversations and isinstance(conversations, list):
            conv_count = len(conversations)
            directions = [
                c.get("direction", "?") for c in conversations[-3:]
            ]
            parts.append(
                f"Conversations: {conv_count} total "
                f"(recent: {', '.join(directions)})"
            )

        if not parts:
            parts.append("No aggregated data available for this lead.")

        return "\n".join(parts)


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
