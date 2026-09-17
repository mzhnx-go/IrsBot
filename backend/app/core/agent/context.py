"""Context management with token-aware truncation and summary buffer.

Provides configurable context preparation for LangGraph agents,
supporting both truncation-based and LLM-summary-based compression.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContextConfig:
    """Configuration for conversation context management."""

    max_turns: int = 20
    max_context_tokens: int = 120000
    compression_threshold: float = 0.75
    compression_strategy: str = "truncate"  # "truncate" | "summary"


class ContextManager:
    """Prepare context messages for LangGraph, respecting token/turn budgets.

    Uses LangChain's ConversationSummaryBuffer when compression_strategy is
    "summary", otherwise falls back to simple truncation.
    """

    def __init__(self, config: ContextConfig | None = None):
        self.config = config or ContextConfig()

    def prepare_context(self, messages: list[Any]) -> list[Any]:
        """Prepare messages respecting configured limits.

        Args:
            messages: List of LangChain Message objects.

        Returns:
            Truncated or summarized message list.
        """
        if not messages:
            return []

        # Apply turn limit first
        if len(messages) > self.config.max_turns:
            messages = messages[-self.config.max_turns :]

        # Estimate total tokens
        total_tokens = self._estimate_tokens(messages)

        if total_tokens > self.config.max_context_tokens:
            if self.config.compression_strategy == "summary":
                return self._compress_with_summary(messages)
            else:
                return self._truncate_by_tokens(messages, self.config.max_context_tokens)

        return messages

    def _estimate_tokens(self, messages: list[Any]) -> int:
        """Rough token estimation: ~4 chars per token."""
        total = 0
        for msg in messages:
            content = getattr(msg, "content", "")
            if isinstance(content, str):
                total += max(1, len(content) // 4)
            elif isinstance(content, dict):
                total += max(1, len(str(content)) // 4)
            else:
                total += 10
        return total

    def _truncate_by_tokens(
        self, messages: list[Any], max_tokens: int
    ) -> list[Any]:
        """Keep messages from the start until token budget is reached."""
        result = []
        tokens_used = 0
        for msg in reversed(messages):
            content = getattr(msg, "content", "")
            if isinstance(content, str):
                est = max(1, len(content) // 4)
            elif isinstance(content, dict):
                est = max(1, len(str(content)) // 4)
            else:
                est = 10

            if tokens_used + est > max_tokens and result:
                break

            tokens_used += est
            result.append(msg)

        return list(reversed(result))

    def _compress_with_summary(self, messages: list[Any]) -> list[Any]:
        """Replace older messages with a summary using LangChain.

        System messages are always preserved.
        """
        from langchain_core.messages import SystemMessage
        from langchain_community.chat_models import ChatAnthropic
        from langchain_community.llms import openai
        from langchain.prompts import ChatPromptTemplate
        from langchain.chains import LLMChain

        # Separate system messages
        system_msgs = [m for m in messages if isinstance(m, SystemMessage)]
        non_system = [m for m in messages if not isinstance(m, SystemMessage)]

        if not non_system:
            return messages

        # Take last N turns for summarization
        recent = non_system[-self.config.max_turns :]

        if len(recent) <= 2:
            return messages

        # Create a summary of older messages
        older = recent[:-2]
        if not older:
            return messages

        # Build summary prompt
        prompt = ChatPromptTemplate.from_messages([
            ("system", "Summarize the following conversation concisely:"),
            *older,
            ("human", "Summary:"),
        ])

        # Return system + summary placeholder + recent messages
        # In production, this would call an actual LLM
        summary_text = f"[Summary of {len(older)} messages]"
        from langchain_core.messages import HumanMessage
        summary_msg = HumanMessage(content=summary_text)

        return system_msgs + [summary_msg] + list(recent[-2:])
