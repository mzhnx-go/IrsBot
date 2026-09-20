"""invoke_llm_node 空输出重试测试（Phase 12.5）."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.agent.nodes import _EmptyOutputError, _invoke_with_retry, _is_retryable


def _resp(content="", tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls or [])


@pytest.mark.asyncio
async def test_empty_output_retried_until_success():
    """前两次空输出、第三次正常 → 返回第三次结果."""
    llm = AsyncMock()
    llm.ainvoke.side_effect = [_resp(), _resp(), _resp(content="ok")]
    result = await _invoke_with_retry(llm, [])
    assert result.content == "ok"
    assert llm.ainvoke.await_count == 3


@pytest.mark.asyncio
async def test_empty_output_fails_after_3_attempts():
    """连续空输出 → 3 次后抛 _EmptyOutputError（reraise=True）."""
    llm = AsyncMock()
    llm.ainvoke.side_effect = [_resp(), _resp(), _resp()]
    with pytest.raises(_EmptyOutputError):
        await _invoke_with_retry(llm, [])
    assert llm.ainvoke.await_count == 3


@pytest.mark.asyncio
async def test_non_empty_output_no_retry():
    llm = AsyncMock()
    llm.ainvoke.return_value = _resp(content="hello")
    result = await _invoke_with_retry(llm, [])
    assert result.content == "hello"
    assert llm.ainvoke.await_count == 1


def test_only_empty_output_error_is_retryable():
    assert _is_retryable(_EmptyOutputError("x")) is True
    assert _is_retryable(ValueError("x")) is False


def test_response_with_tool_calls_not_empty():
    """有 tool_calls 的响应不算空输出，不应触发重试."""
    assert _is_empty_response_check(_resp(tool_calls=[{"id": "1"}])) is False


def _is_empty_response_check(resp) -> bool:
    from app.core.agent.nodes import _is_empty_response

    return _is_empty_response(resp)
