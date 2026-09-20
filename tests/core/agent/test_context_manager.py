"""context_manager 单元测试（Phase 12.5）.

重点：fix_messages 必须保证 assistant(tool_calls) 与 tool 消息配对，
否则截断后的历史发给 OpenAI 直接 400。
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.core.agent.context_manager import (
    ContextTruncator,
    estimate_tokens,
    fix_messages,
    split_into_rounds,
)


# ── estimate_tokens ──────────────────────────────────────────


def test_estimate_tokens_chinese_heavier():
    zh = AIMessage(content="你好世界" * 10)  # 40 个汉字
    en = AIMessage(content="a" * 40)
    assert estimate_tokens(zh) > estimate_tokens(en)


def test_estimate_tokens_multimodal_flat_rate():
    msg = AIMessage(content=[{"type": "image_url", "image_url": {"url": "x"}}])
    assert estimate_tokens(msg) == 800


# ── split_into_rounds ────────────────────────────────────────


def test_split_into_rounds_basic():
    msgs = [
        SystemMessage(content="sys"),
        HumanMessage(content="hi"),
        AIMessage(content="hello"),
        HumanMessage(content="again"),
        AIMessage(content="ok"),
    ]
    rounds = split_into_rounds(msgs)
    assert len(rounds) == 3  # system 前缀 + 2 轮
    assert rounds[0][0].type == "system"


# ── fix_messages ─────────────────────────────────────────────


def test_fix_drops_orphan_tool_message():
    """悬空 tool 消息（前面没有 assistant 声明）必须被丢弃."""
    msgs = [
        HumanMessage(content="hi"),
        ToolMessage(content="orphan", tool_call_id="call-999"),
        AIMessage(content="hello"),
    ]
    fixed = fix_messages(msgs)
    assert not any(isinstance(m, ToolMessage) for m in fixed)
    assert fixed[-1].content == "hello"


def test_fix_appends_synthetic_tool_for_unanswered_call():
    """assistant 声明了 tool_call 但没有响应 → 补合成 ToolMessage."""
    msgs = [
        HumanMessage(content="hi"),
        AIMessage(
            content="",
            tool_calls=[{"name": "search", "args": {}, "id": "call-1"}],
        ),
    ]
    fixed = fix_messages(msgs)
    tool_msgs = [m for m in fixed if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 1
    assert tool_msgs[0].tool_call_id == "call-1"


def test_fix_keeps_well_formed_pair():
    """正常配对序列原样保留."""
    msgs = [
        HumanMessage(content="hi"),
        AIMessage(
            content="",
            tool_calls=[{"name": "search", "args": {}, "id": "call-1"}],
        ),
        ToolMessage(content="result", tool_call_id="call-1"),
        AIMessage(content="done"),
    ]
    fixed = fix_messages(msgs)
    assert fixed == msgs


def test_fix_consecutive_tool_call_blocks():
    """连续两段 tool_calls 各自配对，互不串扰."""
    msgs = [
        AIMessage(
            content="",
            tool_calls=[{"name": "a", "args": {}, "id": "call-1"}],
        ),
        ToolMessage(content="r1", tool_call_id="call-1"),
        AIMessage(
            content="",
            tool_calls=[{"name": "b", "args": {}, "id": "call-2"}],
        ),
        # call-2 的响应丢了，下一轮被截断
        HumanMessage(content="next"),
    ]
    fixed = fix_messages(msgs)
    tool_ids = [m.tool_call_id for m in fixed if isinstance(m, ToolMessage)]
    assert tool_ids == ["call-1", "call-2"]


# ── ContextTruncator ─────────────────────────────────────────


def _conversation_with_tool_pair(rounds: int) -> list:
    msgs: list = [SystemMessage(content="sys")]
    for i in range(rounds):
        msgs.append(HumanMessage(content=f"q{i}"))
        if i == 0:  # 只在第 1 轮放一对 tool_calls/tool
            msgs.append(
                AIMessage(
                    content="",
                    tool_calls=[{"name": "t", "args": {}, "id": "call-1"}],
                )
            )
            msgs.append(ToolMessage(content="r", tool_call_id="call-1"))
        else:
            msgs.append(AIMessage(content=f"a{i}"))
    return msgs


def test_truncator_truncate_by_turns():
    tr = ContextTruncator(max_turns=2, strategy="truncate_by_turns")
    out = tr.truncate(_conversation_with_tool_pair(5))
    rounds = split_into_rounds(out)
    assert len(rounds) <= 3  # system 前缀 + 至多 2 轮


def test_truncator_dropping_oldest_respects_token_budget():
    tr = ContextTruncator(max_tokens=50, strategy="dropping_oldest_turns")
    out = tr.truncate(_conversation_with_tool_pair(10))
    assert out  # 至少保留 system
    assert out[0].type == "system"


def test_truncator_halving():
    tr = ContextTruncator(max_tokens=30, strategy="halving")
    out = tr.truncate(_conversation_with_tool_pair(10))
    assert out
    assert out[0].type == "system"


def test_truncator_output_always_paired():
    """无论哪种策略，输出都必须过 fix_messages 兜底."""
    for strategy in ContextTruncator.STRATEGIES:
        tr = ContextTruncator(max_turns=1, max_tokens=50, strategy=strategy)
        out = tr.truncate(_conversation_with_tool_pair(5))
        tool_ids = {m.tool_call_id for m in out if isinstance(m, ToolMessage)}
        ai_calls = {
            tc["id"]
            for m in out
            if isinstance(m, AIMessage) and getattr(m, "tool_calls", None)
            for tc in m.tool_calls
        }
        assert tool_ids == ai_calls  # 双向配对


def test_truncator_invalid_strategy_rejected():
    with pytest.raises(ValueError):
        ContextTruncator(strategy="nope")
