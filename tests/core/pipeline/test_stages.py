"""Pipeline Stages 单元测试 — RateLimit / SessionStatus / PreProcess / Process / PostProcess."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from app.core.db.models import AgentRun
from app.core.pipeline import run_entry_stages
from app.core.pipeline.base import EventKey, PipelineContext
from app.core.pipeline.stages.post_process import PostProcessStage
from app.core.pipeline.stages.pre_process import PreProcessStage
from app.core.pipeline.stages.process import ProcessStage
from app.core.pipeline.stages.rate_limit import RateLimitStage, get_rate_limit_stage
from app.core.pipeline.stages.session_status import SessionStatusStage


def make_context(user_id=None) -> PipelineContext:
    return PipelineContext(
        user_id=user_id or uuid4(),
        session_id="test",
        event_data={EventKey.USER_MESSAGE: "你好"},
    )


# ─── RateLimitStage ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_rate_limit_allows_under_limit():
    stage = RateLimitStage(max_requests=2, window_seconds=60)
    user = uuid4()
    for _ in range(2):
        result = await stage.process(make_context(user_id=user))
        assert result.stopped is False
        assert EventKey.RATE_LIMITED not in result.event_data


@pytest.mark.asyncio
async def test_rate_limit_blocks_over_limit():
    stage = RateLimitStage(max_requests=2, window_seconds=60)
    user = uuid4()
    for _ in range(2):
        await stage.process(make_context(user_id=user))
    result = await stage.process(make_context(user_id=user))
    assert result.stopped is True
    assert result.event_data[EventKey.RATE_LIMITED] is True


@pytest.mark.asyncio
async def test_rate_limit_isolates_users():
    stage = RateLimitStage(max_requests=1, window_seconds=60)
    user_a = uuid4()
    first = await stage.process(make_context(user_id=user_a))
    assert first.stopped is False
    second = await stage.process(make_context(user_id=user_a))
    assert second.stopped is True

    # 用户 B：新 user_id → 全新队列，放行
    third = await stage.process(make_context(user_id=uuid4()))
    assert third.stopped is False


# ─── PreProcessStage ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_preprocess_strips_whitespace():
    stage = PreProcessStage(max_len=10)
    ctx = make_context()
    ctx.event_data[EventKey.USER_MESSAGE] = "  你好  "

    result = await stage.process(ctx)

    assert result.event_data[EventKey.USER_MESSAGE] == "你好"
    assert result.stopped is False


@pytest.mark.asyncio
async def test_preprocess_rejects_empty():
    stage = PreProcessStage(max_len=10)
    ctx = make_context()
    ctx.event_data[EventKey.USER_MESSAGE] = "   "

    result = await stage.process(ctx)

    assert result.stopped is True
    assert EventKey.ERROR in result.event_data


@pytest.mark.asyncio
async def test_preprocess_allows_empty_text_with_attachments():
    """只发附件不打字：正文为空仍应放行（内容在附件里）"""
    stage = PreProcessStage(max_len=10)
    ctx = make_context()
    ctx.event_data[EventKey.USER_MESSAGE] = "  "
    ctx.event_data[EventKey.HAS_ATTACHMENTS] = True

    result = await stage.process(ctx)

    assert result.stopped is False
    assert EventKey.ERROR not in result.event_data


@pytest.mark.asyncio
async def test_preprocess_truncates_long():
    stage = PreProcessStage(max_len=10)
    ctx = make_context()
    ctx.event_data[EventKey.USER_MESSAGE] = "a" * 20

    result = await stage.process(ctx)

    assert result.event_data[EventKey.USER_MESSAGE] == "a" * 10
    assert result.stopped is False


@pytest.mark.asyncio
async def test_preprocess_short_message_unchanged():
    stage = PreProcessStage(max_len=10)
    ctx = make_context()
    ctx.event_data[EventKey.USER_MESSAGE] = "你好"

    result = await stage.process(ctx)

    assert result.event_data[EventKey.USER_MESSAGE] == "你好"
    assert result.stopped is False


@pytest.mark.asyncio
async def test_process_calls_agent_and_stores_result():
    ctx = make_context()
    ctx.event_data[EventKey.SESSION] = MagicMock()
    ctx.event_data[EventKey.HISTORY] = []

    fake_agent = AsyncMock()
    fake_result = {"messages": [MagicMock(content="hi")], "step_count": 2}
    fake_agent.run.return_value = fake_result

    stage = ProcessStage()
    with patch("app.core.pipeline.stages.process.Agent", return_value=fake_agent):
        result = await stage.process(ctx)

    assert result.event_data[EventKey.AGENT_RESULT] is fake_result


@pytest.mark.asyncio
async def test_post_process_creates_agent_run():
    fake_session = MagicMock()
    ctx = make_context()
    ctx.event_data[EventKey.SESSION] = fake_session
    ctx.event_data[EventKey.AGENT_RESULT] = {
        "messages": [MagicMock(content="AI回复")],
        "step_count": 2,
    }

    stage = PostProcessStage()
    await stage.process(ctx)

    fake_session.add.assert_called_once()
    fake_session.commit.assert_called_once()
    run = fake_session.add.call_args[0][0]
    assert isinstance(run, AgentRun)


@pytest.mark.asyncio
async def test_post_process_stores_correct_fields():
    fake_session = MagicMock()
    ctx = make_context()
    ctx.event_data[EventKey.SESSION] = fake_session
    ctx.event_data[EventKey.AGENT_RESULT] = {
        "messages": [MagicMock(content="AI回复")],
        "step_count": 2,
    }
    stage = PostProcessStage()
    await stage.process(ctx)
    fake_session.add.assert_called_once()
    fake_session.commit.assert_called_once()
    run = fake_session.add.call_args[0][0]
    assert run.user_id == ctx.user_id
    assert run.conversation_id is ctx.conversation_id
    assert run.input_text == "你好"
    assert run.output_text == "AI回复"
    assert run.tool_calls_made == 2
    assert run.status == "completed"


@pytest.mark.asyncio
async def test_process_uses_history_default_empty():
    fake_agent = AsyncMock()
    fake_agent.run.return_value = {
        "messages": [MagicMock(content="hi")],
        "step_count": 1,
    }

    ctx = make_context()
    ctx.event_data[EventKey.SESSION] = MagicMock()

    stage = ProcessStage()
    with patch("app.core.pipeline.stages.process.Agent", return_value=fake_agent):
        await stage.process(ctx)

    assert fake_agent.run.call_args.kwargs["history"] == []


# ─── SessionStatusStage ───────────────────────────────────────


@pytest.mark.asyncio
async def test_session_status_blocks_disabled_conversation():
    stage = SessionStatusStage()
    ctx = make_context()
    conversation = MagicMock(is_enabled=False)
    ctx.event_data[EventKey.CONVERSATION] = conversation

    result = await stage.process(ctx)

    assert result.stopped is True
    assert EventKey.ERROR in result.event_data


@pytest.mark.asyncio
async def test_session_status_allows_enabled_conversation():
    stage = SessionStatusStage()
    ctx = make_context()
    ctx.event_data[EventKey.CONVERSATION] = MagicMock(is_enabled=True)

    result = await stage.process(ctx)

    assert result.stopped is False
    assert EventKey.ERROR not in result.event_data


@pytest.mark.asyncio
async def test_session_status_passes_when_no_conversation():
    stage = SessionStatusStage()
    result = await stage.process(make_context())
    assert result.stopped is False


# ─── run_entry_stages（WS/REST 共用前置 Stage） ────────────────


@pytest.mark.asyncio
async def test_run_entry_stages_rate_limited():
    ctx = make_context()
    ctx.event_data[EventKey.CONVERSATION] = MagicMock(is_enabled=True)
    # 预置一个刚满的窗口：直接操纵共享实例计数
    stage = get_rate_limit_stage()
    original_max = stage.max_requests
    stage.max_requests = 0  # type: ignore[misc]

    try:
        result = await run_entry_stages(ctx)
        assert result.event_data.get(EventKey.RATE_LIMITED) is True
        assert result.stopped is True
    finally:
        stage.max_requests = original_max  # 还原默认，避免污染其它测试


@pytest.mark.asyncio
async def test_run_entry_stages_clean_pass():
    ctx = make_context()
    ctx.event_data[EventKey.CONVERSATION] = MagicMock(is_enabled=True)

    result = await run_entry_stages(ctx)

    assert result.stopped is False
    assert EventKey.RATE_LIMITED not in result.event_data
    assert EventKey.ERROR not in result.event_data
    assert result.event_data[EventKey.USER_MESSAGE] == "你好"


@pytest.mark.asyncio
async def test_get_rate_limit_stage_returns_singleton():
    assert get_rate_limit_stage() is get_rate_limit_stage()
