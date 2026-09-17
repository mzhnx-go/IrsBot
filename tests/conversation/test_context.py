"""Tests for ContextManager."""

import uuid

import pytest
from sqlmodel import Session

from app.core.agent.context import ContextConfig, ContextManager
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage


class TestContextConfig:
    def test_defaults(self):
        cfg = ContextConfig()
        assert cfg.max_turns == 20
        assert cfg.max_context_tokens == 120000
        assert cfg.compression_threshold == 0.75
        assert cfg.compression_strategy == "truncate"

    def test_custom_summary_strategy(self):
        cfg = ContextConfig(compression_strategy="summary")
        assert cfg.compression_strategy == "summary"


class TestContextManagerTruncate:
    def test_empty_messages(self):
        mgr = ContextManager()
        assert mgr.prepare_context([]) == []

    def test_within_limits(self):
        mgr = ContextManager(ContextConfig(max_turns=20, max_context_tokens=100000))
        msgs = [HumanMessage(content="Hello")]
        result = mgr.prepare_context(msgs)
        assert len(result) == 1

    def test_respects_max_turns(self):
        mgr = ContextManager(ContextConfig(max_turns=3))
        msgs = [HumanMessage(content=f"msg{i}") for i in range(10)]
        result = mgr.prepare_context(msgs)
        assert len(result) == 3

    def test_respects_max_tokens(self):
        mgr = ContextManager(ContextConfig(max_context_tokens=50))
        # Each message ~100 chars = ~25 tokens
        msgs = [HumanMessage(content="x" * 100) for _ in range(10)]
        result = mgr.prepare_context(msgs)
        # Should truncate to fit ~50 tokens (~2 messages)
        assert len(result) <= 3

    def test_preserves_system_messages(self):
        mgr = ContextManager()
        msgs = [SystemMessage(content="You are helpful."), HumanMessage(content="Hi")]
        result = mgr.prepare_context(msgs)
        assert len(result) == 2
        assert isinstance(result[0], SystemMessage)

    def test_alternating_messages(self):
        mgr = ContextManager()
        msgs = []
        for i in range(6):
            msgs.append(HumanMessage(content=f"user{i}"))
            msgs.append(AIMessage(content=f"ai{i}"))
        result = mgr.prepare_context(msgs)
        assert len(result) == 12


class TestContextManagerSummary:
    def test_summary_compression(self):
        cfg = ContextConfig(
            max_turns=20,
            compression_strategy="summary",
            max_context_tokens=50,
        )
        mgr = ContextManager(cfg)
        msgs = [HumanMessage(content=f"msg{i}") for i in range(10)]
        result = mgr.prepare_context(msgs)
        # Should compress to fewer messages
        assert len(result) <= len(msgs)

    def test_no_compression_when_within_budget(self):
        cfg = ContextConfig(
            max_context_tokens=100000,
            compression_strategy="summary",
        )
        mgr = ContextManager(cfg)
        msgs = [HumanMessage(content="Hello"), AIMessage(content="Hi")]
        result = mgr.prepare_context(msgs)
        assert len(result) == 2
