from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.core.contracts import ToolResult


class BaseTool(ABC):
    """Abstract base for all ScoutOS tools.

    Every tool exposes a ``name``, a ``description`` (used by agents for
    tool-selection prompts), and an async ``execute`` method.
    """

    name: str
    description: str = ""

    @abstractmethod
    async def execute(self, payload: dict[str, Any]) -> ToolResult:
        """Execute the tool and return structured results with sources."""
