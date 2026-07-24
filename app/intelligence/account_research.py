"""Account Intelligence layer — transforms raw research data into structured,
BDR-ready company intelligence using the provider-neutral AIProvider interface.

This layer should not be called directly by API routes. It is designed for
use by ResearchAgent and can be reused by InboundAgent and PipelineAgent.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.contracts import AIMessage, AIProvider, AIRequest, ProviderError

_ANALYSIS_SYSTEM_PROMPT = """\
You are a senior BDR intelligence analyst. Given raw research data for a company,
produce a structured analysis that helps a BDR understand why this company
is worth pursuing and how to approach them.

Focus on:
- The company's current business situation
- Concrete operational problems they likely face
- Risks they face if problems remain unresolved
- Growth signals (hiring, funding, expansion, partnerships)
- Buying signals (tech stack changes, vendor searches, leadership changes)
- Technology adoption signals
- Industry incidents or trends that create urgency
- How FlytBase specifically addresses their needs

Return ONLY a JSON object with these EXACT keys:
{
  "company_situation": "2-3 sentence summary of current business situation",
  "business_problems": ["Specific problem 1", "Specific problem 2"],
  "operational_risks": ["Risk of not solving problem 1", "Risk of not solving problem 2"],
  "growth_signals": ["Hiring spree in X", "Opened new office in Y", "Raised funding"],
  "buying_signals": ["Evaluating vendor solutions", "Hiring integration engineers"],
  "technology_signals": ["Stack signal 1", "Stack signal 2"],
  "flytbase_relevance": "High/Medium/Low — explanation of why FlytBase fits",
  "industry_incidents": [
    {
      "title": "Incident title",
      "summary": "What happened and why it matters",
      "implication": "Why this creates urgency for the prospect"
    }
  ],
  "recommended_sales_angle": "Specific angle for the BDR to lead with",
  "citations": [
    {"source": "Source description", "url": "URL", "key_finding": "Key finding from this source"}
  ]
}

Base your analysis ONLY on the provided research data. Do not fabricate facts.
Where data is unavailable, note it as \"Insufficient data\" rather than inventing.
"""


class AccountResearchIntelligence:
    """Transforms raw research findings into structured, BDR-focused intelligence.

    Uses the AIProvider for LLM-based analysis while keeping all
    provider-specific concerns behind the neutral interface.
    """

    def __init__(self, ai_provider: AIProvider) -> None:
        self._ai = ai_provider

    async def analyze(
        self,
        *,
        company_name: str,
        search_results: list[dict[str, Any]],
        extracted_content: list[str],
        existing_findings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate structured account intelligence from raw research data.

        Args:
            company_name: Target company name.
            search_results: Raw search result items (title, url, snippet).
            extracted_content: Full-text extracts from top sources.
            existing_findings: Optional previous research findings to enrich.

        Returns:
            Structured intelligence dict with all analysis fields.
        """
        fallback = self._build_fallback(
            company_name=company_name,
            search_results=search_results,
            existing_findings=existing_findings,
        )

        try:
            user_prompt = self._build_prompt(
                company_name=company_name,
                search_results=search_results,
                extracted_content=extracted_content,
                existing_findings=existing_findings,
            )

            response = await self._ai.generate(
                AIRequest(
                    messages=[
                        AIMessage(role="system", content=_ANALYSIS_SYSTEM_PROMPT),
                        AIMessage(role="user", content=user_prompt),
                    ],
                    temperature=0.2,
                )
            )

            parsed = self._parse_response(response.content)
            if parsed is not None:
                return parsed
            return fallback

        except (ProviderError, Exception):
            return fallback

    # ── Prompt builder ──────────────────────────────────────────────────

    @staticmethod
    def _build_prompt(
        *,
        company_name: str,
        search_results: list[dict[str, Any]],
        extracted_content: list[str],
        existing_findings: dict[str, Any] | None,
    ) -> str:
        sections: list[str] = [f"Company: {company_name}\n"]

        if search_results:
            sections.append(
                "=== Search Results ===\n"
                + json.dumps(search_results[:15], indent=2)
            )

        if extracted_content:
            sections.append(
                "=== Extracted Content ===\n"
                + "\n\n".join(extracted_content[:5])
            )

        if existing_findings:
            sections.append(
                "=== Previous Research ===\n"
                + json.dumps(existing_findings, indent=2)
            )

        sections.append(
            "\nProduce a structured BDR intelligence analysis. "
            "Return ONLY valid JSON matching the specified schema."
        )

        return "\n\n".join(sections)

    # ── Response parsing ────────────────────────────────────────────────

    @staticmethod
    def _parse_response(content: str) -> dict[str, Any] | None:
        """Best-effort parse of JSON object from LLM output."""
        cleaned = content.strip()
        # Strip code fences
        if cleaned.startswith("```"):
            cleaned = "\n".join(
                line for line in cleaned.split("\n")
                if not line.strip().startswith("```")
            )
        cleaned = cleaned.strip()

        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        # Fallback to finding JSON object boundaries
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end > start:
            try:
                parsed = json.loads(cleaned[start : end + 1])
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

        return None

    # ── Fallback builder ────────────────────────────────────────────────

    @staticmethod
    def _build_fallback(
        *,
        company_name: str,
        search_results: list[dict[str, Any]],
        existing_findings: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Deterministic fallback when LLM analysis fails."""
        ef = existing_findings or {}
        return {
            "company_situation": ef.get("description", "")
            or f"Research data collected for {company_name}.",
            "business_problems": ef.get("pain_points", [])
            or ["Insufficient data — validate during discovery."],
            "operational_risks": [
                "Coordination overhead may increase as operations scale without a unified platform."  # noqa: E501
            ],
            "growth_signals": ef.get("business_signals", []),
            "buying_signals": [],
            "technology_signals": ef.get("technology_signals", []),
            "flytbase_relevance": ef.get("flytbase_relevance", "")
            or "Medium — determine during qualification.",
            "industry_incidents": [
                {
                    "title": "Scaling without centralised coordination creates risk",
                    "summary": "Companies expanding drone operations across multiple sites "
                    "often face fragmented telemetry, mission conflicts, "
                    "and delayed incident response.",
                    "implication": "FlytBase provides the unified command layer "
                    "to prevent these issues.",
                }
            ],
            "recommended_sales_angle": ef.get("recommended_next_action", "")
            or "Lead with operational visibility and control challenges.",
            "citations": [
                {"source": s.get("url", ""), "url": s.get("url", ""), "key_finding": s.get("snippet", "")[:200]}  # noqa: E501
                for s in search_results[:3]
                if s.get("url")
            ],
        }
