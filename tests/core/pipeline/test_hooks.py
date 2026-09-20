"""HookBus 单元测试（Phase 12.4）."""

import pytest
from app.core.pipeline.hooks import HookBus


@pytest.mark.asyncio
async def test_register_and_emit_sync_hook():
    bus = HookBus()
    calls = []
    bus.register("on_agent_done", lambda result: calls.append(result))
    await bus.emit("on_agent_done", result={"ok": True})
    assert calls == [{"ok": True}]


@pytest.mark.asyncio
async def test_emit_async_hook():
    bus = HookBus()
    calls = []

    async def hook(**kwargs):
        calls.append(kwargs)

    bus.register("on_llm_request", hook)
    await bus.emit("on_llm_request", messages=["m"])
    assert calls == [{"messages": ["m"]}]


@pytest.mark.asyncio
async def test_hook_exception_does_not_propagate():
    bus = HookBus()

    def bad():
        raise RuntimeError("boom")

    bus.register("on_llm_response", bad)
    await bus.emit("on_llm_response", response=None)  # 不应抛异常


@pytest.mark.asyncio
async def test_unknown_hook_name_rejected():
    bus = HookBus()
    with pytest.raises(ValueError):
        bus.register("on_unknown_event", lambda: None)


@pytest.mark.asyncio
async def test_unregister():
    bus = HookBus()
    calls = []
    fn = lambda: calls.append(1)  # noqa: E731
    bus.register("on_agent_done", fn)
    bus.unregister("on_agent_done", fn)
    await bus.emit("on_agent_done")
    assert calls == []


@pytest.mark.asyncio
async def test_emit_without_hooks_is_noop():
    bus = HookBus()
    await bus.emit("on_agent_done", result=None)
