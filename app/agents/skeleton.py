from app.core.contracts import AgentContext, AgentResult, AgentTaskInput, BaseAgent


class FoundationAgent(BaseAgent):
    """Visible placeholder that prevents accidental use before its phase is implemented."""

    async def run(self, context: AgentContext, task: AgentTaskInput) -> AgentResult:
        raise NotImplementedError(f"{self.agent_type} agent is not implemented yet")
