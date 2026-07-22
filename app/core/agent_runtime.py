from app.core.contracts import AgentContext, AgentRegistry, AgentResult, AgentTaskInput, BaseAgent


class InMemoryAgentRegistry:
    """Small registry replaceable by a plugin container in a later phase."""

    def __init__(self, agents: list[BaseAgent]) -> None:
        self._agents = {agent.agent_type: agent for agent in agents}

    def get(self, agent_type: str) -> BaseAgent:
        try:
            return self._agents[agent_type]
        except KeyError as exc:
            raise ValueError(f"Unknown agent type: {agent_type}") from exc


class AgentRuntime:
    def __init__(self, registry: AgentRegistry) -> None:
        self._registry = registry

    async def execute(self, context: AgentContext, task: AgentTaskInput) -> AgentResult:
        return await self._registry.get(task.agent_type).run(context, task)
