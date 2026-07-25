from __future__ import annotations

from typing import Any

from app.core.contracts import ToolResult
from app.tools.base import BaseTool

_MOCK_RESULTS: dict[str, list[dict[str, str]]] = {
    "flytbase": [
        {
            "title": "FlytBase — Drone Fleet Management Platform",
            "url": "https://www.flytbase.com",
            "snippet": "FlytBase is the leading drone fleet management platform"
            " for remote operations. Enables BVLOS flights, automated missions,"
            " and enterprise drone programs.",
        },
        {
            "title": "FlytBase Raises $5M Series A for Drone Automation",
            "url": "https://techcrunch.com/2025/06/flytbase-series-a",
            "snippet": "FlytBase, a drone fleet management startup, raised $5M in Series A funding "
            "led by Accel to expand its enterprise automation platform.",
        },
        {
            "title": "FlytBase Integrates with DJI Drones",
            "url": "https://dronelife.com/flytbase-dji-integration",
            "snippet": "FlytBase now supports full integration with DJI drone ecosystem, "
            "enabling automated flight planning and real-time fleet monitoring.",
        },
    ],
    "drone inspection": [
        {
            "title": "AI-Powered Drone Inspections for Infrastructure",
            "url": "https://www.droneinspections.example/ai",
            "snippet": "Using computer vision and AI to automate infrastructure inspections "
            "with drones. Reducing manual inspection time by 80%.",
        },
        {
            "title": "Top 5 Drone Inspection Software Platforms in 2026",
            "url": "https://dronelife.com/top-inspection-platforms-2026",
            "snippet": "Comparative analysis of leading drone inspection software platforms "
            "including FlytBase, DroneDeploy, and Pix4D.",
        },
    ],
    "rio": [
        {
            "title": "Rio Tinto — Global Mining Operations",
            "url": "https://www.riotinto.com/about",
            "snippet": "Rio Tinto is a leading global mining group with operations in 35 nations. "
            "Core products include iron ore, copper, aluminum, and minerals essential for "
            "the energy transition. Rio Tinto operates large-scale open pit and underground "
            "mines worldwide.",
        },
        {
            "title": "Rio Tinto Invests in Autonomous Mining Technology",
            "url": "https://www.mining-technology.com/rio-tinto-autonomous",
            "snippet": "Rio Tinto has invested heavily in autonomous mining operations including "
            "the world's largest fleet of autonomous trucks, automated drill systems, and "
            "remote operations centers in Perth. Their 'Mine of the Future' program is "
            "a multi-year initiative to fully automate mining operations.",
        },
        {
            "title": "Rio Tinto Digital Transformation in Mining",
            "url": "https://www.mining-technology.com/digital-mining-rio-tinto",
            "snippet": "Rio Tinto is accelerating digital transformation across its mining "
            "operations. Key initiatives include AI-powered predictive maintenance, "
            "remote operations centers, drone-based site inspection, and real-time "
            "operational analytics for mine site optimization.",
        },
        {
            "title": "Rio Tinto Deploys Drones for Mine Site Inspection",
            "url": "https://www.dronelife.com/rio-tinto-drone-inspection",
            "snippet": "Rio Tinto has deployed drone fleets across multiple mine sites for "
            "automated stockpile measurement, equipment inspection, safety monitoring, "
            "and site surveillance. The program aims to reduce manual inspection "
            "time by 70 percent and improve worker safety.",
        },
        {
            "title": "Rio Tinto Hiring Automation and Robotics Engineers",
            "url": "https://www.mining-recruitment.com/rio-tinto-automation-jobs",
            "snippet": "Rio Tinto is hiring dozens of automation engineers, robotics specialists, "
            "and data scientists to support its autonomous mining initiatives. Roles include "
            "fleet management system engineers, remote operations specialists, "
            "and AI/ML engineers for predictive analytics.",
        },
        {
            "title": "Rio Tinto Expands Remote Operations Centre",
            "url": "https://www.mining-technology.com/rio-tinto-remote-ops",
            "snippet": "Rio Tinto has expanded its Operations Centre in Perth to manage "
            "15 mine sites remotely. The centre controls autonomous trucks, trains, "
            "and drills across Pilbara iron ore operations, reducing on-site headcount "
            "while improving operational efficiency.",
        },
    ],
    "mining": [
        {
            "title": "Autonomous Mining — The Future of Mining Operations",
            "url": "https://www.mining-technology.com/autonomous-mining",
            "snippet": "The mining industry is rapidly adopting autonomous technologies including "
            "autonomous haulage systems, remote operations centers, drone-based inspection, "
            "and AI-powered predictive maintenance. Major miners like Rio Tinto, BHP, "
            "and Vale are leading this transformation.",
        },
        {
            "title": "Drone Technology in Mining Operations",
            "url": "https://www.mining-technology.com/drones-in-mining",
            "snippet": "Drones are transforming mining operations with applications in "
            "stockpile measurement, blast monitoring, equipment inspection, safety "
            "surveillance, and site surveying. Drone automation reduces inspection "
            "time from days to hours while improving data accuracy.",
        },
        {
            "title": "Mining Industry Faces Automation Talent Shortage",
            "url": "https://www.mining.com/automation-talent-shortage",
            "snippet": "The mining industry is facing a critical shortage of automation and "
            "robotics talent as companies accelerate their autonomous mining programs. "
            "Demand for fleet management engineers, remote operations specialists, "
            "and drone operators far outpaces supply.",
        },
    ],
}

_DEFAULT_RESULTS = [
    {
        "title": "Company Overview and Products",
        "url": "https://www.example.com/about",
        "snippet": "Leading provider of innovative solutions in the enterprise technology sector. "
        "Serving Fortune 500 clients with cutting-edge products.",
    },
    {
        "title": "Recent News and Press Releases",
        "url": "https://news.example.com/company-updates",
        "snippet": "Company recently announced expansion into new markets and strategic "
        "partnerships with industry leaders.",
    },
]


class SimulatedWebSearchTool(BaseTool):
    """Simulated web search — realistic mock results for dev/test/demo."""

    name = "web_search"
    description = "Search the web for company information, news, and industry signals."

    async def execute(self, payload: dict[str, Any]) -> ToolResult:
        query: str = payload.get("query", "")
        max_results: int = payload.get("max_results", 5)

        # Normalise query to find the closest mock key
        query_lower = query.lower().strip()
        results = _DEFAULT_RESULTS

        for mock_key, mock_results in _MOCK_RESULTS.items():
            if mock_key in query_lower:
                results = mock_results
                break

        limited = results[:max_results]
        sources = [r["url"] for r in limited]

        return ToolResult(
            content={
                "query": query,
                "results": limited,
                "result_count": len(limited),
            },
            sources=sources,
        )
