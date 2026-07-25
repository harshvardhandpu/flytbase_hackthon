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
from app.intelligence import CompanyIntelligenceBriefBuilder
from app.tools.tool_manager import ToolManager

# ── Prompts ────────────────────────────────────────────────────────────

_STRATEGY_PROMPT = """\
You are a BDR outreach strategist. Given a company's research profile and
qualification analysis, design the optimal outreach strategy.

Consider:
- The company's industry, signals, and pain points
- The qualification priority and urgency
- The sales angle recommended by the qualification analysis
- Which channel would be most effective for this type of lead

Return ONLY a JSON object with these exact keys:
{
  "recommended_channel": "email" | "linkedin" | "phone",
  "urgency": "Immediate" | "This week" | "This month",
  "reasoning": "2-3 sentence strategic rationale for the channel and urgency choice"
}
"""

_PERSONALIZATION_PROMPT = """\
You are a BDR personalization specialist. Given a company's research profile
and qualification analysis, craft personalized messaging intelligence for
FlytBase outreach.

FlytBase is a drone fleet management platform that enables enterprises to
operate drone fleets remotely for automated missions.

Return ONLY a JSON object with these exact keys:
{
  "company_hook": "A 1-2 sentence hook connecting FlytBase to this company's mission or achievement.",
  "detected_pain_point": "A 1-2 sentence description of the most relevant pain point from the research.",
  "flytbase_value_proposition": "A 1-2 sentence value proposition on how FlytBase solves the pain point."
}
"""  # noqa: E501

_DRAFT_PROMPT = """\
You are a senior BDR composing a personalized outreach email. Use the
outreach strategy and personalization intelligence provided.

Rules:
- Be specific and relevant to the recipient's company and role
- Reference the detected pain point early to show understanding
- Lead with value, not features
- Keep paragraphs short (2-3 sentences max)
- Include a clear, low-friction call to action
- Sound like a human, not a template
- Use {{first_name}} as a placeholder for the contact's first name

Return ONLY a JSON object with these exact keys:
{
  "subject": "A compelling, personalized subject line under 60 characters",
  "body": "Full email body with paragraphs, personalized hook, value prop, and CTA",
  "follow_up_suggestion": "A 1-2 sentence suggestion for when and how to follow up if no response"
}
"""


# ── Outreach Agent ─────────────────────────────────────────────────────


