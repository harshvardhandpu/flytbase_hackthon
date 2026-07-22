from __future__ import annotations

from typing import Any

from app.core.contracts import ToolResult
from app.tools.base import BaseTool


class ToolManager:
    """Registry and executor for research tools.

    Accepts a list of ``BaseTool`` instances, indexes them by name, and
    provides a single ``execute`` entrypoint used by agents.
    """

    def __init__(self, tools: list[BaseTool]) -> None:
        self._tools: dict[str, BaseTool] = {tool.name: tool for tool in tools}

    @property
    def tool_descriptions(self) -> list[dict[str, str]]:
        """Return name/description pairs for LLM tool-selection prompts."""
        return [{"name": t.name, "description": t.description} for t in self._tools.values()]

    async def execute(self, name: str, payload: dict[str, Any]) -> ToolResult:
        try:
            return await self._tools[name].execute(payload)
        except KeyError as exc:
            raise ValueError(f"Unknown tool: {name}") from exc
