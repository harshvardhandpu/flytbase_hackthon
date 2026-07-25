"""Web content extraction tool — fetches a URL and returns clean readable text.

Uses ``httpx`` for async HTTP requests and basic HTML-to-text extraction.
Falls back to simulated content for dev/test/demo when real fetching fails.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import httpx

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
    "riotinto.com": {
        "title": "Rio Tinto — Global Mining Leader",
        "text": (
            "Rio Tinto is one of the world's largest mining companies with operations "
            "across 35 countries. Our core portfolio includes iron ore, copper, aluminum, "
            "and critical minerals for the energy transition. We operate some of the "
            "largest open-pit and underground mines globally.\n\n"
            "Autonomous Operations: Rio Tinto operates the world's largest fleet of "
            "autonomous haul trucks across our Pilbara iron ore operations. Our "
            "Operations Centre in Perth remotely manages 15 mine sites, controlling "
            "autonomous trucks, trains, and drills.\n\n"
            "Digital Transformation: We are investing in AI-powered predictive maintenance, "
            "drone-based site inspection, real-time operational analytics, and "
            "remote operations technology. Our 'Mine of the Future' program aims to "
            "achieve fully autonomous mining operations.\n\n"
            "Drone Fleet: Rio Tinto uses drone fleets for stockpile measurement, "
            "equipment inspection, blast monitoring, safety surveillance, and site "
            "surveying. We are exploring expanded drone automation for remote "
            "operations and inspection workflows."
        ),
    },
    "mining-technology.com": {
        "title": "Mining Technology — Autonomous Mining News",
        "text": (
            "The mining industry is undergoing a profound transformation driven by "
            "autonomous technologies. Major mining companies are investing heavily in "
            "automation to improve safety, reduce costs, and address labor shortages.\n\n"
            "Autonomous Haulage: Rio Tinto, BHP, and Vale operate large fleets of "
            "autonomous haul trucks that have demonstrated 20-30 percent productivity "
            "improvements compared to manned operations. These trucks are controlled "
            "remotely from centralized operations centers.\n\n"
            "Drone Inspection: Drones are increasingly deployed for mine site inspection, "
            "replacing manual inspection teams. Applications include stockpile "
            "measurement, equipment condition monitoring, safety surveillance, and "
            "blast monitoring. Automation of drone workflows is the next frontier.\n\n"
            "Remote Operations: Centralized remote operations centers allow mining "
            "companies to manage multiple sites from a single location, reducing "
            "on-site headcount while improving operational visibility and control."
        ),
    },
    "dronelife.com": {
        "title": "DroneLife — Drone News in Mining",
        "text": (
            "Drone adoption in mining is accelerating as companies seek to improve "
            "safety and efficiency. Rio Tinto has deployed drone fleets across multiple "
            "mine sites for automated stockpile measurement, equipment inspection, "
            "and safety monitoring. The program has reduced manual inspection time "
            "by 70 percent while improving data accuracy and worker safety.\n\n"
            "Key drone applications in mining include: stockpile volume measurement, "
            "conveyor belt inspection, tailings dam monitoring, blast zone assessment, "
            "and site security surveillance. Fleet management platforms are needed "
            "to coordinate multiple drones across distributed mine sites."
        ),
    },
    "mining-recruitment.com": {
        "title": "Mining Recruitment — Automation Jobs",
        "text": (
            "Rio Tinto is actively recruiting automation engineers, robotics specialists, "
            "fleet management system engineers, and remote operations specialists. "
            "The company is expanding its autonomous mining team to support the "
            "deployment of autonomous haulage systems, drone inspection programs, "
            "and remote operations centers across its global mining operations."
        ),
    },
    "mining.com": {
        "title": "Mining.com — Automation Talent Shortage",
        "text": (
            "The mining industry is facing a critical shortage of automation and "
            "robotics talent as companies like Rio Tinto, BHP, and Vale accelerate "
            "their autonomous mining programs. Demand for engineers with experience "
            "in fleet management, remote operations, and drone automation far "
            "outpaces supply, creating urgency for technology solutions."
        ),
    },
}

_DEFAULT_PAGE: dict[str, str] = {
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


class WebContentExtractorTool(BaseTool):
    """Fetch a URL and extract clean readable text content.

    Uses simple HTTP GET + regex-based HTML stripping for extraction.
    Falls back to simulated content when the URL is unreachable or when
    running in dev/test/demo mode.
    """

    name = "extract_web_content"
    description = "Extract readable text content from a given URL."

    def __init__(self, force_simulated: bool = False) -> None:
        self.force_simulated = force_simulated

    async def execute(self, payload: dict[str, Any]) -> ToolResult:
        url: str = payload.get("url", "").strip()
        if not url:
            return ToolResult(
                content={"url": "", "title": "", "text": "", "error": "No URL provided"},
                sources=[],
            )

        if self.force_simulated:
            return self._simulated_extract(url)

        # Try real HTTP extraction first
        try:
            return await self._http_extract(url)
        except Exception:
            # Fall back to simulated
            return self._simulated_extract(url)

    # ── Real HTTP extraction ────────────────────────────────────────────

    @staticmethod
    async def _http_extract(url: str) -> ToolResult:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "ScoutOS/1.0"})
            resp.raise_for_status()
            html = resp.text

        title = _extract_title(html)
        text = _html_to_text(html)
        # Truncate to avoid huge responses
        max_chars = 10_000
        if len(text) > max_chars:
            text = text[:max_chars] + "\n\n[... truncated ...]"

        return ToolResult(
            content={
                "url": url,
                "title": title or "Untitled",
                "text": text,
                "extracted_at": datetime.now(UTC).isoformat(),
            },
            sources=[url],
        )

    # ── Simulated fallback ──────────────────────────────────────────────

    @staticmethod
    def _simulated_extract(url: str) -> ToolResult:
        url_lower = url.lower()
        page = dict(_DEFAULT_PAGE)

        for domain, content in _MOCK_PAGES.items():
            if domain in url_lower:
                page = dict(content)
                break

        return ToolResult(
            content={
                "url": url,
                "title": page["title"],
                "text": page["text"],
                "extracted_at": datetime.now(UTC).isoformat(),
                "simulated": True,
            },
            sources=[url] if url else [],
        )


# ── HTML extraction helpers ─────────────────────────────────────────────


def _extract_title(html: str) -> str | None:
    """Extract the <title> tag content from HTML."""
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def _html_to_text(html: str) -> str:
    """Convert HTML to plain text with basic structural preservation.

    Strips scripts, styles, and tags while preserving paragraph breaks
    and newlines for readability.
    """
    # Remove scripts and styles
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.IGNORECASE | re.DOTALL)
    # Replace <br> and block-level tags with newlines
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(
        r"</?(?:p|div|h[1-6]|li|tr|th|td|blockquote|pre|section|article)[^>]*>",
        "\n",
        html,
        flags=re.IGNORECASE,
    )
    # Remove remaining HTML tags
    text = re.sub(r"<[^>]+>", "", html)
    # Decode common entities
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&nbsp;", " ")
    # Collapse multiple newlines to at most 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Strip leading/trailing whitespace per line
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)
    return text.strip()
