"""Knowledge base query tool — placeholder for RAG integration."""

from app.core.agent.tools import register_tool


@register_tool(
    "knowledge_base_query",
    "Query the knowledge base for relevant information",
    category="rag",
)
async def knowledge_base_query(
    query: str,
    kb_id: str | None = None,
    top_k: int = 3,
) -> str:
    """Query the knowledge base and return relevant document chunks.

    Args:
        query: The search query.
        kb_id: Optional specific knowledge base ID to query.
        top_k: Number of results to return.
    """
    # Placeholder: in production this integrates with KnowledgeBaseManager
    return (
        f"[Knowledge Base Query] Query: '{query}', "
        f"KB: {kb_id or 'all'}, Top-K: {top_k}\n"
        "No knowledge base configured. Upload documents to enable RAG."
    )