class OutreachAgent(BaseAgent):
    """BDR outreach agent that generates personalised email drafts.

    Workflow:
    1. Load company research and qualification context from task input
    2. Generate outreach strategy (channel, urgency, reasoning)
    3. Generate personalization intelligence (hook, pain point, value prop)
    4. Generate editable email draft (subject, body, follow-up)
    5. Mark result as requiring human approval (never auto-send)
    """

    agent_type = "outreach"

    def __init__(
        self,
        ai_provider: AIProvider,
        tool_manager: ToolManager,
        task_manager: TaskManager,
        intelligence_builder: CompanyIntelligenceBriefBuilder | None = None,
    ) -> None:
        self._ai = ai_provider
        self._tools = tool_manager
        self._tm = task_manager
        self._intelligence_builder = intelligence_builder or CompanyIntelligenceBriefBuilder()

    async def run(self, context: AgentContext, task: AgentTaskInput) -> AgentResult:
        task_id = context.task_id
        input_data = task.input_data

        # ── Step 1: Start ──────────────────────────────────────────────
        company_name = input_data.get("company_name", "")
        research_findings: dict[str, Any] = input_data.get("research_findings", {})
        qualification: dict[str, Any] = input_data.get("qualification", {})

        self._tm.append_log(
            task_id, "info", "outreach_started",
            f"Starting outreach generation for company={company_name!r}",
            {"company_name": company_name},
        )

        intelligence_brief = self._intelligence_builder.build(
            company_name=company_name,
            research=research_findings,
            qualification=qualification,
        )
        self._tm.append_log(
            task_id, "info", "intelligence_brief_generated",
            "Generated reusable company intelligence brief for approval review",
            {
                "source": intelligence_brief["source"],
                "problem_count": len(intelligence_brief["detected_business_problems"]),
            },
        )

        # ── Step 2: Context loaded ─────────────────────────────────────
        self._tm.append_log(
            task_id, "info", "context_loaded",
            f"Loaded research and qualification for {company_name!r}",
            {
                "has_research": bool(research_findings),
                "has_qualification": bool(qualification),
            },
        )

        # ── Step 3: Generate outreach strategy ─────────────────────────
        self._tm.append_log(
            task_id, "info", "strategy_generation_started",
            "Generating outreach strategy via LLM",
        )

        strategy = await self._generate_strategy(
            company_name=company_name,
            research=research_findings,
            qualification=qualification,
            task_id=task_id,
        )

        self._tm.append_log(
            task_id, "info", "strategy_generation_completed",
            f"Strategy generated: channel={strategy['recommended_channel']} "
            f"urgency={strategy['urgency']}",
            strategy,
        )

        # ── Step 4: Generate personalization intelligence ──────────────
        self._tm.append_log(
            task_id, "info", "personalization_started",
            "Generating personalization intelligence via LLM",
        )

        personalization = await self._generate_personalization(
            company_name=company_name,
            research=research_findings,
            qualification=qualification,
            strategy=strategy,
            task_id=task_id,
        )

        self._tm.append_log(
            task_id, "info", "personalization_completed",
            "Personalization generated",
            {
                "has_hook": bool(personalization.get("company_hook")),
                "has_pain_point": bool(personalization.get("detected_pain_point")),
                "has_value_prop": bool(personalization.get("flytbase_value_proposition")),
            },
        )

        # ── Step 5: Generate email draft ───────────────────────────────
        self._tm.append_log(
            task_id, "info", "draft_generation_started",
            "Generating email draft via LLM",
        )

        draft = await self._generate_draft(
            company_name=company_name,
            strategy=strategy,
            personalization=personalization,
            task_id=task_id,
        )

        self._tm.append_log(
            task_id, "info", "draft_generation_completed",
            "Email draft generated",
            {
                "subject_preview": draft.get("subject", "")[:60],
                "body_length": len(draft.get("body", "")),
            },
        )

        # ── Step 6: Assemble output ──────────────────────────────────
        output_data: dict[str, Any] = {
            "outreach_strategy": {
                "recommended_channel": strategy.get("recommended_channel", "email"),
                "urgency": strategy.get("urgency", "This week"),
                "reasoning": strategy.get("reasoning", ""),
            },
            "personalization": {
                "company_hook": personalization.get("company_hook", ""),
                "detected_pain_point": personalization.get("detected_pain_point", ""),
                "flytbase_value_proposition": personalization.get(
                    "flytbase_value_proposition", ""
                ),
            },
            "email_draft": {
                "subject": draft.get("subject", ""),
                "body": draft.get("body", ""),
                "follow_up_suggestion": draft.get("follow_up_suggestion", ""),
            },
            "company_intelligence": intelligence_brief,
            "requires_human_approval": True,
            "providers_used": getattr(self._ai, "name", "unknown"),
        }

        # ── Step 7: Complete ────────────────────────────────────────────
        summary = (
            f"Outreach draft generated for {company_name}: "
            f"channel={strategy.get('recommended_channel', 'email')} "
            f"urgency={strategy.get('urgency', 'This week')}"
        )

        self._tm.append_log(
            task_id, "info", "outreach_completed",
            summary,
            {"requires_human_approval": True},
        )

        return AgentResult(
            output_data=output_data,
            summary=summary,
            requires_human_approval=True,
        )

    # ── Strategy generation ─────────────────────────────────────────────

    async def _generate_strategy(
        self,
        company_name: str,
        research: dict[str, Any],
        qualification: dict[str, Any],
        task_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Use LLM to determine outreach channel, urgency, and reasoning."""
        fallback: dict[str, Any] = {
            "recommended_channel": "email",
            "urgency": "This week",
            "reasoning": f"Outreach via email for {company_name}.",
        }

        prompt = self._build_strategy_prompt(company_name, research, qualification)

        try:
            response = await self._ai.generate(
                AIRequest(
                    messages=[
                        AIMessage(role="system", content=_STRATEGY_PROMPT),
                        AIMessage(role="user", content=prompt),
                    ],
                    temperature=0.3,
                    max_tokens=500,
                    metadata={"agent": "outreach"},
                )
            )
            parsed = _parse_json_object(response.content)
            if parsed and isinstance(parsed, dict):
                return {
                    "recommended_channel": str(
                        parsed.get("recommended_channel", "email")
                    ),
                    "urgency": str(parsed.get("urgency", "This week")),
                    "reasoning": str(parsed.get("reasoning", "")),
                }
            return fallback
        except (ProviderError, Exception) as exc:
            self._tm.append_log(
                task_id, "error", "outreach_strategy_failed",
                f"Strategy generation failed: {exc}",
                {"error": str(exc)},
            )
            return fallback

    # ── Personalization generation ──────────────────────────────────────

    async def _generate_personalization(
        self,
        company_name: str,
        research: dict[str, Any],
        qualification: dict[str, Any],
        strategy: dict[str, Any],
        task_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Use LLM to craft personalized messaging intelligence."""
        fallback: dict[str, Any] = {
            "company_hook": "",
            "detected_pain_point": "",
            "flytbase_value_proposition": "",
        }

        prompt = self._build_personalization_prompt(
            company_name, research, qualification, strategy
        )

        try:
            response = await self._ai.generate(
                AIRequest(
                    messages=[
                        AIMessage(role="system", content=_PERSONALIZATION_PROMPT),
                        AIMessage(role="user", content=prompt),
                    ],
                    temperature=0.3,
                    max_tokens=500,
                    metadata={"agent": "outreach"},
                )
            )
            parsed = _parse_json_object(response.content)
            if parsed and isinstance(parsed, dict):
                return {
                    "company_hook": str(parsed.get("company_hook", "")),
                    "detected_pain_point": str(
                        parsed.get("detected_pain_point", "")
                    ),
                    "flytbase_value_proposition": str(
                        parsed.get("flytbase_value_proposition", "")
                    ),
                }
            return fallback
        except (ProviderError, Exception) as exc:
            self._tm.append_log(
                task_id, "error", "outreach_personalization_failed",
                f"Personalization generation failed: {exc}",
                {"error": str(exc)},
            )
            return fallback

    # ── Draft generation ────────────────────────────────────────────────

    async def _generate_draft(
        self,
        company_name: str,
        strategy: dict[str, Any],
        personalization: dict[str, Any],
        task_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Use LLM to compose the full email draft."""
        fallback: dict[str, Any] = {
            "subject": f"Introduction: {company_name}",
            "body": "",
            "follow_up_suggestion": "",
        }

        prompt = self._build_draft_prompt(company_name, strategy, personalization)

        try:
            response = await self._ai.generate(
                AIRequest(
                    messages=[
                        AIMessage(role="system", content=_DRAFT_PROMPT),
                        AIMessage(role="user", content=prompt),
                    ],
                    temperature=0.3,
                    max_tokens=500,
                    metadata={"agent": "outreach"},
                )
            )
            parsed = _parse_json_object(response.content)
            if parsed and isinstance(parsed, dict):
                return {
                    "subject": str(parsed.get("subject", fallback["subject"])),
                    "body": str(parsed.get("body", "")),
                    "follow_up_suggestion": str(
                        parsed.get("follow_up_suggestion", "")
                    ),
                }
            return fallback
        except (ProviderError, Exception) as exc:
            self._tm.append_log(
                task_id, "error", "outreach_draft_failed",
                f"Draft generation failed: {exc}",
                {"error": str(exc)},
            )
            return fallback

    # ── Prompt builders ─────────────────────────────────────────────────

    @staticmethod
    def _build_strategy_prompt(
        company_name: str,
        research: dict[str, Any],
        qualification: dict[str, Any],
    ) -> str:
        qual_action = qualification.get("recommended_bdr_action", {})
        lines = [
            f"Company: {company_name}",
            f"Industry: {research.get('industry', 'Unknown')}",
            f"Description: {research.get('description', '')}",
            f"Business Signals: {json.dumps(research.get('business_signals', []))}",
            f"Pain Points: {json.dumps(research.get('pain_points', []))}",
            f"FlytBase Relevance: {research.get('flytbase_relevance', 'Unknown')}",
            f"Qualification Score: {qualification.get('overall_score', 'N/A')}/100",
            f"Qualification Priority: {qualification.get('priority', 'N/A')}",
            f"Recommended Sales Angle: {qual_action.get('suggested_sales_angle', 'N/A')}",
            f"Qualification Urgency: {qual_action.get('urgency', 'N/A')}",
        ]
        return "\n".join(lines)

    @staticmethod
    def _build_personalization_prompt(
        company_name: str,
        research: dict[str, Any],
        qualification: dict[str, Any],
        strategy: dict[str, Any],
    ) -> str:
        qual_action = qualification.get("recommended_bdr_action", {})
        lines = [
            f"Company: {company_name}",
            f"Industry: {research.get('industry', 'Unknown')}",
            f"Description: {research.get('description', '')}",
            f"Business Signals: {json.dumps(research.get('business_signals', []))}",
            f"Pain Points: {json.dumps(research.get('pain_points', []))}",
            f"Technology Signals: {json.dumps(research.get('technology_signals', []))}",
            f"FlytBase Relevance: {research.get('flytbase_relevance', 'Unknown')}",
            f"Sales Angle: {qual_action.get('suggested_sales_angle', 'N/A')}",
            f"Recommended Channel: {strategy.get('recommended_channel', 'email')}",
        ]
        return "\n".join(lines)

    @staticmethod
    def _build_draft_prompt(
        company_name: str,
        strategy: dict[str, Any],
        personalization: dict[str, Any],
    ) -> str:
        lines = [
            f"Company: {company_name}",
            f"Channel: {strategy.get('recommended_channel', 'email')}",
            f"Urgency: {strategy.get('urgency', 'This week')}",
            f"Company Hook: {personalization.get('company_hook', '')}",
            f"Detected Pain Point: {personalization.get('detected_pain_point', '')}",
            f"FlytBase Value Proposition: {personalization.get('flytbase_value_proposition', '')}",
        ]
        return "\n".join(lines)


# ── JSON parsing helper ────────────────────────────────────────────────


def _parse_json_object(text: str) -> dict[str, Any] | None:
    """Best-effort parse of a JSON object from LLM output."""
    cleaned = text.strip()
    # Strip code fences
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
