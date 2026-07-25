"""BDR qualification agent — evidence-backed lead scoring.

Scoring model (total = 100):
  ICP Match:       30 pts  (deterministic: industry, size, location)
  Pain Alignment:  30 pts  (AI: does research show FlytBase-solvable problems)
  Buying Intent:   25 pts  (AI: recent signals of buying readiness)
  Company Fit:     15 pts  (AI: overall strategic fit)

Every qualification reason MUST reference evidence from the research report.
If research has no evidence, scores are reduced and explanation is provided.
"""

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


_EVIDENCE_SCORING_PROMPT = """\
You are a senior BDR qualification analyst. Evaluate the company's research
intelligence for FlytBase relevance using ONLY the evidence provided.

FlytBase is a drone fleet management platform that enables enterprises
to operate drones remotely for automated missions — fleet management,
remote monitoring, inspection automation, and operational visibility.

Score the following dimensions 0-100 based on EVIDENCE in the data:

PAIN ALIGNMENT (0-100):
Does the research show problems FlytBase solves?
- Drone fleet operations or aerial operations
- Remote monitoring of equipment/sites
- Automation needs in inspection/surveillance
- Fleet management complexity at scale
- Safety inspection problems
- Operational visibility gaps

BUYING INTENT (0-100):
Evidence of buying readiness from:
- Recent initiatives or investments in automation
- Hiring for drone/robotics/automation roles
- Technology partnerships or platform evaluations
- Expansion into drone-adjacent operations
- Budget or resource allocation signals
- Digital transformation projects

COMPANY FIT (0-100):
Overall strategic fit:
- Industry relevance for drone/automation solutions
- Operational scale that benefits from automation
- Technology maturity and innovation culture

CRITICAL RULES:
1. Every scored item MUST reference specific evidence.
2. If no evidence exists for a dimension, score LOW and explain why.
3. Use the following fields from the research for evidence:
   - operational_pain_points (with evidence text and source URLs)
   - buying_signals (with source URLs)
   - business_signals (categorized with summaries)
   - evidence items (claims with source URLs)
   - company_situation

Return ONLY a JSON object with these keys:
{
  "pain_alignment_score": 0-100,
  "buying_intent_score": 0-100,
  "company_fit_score": 0-100,
  "evidence_based_reasons": [
    "Because [specific evidence from research], the pain alignment score is X/100."
  ],
  "reasons": ["Short reason 1", "Short reason 2"],
  "risks": ["Risk 1", "Risk 2"],
  "reasoning": "2-3 sentence explanation of why these scores were assigned."
}"""


_COMPOSITE_PROMPT = """\
You are a lead scoring analyst. Given the four component scores and the
company's research intelligence, determine the overall lead qualification
and recommended BDR action.

Scoring rules:
- ICP Match:       30 pts max (deterministic — industry, size, location fit)
- Pain Alignment:  30 pts max (AI — research shows FlytBase-solvable problems)
- Buying Intent:   25 pts max (AI — evidence of buying readiness)
- Company Fit:     15 pts max (AI — overall strategic fit)
- Overall Score:   Sum of all four component scores (0-100)

Priority rules:
- HOT:   overall >= 70
- WARM:  overall >= 40
- COLD:  overall < 40

Urgency rules:
- HOT:   "Immediate"
- WARM:  "This week"
- COLD:  "This month"

Return ONLY a JSON object with these keys:
{
  "overall_score": 0-100 (sum of component scores),
  "priority": "HOT" | "WARM" | "COLD",
  "urgency": "Immediate" | "This week" | "This month",
  "sales_angle": "A 1-2 sentence sales angle based on specific pain points",
  "qualification_summary": "One sentence summarising the qualification decision",
  "reasons": ["Reason 1", "Reason 2"],
  "reasoning": "Explain why this overall score was assigned."
}"""


# ── Qualification Agent ────────────────────────────────────────────────


