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
