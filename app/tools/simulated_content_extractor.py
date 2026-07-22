from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.core.contracts import ToolResult
from app.tools.base import BaseTool

_MOCK_PAGES: dict[str, dict[str, str]] = {
    "flytbase.com": {
        "title": "FlytBase — Drone Fleet Management Platform",
        "text": (
            "FlytBase is the industry-leading drone fleet management platform. "
            "We enable enterprises to operate drones remotely, plan automated BVLOS missions, "
            "and manage fleets from a single dashboard. Our platform integrates with DJI, "
            "Autel, and other major drone manufacturers. Key capabilities include:\n\n"
            "- Remote drone operations and real-time video streaming\n"
            "- Automated flight planning and mission scheduling\n"
            "- Fleet health monitoring and maintenance alerts\n"
            "- Compliance management for FAA and EASA regulations\n"
            "- API-first architecture for custom integrations\n\n"
            "Founded in 2018, FlytBase serves over 500 enterprise customers across "
            "construction, agriculture, energy, and public safety sectors."
        ),
    },
}

_DEFAULT_PAGE = {
    "title": "About Us",
    "text": (
        "The company is a leading technology firm specializing in enterprise solutions. "
        "Founded in 2015, they have grown to serve customers across multiple industries. "
        "Their platform leverages AI and automation to deliver measurable business outcomes.\n\n"
        "Recent developments include expansion into new geographic markets, "
        "strategic partnerships with technology leaders, and significant investment in "
        "research and development. The company has been recognized for innovation "
        "in enterprise software and customer satisfaction."
    ),
}


class SimulatedContentExtractorTool(BaseTool):
    """Simulated webpage content extractor returning realistic mock content.

    Used for development, testing, and demo environments.
    Replace with an HTTP-based HTML-to-text extractor in production.
    """

    name = "extract_web_content"
    description = "Extract readable text content from a given URL."

    async def execute(self, payload: dict[str, Any]) -> ToolResult:
        url: str = payload.get("url", "").strip()
        url_lower = url.lower()

        # Find best matching mock
        page = _DEFAULT_PAGE
        for domain, content in _MOCK_PAGES.items():
            if domain in url_lower:
                page = content
                break

        return ToolResult(
            content={
                "url": url,
                "title": page["title"],
                "text": page["text"],
                "extracted_at": datetime.now(UTC).isoformat(),
            },
            sources=[url] if url else [],
        )
