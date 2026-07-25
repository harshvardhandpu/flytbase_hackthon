from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, Field


class ProviderError(Exception):
    """Raised when an AI provider call fails due to network, auth, or API errors.

    Attributes:
        provider: Name of the provider that failed (e.g. "anthropic", "openai").
        status_code: HTTP status code if applicable, else None.
        message: Human-readable error description.
    """

    def __init__(self, provider: str, status_code: int | None, message: str) -> None:
        self.provider = provider
        self.status_code = status_code
        self.message = message
        super().__init__(f"[{provider}] {message}")


class AIMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


class AIRequest(BaseModel):
    messages: list[AIMessage]
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=32000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AIResponse(BaseModel):
    content: str
    model: str | None = None
    provider: str
    usage: dict[str, int] = Field(default_factory=dict)
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class AIProvider(Protocol):
    """Portable LLM capability used by agents."""

    name: str

    async def generate(self, request: AIRequest) -> AIResponse: ...


class KnowledgeDocument(BaseModel):
    id: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryStore(Protocol):
    async def search(
        self, query: str, *, scope: str, limit: int = 5
    ) -> list[KnowledgeDocument]: ...

    async def save(self, document: KnowledgeDocument, *, scope: str) -> None: ...


class ToolResult(BaseModel):
    content: dict[str, Any]
    sources: list[str] = Field(default_factory=list)


class AgentTool(Protocol):
    name: str

    async def execute(self, payload: dict[str, Any]) -> ToolResult: ...


class AgentTaskInput(BaseModel):
    id: UUID
    agent_type: str
    input_data: dict[str, Any]
    company_id: UUID | None = None
    lead_id: UUID | None = None
    requires_human_approval: bool = False


class AgentResult(BaseModel):
    output_data: dict[str, Any]
    summary: str
    requires_human_approval: bool = False


class AgentContext(BaseModel):
    """Serializable per-run identifiers; dependencies are injected into the agent instance."""

    task_id: UUID
    correlation_id: str


class BaseAgent(ABC):
    agent_type: str

    @abstractmethod
    async def run(self, context: AgentContext, task: AgentTaskInput) -> AgentResult:
        """Execute a bounded task and return a reviewable structured result."""


class AgentRegistry(Protocol):
    def get(self, agent_type: str) -> BaseAgent: ...
