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
        account_intelligence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a stable brief with evidence traceable to existing inputs.

        When ``account_intelligence`` is provided (from the Account Intelligence
        Engine), its richer fields are used directly instead of deriving them
        from the raw research signals.
        """
        if account_intelligence:
            return self._build_from_intelligence(
                company_name=company_name,
                account_intelligence=account_intelligence,
                qualification=qualification,
                research=research,
            )

        return self._build_from_research(
            company_name=company_name,
            research=research,
            qualification=qualification,
        )

    def _build_from_intelligence(
        self,
        *,
        company_name: str,
        account_intelligence: dict[str, Any],
        qualification: dict[str, Any],
        research: dict[str, Any],
    ) -> dict[str, Any]:
        """Build brief using Account Intelligence Engine output."""
        ai = account_intelligence
        business_problems = ai.get("business_problems", [])
        growth_signals = ai.get("growth_signals", [])
        buying_signals = ai.get("buying_signals", [])
        technology_signals = ai.get("technology_signals", [])
        company_situation = ai.get("company_situation", "")
        flytbase_relevance = ai.get("flytbase_relevance", "")
        recommended_angle = ai.get("recommended_sales_angle", "")
        industry_incidents = ai.get("industry_incidents", [])
        operational_risks = ai.get("operational_risks", [])
        citations = ai.get("citations", [])

        problems = business_problems or [
            "Insufficient data — validate fleet coordination and workflow maturity in discovery."  # noqa: E501
        ]
        fit = flytbase_relevance or (
            "FlytBase is relevant when an operator needs centralized visibility, "
            "remote operations, and repeatable drone workflows."
        )
        sales_angle = recommended_angle or self._sales_angle(qualification, problems)

        # Merge buying signals into growth signals for the brief display
        all_growth = list(dict.fromkeys(growth_signals + buying_signals))

        # Use AI-detected risks or fall back to derived risks
        risks = operational_risks or self._risks(problems)

        # Use Account Intelligence incidents or fall back to generic ones
        incidents = industry_incidents or self._incidents(
            research.get("industry", "drone operations")
        )

        return {
            "source": "account_intelligence_engine",
            "company_situation_summary": company_situation
            or self._build_situation(company_name, all_growth, technology_signals),
            "growth_signals": all_growth,
            "expansion_indicators": [],
            "technology_adoption_signals": technology_signals,
            "detected_business_problems": problems,
            "operational_risks": risks,
            "flytbase_fit": {
                "summary": str(fit),
                "capabilities": [
                    "Centralized fleet visibility and remote operations",
                    "Automated mission planning and repeatable workflows",
                    "API-based integration with operational systems",
                ],
            },
            "recommended_sales_angle": sales_angle,
            "relevant_incidents": incidents,
            "citations": citations,
        }

    def _build_from_research(
        self,
        *,
        company_name: str,
        research: dict[str, Any],
        qualification: dict[str, Any],
    ) -> dict[str, Any]:
        """Derive brief from research data, preferring Account Intelligence fields if present."""
        # Prefer Account Intelligence field names over legacy names
        signals = self._as_strings(
            research.get("growth_signals") or research.get("business_signals")
        )
        pains = self._as_strings(
            research.get("business_problems") or research.get("pain_points")
        )
        technologies = self._as_strings(
            research.get("technology_signals")
        )
        growth = self._matching(signals, self._GROWTH_TERMS)
        expansion = self._matching(signals, self._EXPANSION_TERMS)
        operational_changes = [
            signal for signal in signals
            if signal not in growth and signal not in expansion
        ]
        problems = pains or [
            "The available research does not name a specific operational problem yet. "
            "Validate fleet coordination and workflow maturity in discovery."
        ]
        fit = research.get("flytbase_relevance") or (
            "FlytBase is relevant when an operator needs centralized visibility, "
            "remote operations, and repeatable drone workflows."
        )
        sales_angle = self._sales_angle(qualification, problems)

        situation = self._build_situation(
            company_name,
            growth + expansion + operational_changes,
            technologies,
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
            "relevant_incidents": self._incidents(
                research.get("industry", "drone operations")
            ),
        }

    @staticmethod
    def _build_situation(
        company_name: str,
        signals: list[str],
        technologies: list[str],
    ) -> str:
        """Build a company situation summary from signals and technologies."""
        profile = ", ".join(signals[:3]) if signals else "an operating profile that warrants discovery"  # noqa: E501
        footprint = ", ".join(technologies[:3]) if technologies else "no confirmed stack signals"
        return f"{company_name} shows {profile}. Its technology footprint includes {footprint}."

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
