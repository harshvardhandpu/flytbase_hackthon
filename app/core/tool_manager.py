from app.core.contracts import AgentTool, ToolResult


class ToolManager:
    def __init__(self, tools: list[AgentTool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    async def execute(self, name: str, payload: dict) -> ToolResult:
        try:
            return await self._tools[name].execute(payload)
        except KeyError as exc:
            raise ValueError(f"Unknown tool: {name}") from exc
