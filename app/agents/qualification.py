from __future__ import annotations

import json
import uuid
from typing import Any

from app.core.contracts import (
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

# ── ICP config helpers ─────────────────────────────────────────────────


class IcpRules:
    """In-memory snapshot of ICP rules used for deterministic scoring."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.industries: list[str] = config.get("industries", [])
        self.min_employees: int | None = config.get("min_employees")
        self.max_employees: int | None = config.get("max_employees")
        self.locations: list[str] = config.get("locations", [])

    @staticmethod
    def default() -> IcpRules:
        return IcpRules(
            {
                "industries": [
                    "Mining", "Manufacturing", "Logistics", "Energy",
                    "Drone Technology", "SaaS", "Automation",
                    "Enterprise Software", "Healthcare",
                ],
                "min_employees": 10,
                "max_employees": 5000,
                "locations": ["US", "EU", "IN", "UK", "AU", "CA"],
            }
        )


# ── Prompts ────────────────────────────────────────────────────────────


_BUYING_SIGNAL_PROMPT = """\
You are a BDR qualification analyst. Evaluate the buying signals and
company fit from a company's research profile for FlytBase relevance.

FlytBase is a drone fleet management platform that enables enterprises
to operate drones remotely for automated missions.

Score the following dimensions 0-100 based on the provided data:

BUYING SIGNALS (0-100):
- Quality of business signals (funding, hiring, expansion)
- Relevance of pain points to drone automation
- Urgency indicators (recent initiatives, budget allocation)

COMPANY FIT (0-100):
- Technology stack compatibility with drone platforms
- Strategic alignment with FlytBase solutions
- Description and product/service overlap

Return ONLY a JSON object with these keys:
{
  "buying_signal_score": 0-100,
  "company_fit_score": 0-100,
  "reasons": ["reason 1", "reason 2"],
  "risks": ["risk 1", "risk 2"],
  "reasoning": "2-3 sentence explanation"
}

Use only information present in the data. Do NOT fabricate scores."""


_COMPOSITE_PROMPT = """\
You are a lead scoring analyst. Given the ICP match score, buying signal
score, company fit score, and the company's research profile, determine
the overall lead score and recommended BDR action.

Rules:
- overall_score: 0-100 weighted assessment
- priority: HOT (>=70), WARM (>=40), COLD (<40)
- urgency: "Immediate" for HOT, "This week" for WARM, "This month" for COLD
- sales_angle: A 1-2 sentence suggested sales approach based on
  the company's pain points and FlytBase relevance

Return ONLY a JSON object with these keys:
{
  "overall_score": 0-100,
  "priority": "HOT" | "WARM" | "COLD",
  "urgency": "Immediate" | "This week" | "This month",
  "sales_angle": "Suggested approach...",
  "reasons": ["reason 1", "reason 2"],
  "reasoning": "2-3 sentence explanation"
}"""


# ── Qualification Agent ────────────────────────────────────────────────


class QualificationAgent(BaseAgent):
    """BDR qualification agent that scores lead fit against ICP.

    Workflow:
    1. Load research report findings and ICP config from task input
    2. Compute deterministic ICP match score (industry, size, location)
    3. Use LLM to evaluate buying signals and company fit
    4. Compute composite overall score and assign priority
    5. Generate recommended BDR action (urgency + sales angle)
    6. Persist QualificationResult via output_data
    """

    agent_type = "qualification"

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
        report_id = input_data.get("report_id", "")
        company_name = input_data.get("company_name", "")
        findings: dict[str, Any] = input_data.get("findings", {})
        inline_icp: dict[str, Any] | None = input_data.get("icp_config")

        self._tm.append_log(
            task_id, "info", "qualification_started",
            f"Starting qualification for company={company_name!r} "
            f"report_id={report_id}",
            {"company_name": company_name, "report_id": report_id},
        )

        # ── Step 2: Resolve ICP config ─────────────────────────────────
        icp = IcpRules(inline_icp) if inline_icp else IcpRules.default()

        self._tm.append_log(
            task_id, "info", "icp_config_loaded",
            f"Using ICP config with industries={icp.industries}",
            {"industries": icp.industries, "locations": icp.locations},
        )

        # ── Step 3: Deterministic ICP match scoring ────────────────────
        self._tm.append_log(
            task_id, "debug", "deterministic_scoring_started",
            "Computing deterministic ICP match score",
        )

        icp_score, icp_reasons = self._compute_icp_match(findings, icp)

        self._tm.append_log(
            task_id, "debug", "deterministic_scoring_completed",
            f"ICP match score={icp_score}",
            {"icp_match_score": icp_score, "reasons": icp_reasons},
        )

        # ── Step 4: AI scoring (buying signals + company fit) ──────────
        self._tm.append_log(
            task_id, "info", "ai_scoring_started",
            "Evaluating buying signals and company fit via LLM",
        )

        buying_score, fit_score, ai_reasons, ai_risks, ai_reasoning = (
            await self._score_signals(findings, task_id)
        )

        self._tm.append_log(
            task_id, "info", "ai_scoring_completed",
            f"Buying signal score={buying_score} company fit score={fit_score}",
            {
                "buying_signal_score": buying_score,
                "company_fit_score": fit_score,
            },
        )

        # ── Step 5: Composite score + BDR action recommendation ────────
        self._tm.append_log(
            task_id, "info", "composite_scoring_started",
            "Computing overall score and BDR action recommendation",
        )

        overall_score, priority, urgency, sales_angle, composite_reasons, \
            composite_reasoning = await self._compute_composite(
                icp_score=icp_score,
                buying_score=buying_score,
                fit_score=fit_score,
                company_name=company_name,
                findings=findings,
                task_id=task_id,
            )

        self._tm.append_log(
            task_id, "info", "priority_assigned",
            f"Priority={priority} overall_score={overall_score}",
            {
                "overall_score": overall_score,
                "priority": priority,
                "urgency": urgency,
            },
        )

        # ── Step 6: Build output ──────────────────────────────────────
        all_reasons = list(dict.fromkeys(icp_reasons + ai_reasons + composite_reasons))
        all_risks = list(dict.fromkeys(ai_risks))
        final_reasoning = composite_reasoning or ai_reasoning

        output_data: dict[str, Any] = {
            "overall_score": overall_score,
            "icp_match_score": icp_score,
            "buying_signal_score": buying_score,
            "company_fit_score": fit_score,
            "priority": priority,
            "reasoning": final_reasoning,
            "reasons": all_reasons,
            "risks": all_risks,
            "recommended_bdr_action": {
                "urgency": urgency,
                "suggested_sales_angle": sales_angle,
            },
            "icp_config_used": {
                "industries": icp.industries,
                "min_employees": icp.min_employees,
                "max_employees": icp.max_employees,
                "locations": icp.locations,
            },
            "report_id": report_id,
            "providers_used": getattr(self._ai, "name", "unknown"),
        }

        # ── Step 7: Complete ────────────────────────────────────────────
        summary = (
            f"Qualification for {company_name or report_id}: "
            f"score={overall_score}/100 priority={priority}"
        )

        self._tm.append_log(
            task_id, "info", "qualification_completed",
            summary,
            {
                "overall_score": overall_score,
                "priority": priority,
                "urgency": urgency,
            },
        )

        return AgentResult(
            output_data=output_data,
            summary=summary,
            requires_human_approval=False,
        )

    # ── deterministic scoring ──────────────────────────────────────────

    def _compute_icp_match(
        self,
        findings: dict[str, Any],
        icp: IcpRules,
    ) -> tuple[int, list[str]]:
        """Compute ICP match score from deterministic rules (0-100)."""
        reasons: list[str] = []
        score = 0

        # Industry match (40 points)
        company_industry = (findings.get("industry") or "").lower().strip()
        if company_industry and icp.industries:
            matched_industry = any(
                icp_industry.lower() in company_industry
                or company_industry in icp_industry.lower()
                for icp_industry in icp.industries
            )
            if matched_industry:
                score += 40
                reasons.append(f"+ Industry '{findings.get('industry')}' matches ICP")
            else:
                reasons.append(
                    f"- Industry '{findings.get('industry')}' outside ICP target"
                )
        else:
            score += 20  # neutral
            reasons.append("? Industry unknown — partial ICP credit")

        # Company size (30 points)
        emp_count = findings.get("employee_count")
        if emp_count is not None and icp.min_employees is not None:
            if icp.max_employees is not None:
                if icp.min_employees <= emp_count <= icp.max_employees:
                    score += 30
                    reasons.append(
                        f"+ Company size {emp_count} within ICP range"
                        f" ({icp.min_employees}-{icp.max_employees})"
                    )
                elif emp_count < icp.min_employees:
                    ratio = emp_count / icp.min_employees
                    score += round(30 * min(ratio, 1.0))
                    reasons.append(
                        f"- Company size {emp_count} below ICP minimum {icp.min_employees}"
                    )
                else:
                    score += 10  # above max but still interesting
                    reasons.append(
                        f"~ Company size {emp_count} above ICP max {icp.max_employees}"
                    )
            else:
                score += 15  # no max constraint
                reasons.append("? No max employee limit in ICP")
        else:
            score += 15  # neutral
            reasons.append("? Employee count unknown — partial ICP credit")

        # Location (30 points)
        company_location = (findings.get("location") or "").lower().strip()
        if company_location and icp.locations:
            matched_location = any(
                loc.lower() in company_location
                or company_location in loc.lower()
                for loc in icp.locations
            )
            if matched_location:
                score += 30
                reasons.append(
                    f"+ Location '{findings.get('location')}' in ICP target regions"
                )
            else:
                reasons.append(
                    f"- Location '{findings.get('location')}' outside ICP regions"
                )
        else:
            score += 15  # neutral
            reasons.append("? Location unknown — partial ICP credit")

        return min(score, 100), reasons

    # ── AI scoring ─────────────────────────────────────────────────────

    async def _score_signals(
        self,
        findings: dict[str, Any],
        task_id: uuid.UUID,
    ) -> tuple[int, int, list[str], list[str], str]:
        """Use LLM to evaluate buying signals and company fit."""
        fallback = (50, 50, [], [], "AI scoring unavailable — using neutral scores.")

        signals = findings.get("business_signals", [])
        pain_points = findings.get("pain_points", [])
        tech_signals = findings.get("technology_signals", [])
        flytbase_relevance = findings.get("flytbase_relevance", "Unknown")
        description = findings.get("description", "")
        industry = findings.get("industry", "")
        location = findings.get("location", "")

        if not signals and not pain_points and not tech_signals:
            return 40, 50, [], ["No signals or pain points in research data"], \
                "Insufficient data for AI signal scoring."

        prompt = (
            f"Company Industry: {industry}\n"
            f"Location: {location}\n"
            f"Description: {description}\n"
            f"FlytBase Relevance: {flytbase_relevance}\n\n"
            f"Business Signals: {json.dumps(signals)}\n"
            f"Pain Points: {json.dumps(pain_points)}\n"
            f"Technology Signals: {json.dumps(tech_signals)}\n"
        )

        try:
            response = await self._ai.generate(
                AIRequest(
                    messages=[
                        AIMessage(role="system", content=_BUYING_SIGNAL_PROMPT),
                        AIMessage(role="user", content=prompt),
                    ],
                    temperature=0.3,
                )
            )
            parsed = _parse_json_object(response.content)
            if parsed and isinstance(parsed, dict):
                buying = max(0, min(100, parsed.get("buying_signal_score", 50)))
                fit = max(0, min(100, parsed.get("company_fit_score", 50)))
                reasons: list[str] = parsed.get("reasons", []) or []
                risks: list[str] = parsed.get("risks", []) or []
                reasoning = parsed.get("reasoning", "") or ""
                return buying, fit, reasons, risks, reasoning
            return fallback
        except (ProviderError, Exception):
            return fallback

    async def _compute_composite(
        self,
        icp_score: int,
        buying_score: int,
        fit_score: int,
        company_name: str,
        findings: dict[str, Any],
        task_id: uuid.UUID,
    ) -> tuple[int, str, str, str, list[str], str]:
        """Compute overall score and BDR action recommendation."""
        # Deterministic fallback composite
        weighted = round(icp_score * 0.40 + buying_score * 0.35 + fit_score * 0.25)
        fallback_priority = "HOT" if weighted >= 70 else "WARM" if weighted >= 40 else "COLD"
        fallback_urgency = "Immediate" if fallback_priority == "HOT" \
            else "This week" if fallback_priority == "WARM" else "This month"
        fallback = (
            weighted, fallback_priority, fallback_urgency,
            f"Engage {company_name} based on ICP fit and signals.",
            [], "Composite scoring complete (deterministic fallback).",
        )

        prompt = (
            f"Company: {company_name}\n"
            f"Industry: {findings.get('industry', 'Unknown')}\n"
            f"ICP Match Score: {icp_score}/100\n"
            f"Buying Signal Score: {buying_score}/100\n"
            f"Company Fit Score: {fit_score}/100\n"
            f"FlytBase Relevance: {findings.get('flytbase_relevance', 'Unknown')}\n"
            f"Pain Points: {json.dumps(findings.get('pain_points', []))}\n"
            f"Description: {findings.get('description', '')}\n"
        )

        try:
            response = await self._ai.generate(
                AIRequest(
                    messages=[
                        AIMessage(role="system", content=_COMPOSITE_PROMPT),
                        AIMessage(role="user", content=prompt),
                    ],
                    temperature=0.3,
                )
            )
            parsed = _parse_json_object(response.content)
            if parsed and isinstance(parsed, dict):
                overall = max(0, min(100, parsed.get("overall_score", weighted)))
                priority = str(parsed.get("priority", fallback_priority))
                urgency = str(parsed.get("urgency", fallback_urgency))
                angle = str(parsed.get("sales_angle", ""))
                reasons: list[str] = parsed.get("reasons", []) or []
                reasoning = str(parsed.get("reasoning", ""))
                return overall, priority, urgency, angle, reasons, reasoning
            return fallback
        except (ProviderError, Exception):
            return fallback


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
