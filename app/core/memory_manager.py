from app.core.contracts import KnowledgeDocument, MemoryStore


class MemoryManager:
    """Keeps agent code independent from markdown, RAG, or graph implementations."""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def recall(self, query: str, scope: str) -> list[KnowledgeDocument]:
        return await self._store.search(query, scope=scope)
