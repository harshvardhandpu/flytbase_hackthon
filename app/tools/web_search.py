"""Web search tool — Tavily API with simulated fallback.

Uses the Tavily Search API when a key is configured; otherwise
falls back to the existing simulated search for dev/test/demo.

No third-party ``tavily`` package is required — requests go through ``httpx``.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from app.config import get_settings
from app.core.contracts import ToolResult
from app.tools.base import BaseTool

logger = logging.getLogger(__name__)

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

TAVILY_API_URL = "https://api.tavily.com/search"


def _clean_api_key(value: str | None) -> str | None:
    """Normalize a raw key string. Never log the value."""
    if not value or not isinstance(value, str):
        return None
    cleaned = value.strip().strip('"').strip("'").strip()
    return cleaned or None


def resolve_tavily_api_key() -> str | None:
    """Resolve TAVILY_API_KEY from the live process environment first.

    Priority:
      1. ``os.getenv("TAVILY_API_KEY")`` — what Railway injects at runtime
      2. ``get_settings().tavily_api_key`` — pydantic-settings / ``.env`` fallback

    Using ``os.getenv`` first avoids stale ``lru_cache`` Settings and ensures
    production env vars win even if Settings init missed them.
    """
    env_key = _clean_api_key(os.getenv("TAVILY_API_KEY"))
    if env_key:
        return env_key

    try:
        settings_key = _clean_api_key(get_settings().tavily_api_key)
    except Exception:  # noqa: BLE001 — never break search init
        settings_key = None
    return settings_key


class WebSearchTool(BaseTool):
    """Web search via Tavily API, falling back to simulated results.

    Requires ``TAVILY_API_KEY`` environment variable for real API access.
    When the key is absent, returns deterministic mock results matching
    known company patterns.

    Uses ``httpx`` (already a project dependency) — there is no separate
    ``tavily`` Python package to install.
    """

    name = "web_search"
    description = "Search the web for company information, news, and industry signals."

    _simulated: bool
    _api_key: str | None

    def __init__(self) -> None:
        # Verify httpx import path is usable (Tavily client dependency)
        try:
            _ = httpx.AsyncClient
            httpx_ok = True
        except Exception:  # noqa: BLE001
            httpx_ok = False

        self._api_key = resolve_tavily_api_key()
        self._simulated = not bool(self._api_key)

        logger.info(
            "[TAVILY INIT] key_present=%s httpx_ok=%s client=httpx",
            "true" if self._api_key else "false",
            "true" if httpx_ok else "false",
        )
        if self._simulated:
            logger.warning(
                "[TAVILY INIT] missing TAVILY_API_KEY — web_search will use simulated fallback"
            )

    async def execute(self, payload: dict[str, Any]) -> ToolResult:
        query: str = payload.get("query", "")
        max_results: int = payload.get("max_results", 5)

        logger.info("[SEARCH] query=%s", query)

        if self._simulated or not self._api_key:
            logger.info("[SEARCH] provider=fallback")
            result = self._simulated_search(query, max_results)
            logger.info(
                "[SEARCH] results_count=%s",
                result.content.get("result_count", 0),
            )
            return result

        result = await self._tavily_search(query, max_results)
        # If Tavily failed, _tavily_search returns simulated results
        provider = "fallback" if result.content.get("simulated") else "tavily"
        logger.info("[SEARCH] provider=%s", provider)
        logger.info(
            "[SEARCH] results_count=%s",
            result.content.get("result_count", 0),
        )
        return result

    # ── Tavily API path ────────────────────────────────────────────────

    async def _tavily_search(self, query: str, max_results: int) -> ToolResult:
        if not self._api_key:
            logger.warning(
                "[SEARCH] tavily_error status=None reason=missing_api_key"
            )
            return self._simulated_search(query, max_results)

        # Prefer Bearer auth (current Tavily docs); also send api_key in body
        # for older endpoint compatibility. Never log either value.
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        body = {
            "api_key": self._api_key,
            "query": query,
            # basic: 1 credit, wider free-tier compatibility than advanced
            "search_depth": "basic",
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    TAVILY_API_URL,
                    headers=headers,
                    json=body,
                )
                if resp.status_code >= 400:
                    reason = (resp.reason_phrase or "http_error")[:120]
                    logger.warning(
                        "[SEARCH] tavily_error status=%s reason=%s",
                        resp.status_code,
                        reason,
                    )
                    return self._simulated_search(query, max_results)

                data = resp.json()
        except httpx.HTTPStatusError as exc:
            reason = (exc.response.reason_phrase or "http_error")[:120]
            logger.warning(
                "[SEARCH] tavily_error status=%s reason=%s",
                exc.response.status_code,
                reason,
            )
            return self._simulated_search(query, max_results)
        except httpx.HTTPError as exc:
            logger.warning(
                "[SEARCH] tavily_error status=None reason=%s",
                f"{type(exc).__name__}: {str(exc)[:160]}",
            )
            return self._simulated_search(query, max_results)
        except Exception as exc:  # noqa: BLE001 — never break research pipeline
            logger.warning(
                "[SEARCH] tavily_error status=None reason=%s",
                f"{type(exc).__name__}: {str(exc)[:160]}",
            )
            return self._simulated_search(query, max_results)

        results = data.get("results", [])
        formatted = [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", ""),
            }
            for r in results[:max_results]
        ]
        sources = [r["url"] for r in formatted if r["url"]]

        return ToolResult(
            content={
                "query": query,
                "results": formatted,
                "result_count": len(formatted),
            },
            sources=sources,
        )

    # ── Simulated fallback path ─────────────────────────────────────────

    def _simulated_search(self, query: str, max_results: int) -> ToolResult:
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
                "simulated": True,
            },
            sources=sources,
        )
