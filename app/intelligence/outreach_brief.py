"""Deterministic company intelligence for human outreach review.

This module deliberately does not call an LLM or external service.  It turns
already-approved research and qualification inputs into a reviewable brief so
that any agent can reuse the same intelligence without duplicating logic.
"""

from __future__ import annotations

from typing import Any


class CompanyIntelligenceBriefBuilder:
    """Build a structured, demo-safe brief from research and qualification data."""

    _GROWTH_TERMS = ("funding", "series", "hiring", "growth", "launch", "contract", "partner")
    _EXPANSION_TERMS = ("expand", "expansion", "market", "city", "region", "eu", "global")

    def build(
        self,
        *,
        company_name: str,
        research: dict[str, Any],
        qualification: dict[str, Any],
    ) -> dict[str, Any]:
        """Return a stable brief with evidence traceable to existing inputs."""
        signals = self._as_strings(research.get("business_signals"))
        pains = self._as_strings(research.get("pain_points"))
        technologies = self._as_strings(research.get("technology_signals"))
        growth = self._matching(signals, self._GROWTH_TERMS)
        expansion = self._matching(signals, self._EXPANSION_TERMS)
        operational_changes = [
            signal for signal in signals
            if signal not in growth and signal not in expansion
        ]
        problems = pains or [
            ""
            "The available research does not name a specific operational problem yet. "
            "Validate fleet coordination and workflow maturity in discovery."
        ]
        fit = research.get("flytbase_relevance") or (
            ""
            "FlytBase is relevant when an operator needs centralized visibility, "
            "remote operations, and repeatable drone workflows."
        )
        sales_angle = self._sales_angle(qualification, problems)

        situation_bits = growth + expansion + operational_changes
        profile = self._join(situation_bits) or "an operating profile that warrants discovery"
        footprint = self._join(technologies) or "no confirmed stack signals"
        situation = (
            f"{company_name} shows {profile}. "
            f"Its technology footprint includes {footprint}."
        )
        return {
            "source": "simulated_structured_intelligence",
            "company_situation_summary": situation,
            "growth_signals": growth,
            "operational_changes": operational_changes,
            "expansion_indicators": expansion,
            "technology_adoption_signals": technologies,
            "detected_business_problems": problems,
            "operational_risks": self._risks(problems),
            "flytbase_fit": {
                "summary": str(fit),
                "capabilities": [
                    "Centralized fleet visibility and remote operations",
                    "Automated mission planning and repeatable workflows",
                    "API-based integration with operational systems",
                ],
            },
            "recommended_sales_angle": sales_angle,
            "relevant_incidents": self._incidents(research.get("industry", "drone operations")),
        }

    @staticmethod
    def _as_strings(value: Any) -> list[str]:
        return [str(item).strip() for item in value or [] if str(item).strip()]

    @staticmethod
    def _matching(items: list[str], terms: tuple[str, ...]) -> list[str]:
        return [
            item for item in items
            if any(term in item.lower() for term in terms)
        ]

    @staticmethod
    def _join(items: list[str]) -> str:
        if not items:
            return ""
        return ", ".join(items[:3])

    @staticmethod
    def _risks(problems: list[str]) -> list[str]:
        return [
            (
                f"If unresolved, {problem.rstrip('.')} can increase "
                "coordination overhead as operations grow."
            )
            for problem in problems[:3]
        ]

    @staticmethod
    def _sales_angle(
        qualification: dict[str, Any], problems: list[str]
    ) -> str:
        action = qualification.get("recommended_bdr_action") or {}
        existing = action.get("suggested_sales_angle")
        if existing:
            return str(existing)
        problem = problems[0].rstrip(".") if problems else "scaling operational complexity"
        return (
            "Discuss how enterprise drone operators maintain "
            "visibility and control while addressing "
            f"{problem.lower()}."
        )

    @staticmethod
    def _incidents(industry: Any) -> list[dict[str, str]]:
        return [
            {
                "title": "Scaling operations can expose coordination gaps",
                "summary": (
                    f"Demo industry context for {industry}: multi-site drone programs can face "
                    "mission conflicts, fragmented telemetry, "
                    "and delayed operator response."
                ),
                "urgency": "Use this as a discovery prompt, not as a claim about this company.",
            },
            {
                "title": "Regulatory and safety workflows become harder across regions",
                "summary": (
                    "Demo industry context: regional expansion increases the need for "
                    "consistent operating procedures, auditability, and exception "
                    "visibility."
                ),
                "urgency": (
                    "Relevant when the prospect is adding sites, "
                    "customers, or operating regions."
                ),
            },
        ]
