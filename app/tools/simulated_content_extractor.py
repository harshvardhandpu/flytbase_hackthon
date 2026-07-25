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
    "riotinto.com": {
        "title": "Rio Tinto — Global Mining Leader",
        "text": (
            "Rio Tinto is one of the world's largest mining companies with operations "
            "across 35 countries. Rio Tinto operates the world's largest fleet of "
            "autonomous haul trucks across our Pilbara iron ore operations. "
            "Our Operations Centre in Perth remotely manages 15 mine sites.\n\n"
            "Digital Transformation: We are investing in AI-powered predictive maintenance, "
            "drone-based site inspection, real-time operational analytics, and "
            "remote operations technology. Our 'Mine of the Future' program aims to "
            "achieve fully autonomous mining operations.\n\n"
            "Drone Fleet: Rio Tinto uses drone fleets for stockpile measurement, "
            "equipment inspection, blast monitoring, safety surveillance, and site "
            "surveying. We are exploring expanded drone automation."
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
            "replacing manual inspection teams. Automation of drone workflows is the "
            "next frontier for mining operations."
        ),
    },
    "dronelife.com": {
        "title": "DroneLife — Drone News in Mining",
        "text": (
            "Drone adoption in mining is accelerating as companies seek to improve "
            "safety and efficiency. Rio Tinto has deployed drone fleets across multiple "
            "mine sites for automated stockpile measurement, equipment inspection, "
            "and safety monitoring. The program has reduced manual inspection time "
            "by 70 percent while improving data accuracy and worker safety."
        ),
    },
    "mining-recruitment.com": {
        "title": "Mining Recruitment — Automation Jobs",
        "text": (
            "Rio Tinto is actively recruiting automation engineers, robotics specialists, "
            "fleet management system engineers, and remote operations specialists. "
            "The company is expanding its autonomous mining team to support the "
            "deployment of autonomous haulage systems, drone inspection programs, "
            "and remote operations centers."
        ),
    },
    "mining.com": {
        "title": "Mining.com — Automation Talent Shortage",
        "text": (
            "The mining industry is facing a critical shortage of automation and "
            "robotics talent as companies like Rio Tinto accelerate their autonomous "
            "mining programs. Demand for fleet management and drone automation "
            "engineers far outpaces supply."
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
