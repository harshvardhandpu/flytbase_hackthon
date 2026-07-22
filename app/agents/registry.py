from __future__ import annotations

from typing import TYPE_CHECKING

from app.agents.inbound import InboundAgent
from app.agents.outreach import OutreachAgent
from app.agents.pipeline import PipelineAgent
from app.agents.qualification import QualificationAgent
from app.agents.research import ResearchAgent
from app.core.agent_runtime import InMemoryAgentRegistry

if TYPE_CHECKING:
    from app.core.contracts import AIProvider
    from app.core.task_manager import TaskManager
    from app.tools.tool_manager import ToolManager


def build_default_registry(
    ai_provider: AIProvider | None = None,
    tool_manager: ToolManager | None = None,
    task_manager: TaskManager | None = None,
) -> InMemoryAgentRegistry:
    """Build the default agent registry.

    Agents that require concrete dependencies receive them here.
    Agents that are not yet implemented remain as skeletons.
    """
    return InMemoryAgentRegistry(
        [
            ResearchAgent(
                ai_provider=ai_provider,
                tool_manager=tool_manager,
                task_manager=task_manager,
            ),
            QualificationAgent(
                ai_provider=ai_provider,
                tool_manager=tool_manager,
                task_manager=task_manager,
            ),
            OutreachAgent(
                ai_provider=ai_provider,
                tool_manager=tool_manager,
                task_manager=task_manager,
            ),
            InboundAgent(
                ai_provider=ai_provider,
                tool_manager=tool_manager,
                task_manager=task_manager,
            ),
            PipelineAgent(
                ai_provider=ai_provider,
                tool_manager=tool_manager,
                task_manager=task_manager,
            ),
        ]
    )