class QualificationAgent(BaseAgent):
    """BDR qualification agent — evidence-backed lead scoring.

    Scoring model:
      ICP Match:       30 pts — deterministic (industry, size, location)
      Pain Alignment:  30 pts — AI (problems FlytBase solves)
      Buying Intent:   25 pts — AI (buying readiness signals)
      Company Fit:     15 pts — AI (strategic fit)

    Every reason references evidence. Missing evidence reduces scores.
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

        # ── Step 3: Deterministic ICP match scoring (max 30) ────────────
        self._tm.append_log(
            task_id, "debug", "deterministic_scoring_started",
            "Computing deterministic ICP match score",
        )

        icp_score, icp_reasons = self._compute_icp_match(findings, icp)

        self._tm.append_log(
            task_id, "debug", "deterministic_scoring_completed",
            f"ICP match score={icp_score}/30",
            {"icp_match_score": icp_score, "reasons": icp_reasons},
        )

        # ── Step 4: AI evidence-based scoring ──────────────────────────
        self._tm.append_log(
            task_id, "info", "ai_scoring_started",
            "Evaluating pain alignment, buying intent, and company fit via LLM",
        )

        pain_score, intent_score, fit_score, evidence_reasons, \
            ai_reasons, ai_risks, ai_reasoning = (
                await self._score_with_evidence(findings, task_id)
            )

        self._tm.append_log(
            task_id, "info", "ai_scoring_completed",
            f"Pain Alignment={pain_score}/100 Intent={intent_score}/100 Fit={fit_score}/100",
            {
                "pain_alignment_score": pain_score,
                "buying_intent_score": intent_score,
                "company_fit_score": fit_score,
            },
        )

        # ── Step 5: Composite score ─────────────────────────────────────
        self._tm.append_log(
            task_id, "info", "composite_scoring_started",
            "Computing overall score from weighted component scores",
        )

        overall_score = self._compute_weighted_overall(
            icp_score=icp_score,
            pain_score=pain_score,
            intent_score=intent_score,
            fit_score=fit_score,
        )

        # Apply priority thresholds
        priority, urgency = self._compute_priority(overall_score)

        self._tm.append_log(
            task_id, "info", "priority_assigned",
            f"Priority={priority} overall_score={overall_score}",
            {
                "overall_score": overall_score,
                "priority": priority,
                "urgency": urgency,
            },
        )

        # Generate composite reasons from evidence
        all_reasons = list(dict.fromkeys(
            icp_reasons + evidence_reasons + ai_reasons
        ))
        all_risks = list(dict.fromkeys(ai_risks))

        # Build qualification summary from evidence
        qualification_summary = self._build_summary(
            company_name=company_name,
            overall_score=overall_score,
            priority=priority,
            pain_score=pain_score,
            intent_score=intent_score,
            findings=findings,
        )

        # ── Step 6: AI composites (sales angle + reasoning) ────────────
        sales_angle, composite_reasons, composite_reasoning = \
            await self._compute_composite(
                icp_score=icp_score,
                pain_score=pain_score,
                intent_score=intent_score,
                fit_score=fit_score,
                overall_score=overall_score,
                priority=priority,
                urgency=urgency,
                company_name=company_name,
                findings=findings,
                task_id=task_id,
            )

        if composite_reasons:
            all_reasons = list(dict.fromkeys(all_reasons + composite_reasons))

        final_reasoning = composite_reasoning or ai_reasoning or (
            f"Qualification completed for {company_name}: "
            f"score={overall_score}/100 ({priority})."
        )

        # ── Evidence confidence ────────────────────────────────────────
        # Confidence in the qualification based on research evidence quality
        research_confidence = findings.get("confidence_score", 0)
        evidence_count = len(evidence_reasons)
        qualification_confidence = research_confidence
        if evidence_count == 0 and research_confidence < 50:
            qualification_confidence = max(0, research_confidence - 20)

        # ── Step 7: Build output ──────────────────────────────────────
        output_data: dict[str, Any] = {
            "overall_score": overall_score,
            "icp_match_score": icp_score,
            "pain_alignment_score": pain_score,
            "buying_signal_score": intent_score,
            "company_fit_score": fit_score,
            "priority": priority,
            "reasoning": final_reasoning,
            "reasons": all_reasons,
            "risks": all_risks,
            "evidence_based_reasons": evidence_reasons,
            "qualification_summary": qualification_summary,
            "confidence_score": qualification_confidence,
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

        # ── Step 8: Complete ───────────────────────────────────────────
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
                "pain_alignment_score": pain_score,
                "buying_intent_score": intent_score,
            },
        )

        return AgentResult(
            output_data=output_data,
            summary=summary,
            requires_human_approval=False,
        )

    # ── Deterministic ICP scoring (max 30 pts) ──────────────────────────

    def _compute_icp_match(
        self,
        findings: dict[str, Any],
        icp: IcpRules,
    ) -> tuple[int, list[str]]:
        """Compute ICP match score from deterministic rules (max 30)."""
        reasons: list[str] = []
        score = 0

        # Industry match (12 points)
        company_industry = (findings.get("industry") or "").lower().strip()
        if company_industry and icp.industries:
            matched_industry = any(
                icp_industry.lower() in company_industry
                or company_industry in icp_industry.lower()
                for icp_industry in icp.industries
            )
            if matched_industry:
                score += 12
                reasons.append(f"+ Industry '{findings.get('industry')}' matches ICP [+12]")
            else:
                reasons.append(
                    f"- Industry '{findings.get('industry')}' outside ICP target [0]"
                )
        else:
            score += 6  # neutral
            reasons.append("? Industry unknown — partial credit [+6]")

        # Company size (9 points)
        emp_count = findings.get("employee_count")
        if emp_count is not None and icp.min_employees is not None:
            if icp.max_employees is not None:
                if icp.min_employees <= emp_count <= icp.max_employees:
                    score += 9
                    reasons.append(
                        f"+ Company size {emp_count} within ICP range"
                        f" ({icp.min_employees}-{icp.max_employees}) [+9]"
                    )
                elif emp_count < icp.min_employees:
                    ratio = emp_count / icp.min_employees
                    score += round(9 * min(ratio, 1.0))
                    reasons.append(
                        f"- Company size {emp_count} below ICP minimum {icp.min_employees}"
                        f" [{round(9 * min(ratio, 1.0))}]"
                    )
                else:
                    score += 3  # above max but still interesting
                    reasons.append(
                        f"~ Company size {emp_count} above ICP max {icp.max_employees} [+3]"
                    )
            else:
                score += 4  # no max constraint
                reasons.append("? No max employee limit in ICP [+4]")
        else:
            score += 4  # neutral
            reasons.append("? Employee count unknown — partial credit [+4]")

        # Location (9 points)
        company_location = (findings.get("location") or "").lower().strip()
        if company_location and icp.locations:
            matched_location = any(
                loc.lower() in company_location
                or company_location in loc.lower()
                for loc in icp.locations
            )
            if matched_location:
                score += 9
                reasons.append(
                    f"+ Location '{findings.get('location')}' in ICP target regions [+9]"
                )
            else:
                reasons.append(
                    f"- Location '{findings.get('location')}' outside ICP regions [0]"
                )
        else:
            score += 4  # neutral
            reasons.append("? Location unknown — partial credit [+4]")

        return min(score, 30), reasons

    # ── Evidence-backed AI scoring ─────────────────────────────────────

    async def _score_with_evidence(
        self,
        findings: dict[str, Any],
        task_id: uuid.UUID,
    ) -> tuple[int, int, int, list[str], list[str], list[str], str]:
        """Use LLM to evaluate pain alignment, buying intent, and company
        fit using ONLY evidence from the research report.

        Returns:
            (pain_alignment, buying_intent, company_fit,
             evidence_based_reasons, reasons, risks, reasoning)
        """
        fallback = (0, 0, 0, [], [], [
            "No research evidence available — scores defaulted to 0.",
        ], "Insufficient data for AI scoring.")

        # Check if we have any evidence to work with
        operational_pain_points = findings.get("operational_pain_points", [])
        buying_signals = findings.get("buying_signals", [])
        business_signals = findings.get("business_signals", [])
        evidence = findings.get("evidence", [])
        company_situation = findings.get("company_situation", "")
        flytbase_fit = findings.get("flytbase_fit", "")
        flytbase_relevance = findings.get("flytbase_relevance", "")
        description = findings.get("description", "")
        industry = findings.get("industry", "")

        has_evidence = bool(
            operational_pain_points or buying_signals or business_signals
            or evidence or company_situation
        )

        if not has_evidence:
            return 0, 0, 0, [], [
                "Research report contains no evidence for this company.",
            ], [
                "No operational pain points, buying signals, or evidence found.",
                "Scores defaulted to 0 — intelligence gathering needed.",
            ], (
                "No evidence was found in the research report for this company. "
                "Scores defaulted to 0. Run research enrichment first."
            )

        prompt = (
            f"Company Industry: {industry}\n"
            f"Company Description: {description}\n"
            f"Company Situation: {company_situation}\n"
            f"FlytBase Relevance: {flytbase_relevance}\n"
            f"FlytBase Fit: {flytbase_fit}\n\n"
            f"=== Operational Pain Points (evidence-backed) ===\n"
            f"{json.dumps(operational_pain_points, indent=2)}\n\n"
            f"=== Buying Signals ===\n"
            f"{json.dumps(buying_signals, indent=2)}\n\n"
            f"=== Business Signals (categorized) ===\n"
            f"{json.dumps(business_signals, indent=2)}\n\n"
            f"=== Evidence Items ===\n"
            f"{json.dumps(evidence, indent=2)}\n"
        )

        try:
            response = await self._ai.generate(
                AIRequest(
                    messages=[
                        AIMessage(role="system", content=_EVIDENCE_SCORING_PROMPT),
                        AIMessage(role="user", content=prompt),
                    ],
                    temperature=0.3,
                )
            )
            parsed = _parse_json_object(response.content)
            if parsed and isinstance(parsed, dict):
                pain = max(0, min(100, parsed.get("pain_alignment_score", 0)))
                intent = max(0, min(100, parsed.get("buying_intent_score", 0)))
                fit = max(0, min(100, parsed.get("company_fit_score", 0)))
                evidence_reasons: list[str] = parsed.get("evidence_based_reasons", []) or []
                reasons: list[str] = parsed.get("reasons", []) or []
                risks: list[str] = parsed.get("risks", []) or []
                reasoning = parsed.get("reasoning", "") or ""
                return pain, intent, fit, evidence_reasons, reasons, risks, reasoning
            return fallback
        except (ProviderError, Exception):
            return fallback

    # ── Composite calculation helpers ───────────────────────────────────

    @staticmethod
    def _compute_weighted_overall(
        icp_score: int,
        pain_score: int,
        intent_score: int,
        fit_score: int,
    ) -> int:
        """Compute overall 0-100 score from weighted components.

        Weights:
          ICP Match:     30% of raw score (icp_score is already 0-30)
          Pain Alignment: 30% of raw score (pain is 0-100, apply 0.30)
          Buying Intent:  25% of raw score (intent is 0-100, apply 0.25)
          Company Fit:    15% of raw score (fit is 0-100, apply 0.15)
        """
        weighted = (
            icp_score                          # already 0-30
            + round(pain_score * 0.30)          # 0-100 → 0-30
            + round(intent_score * 0.25)        # 0-100 → 0-25
            + round(fit_score * 0.15)           # 0-100 → 0-15
        )
        return min(weighted, 100)

    @staticmethod
    def _compute_priority(score: int) -> tuple[str, str]:
        """Assign priority and urgency based on overall score."""
        if score >= 70:
            return "HOT", "Immediate"
        elif score >= 40:
            return "WARM", "This week"
        else:
            return "COLD", "This month"

    @staticmethod
    def _build_summary(
        company_name: str,
        overall_score: int,
        priority: str,
        pain_score: int,
        intent_score: int,
        findings: dict[str, Any],
    ) -> str:
        """Build a one-sentence qualification summary."""
        industry = findings.get("industry", "")
        if industry:
            industry_info = f"in {industry}"
        else:
            industry_info = ""

        if pain_score >= 70 and intent_score >= 70:
            signal = "strong pain alignment and buying intent"
        elif pain_score >= 50:
            signal = "moderate pain alignment but limited buying signals"
        elif intent_score >= 50:
            signal = "some buying interest but weak problem alignment"
        else:
            signal = "limited intelligence — further research needed"

        return (
            f"{company_name} {industry_info} qualifies as {priority} "
            f"({overall_score}/100) with {signal}."
        )

    async def _compute_composite(
        self,
        icp_score: int,
        pain_score: int,
        intent_score: int,
        fit_score: int,
        overall_score: int,
        priority: str,
        urgency: str,
        company_name: str,
        findings: dict[str, Any],
        task_id: uuid.UUID,
    ) -> tuple[str, list[str], str]:
        """Use LLM to refine sales angle and generate composite reasoning."""
        fallback = (
            f"Engage {company_name} based on {', '.join([
                s for s in [
                    f"industry fit ({findings.get('industry', '?')})",
                    f"pain alignment ({pain_score}/30 pts)",
                    f"buying intent ({intent_score}/25 pts)",
                ] if s
            ])}.",
            [],
            f"Qualification completed: score={overall_score}/100 ({priority}).",
        )

        operational_pain_points = findings.get("operational_pain_points", [])
        buying_signals = findings.get("buying_signals", [])
        company_situation = findings.get("company_situation", "")
        flytbase_fit = findings.get("flytbase_fit", "")

        prompt = (
            f"Company: {company_name}\n"
            f"Industry: {findings.get('industry', 'Unknown')}\n"
            f"Company Situation: {company_situation}\n"
            f"FlytBase Fit: {flytbase_fit}\n\n"
            f"Scores:\n"
            f"  ICP Match:      {icp_score}/30\n"
            f"  Pain Alignment: {pain_score}/30\n"
            f"  Buying Intent:  {intent_score}/25\n"
            f"  Company Fit:    {fit_score}/15\n"
            f"  Overall:        {overall_score}/100 ({priority})\n"
            f"  Urgency:        {urgency}\n\n"
            f"Operational Pain Points: {json.dumps(operational_pain_points, indent=2)}\n\n"
            f"Buying Signals: {json.dumps(buying_signals, indent=2)}\n"
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
                angle = str(parsed.get("sales_angle", "")) or fallback[0]
                reasons: list[str] = parsed.get("reasons", []) or []
                reasoning = str(parsed.get("reasoning", "")) or fallback[2]
                return angle, reasons, reasoning
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
