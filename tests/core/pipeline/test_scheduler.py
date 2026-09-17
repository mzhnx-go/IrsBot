from uuid import uuid4

import pytest 
from app.core.pipeline.base import PipelineContext, PipelineScheduler, Stage

class FakeStage(Stage):
    """可配置的假 Stage：记录执行、可选叫停、可选返回None."""
    def __init__(self, name: str, calls: list, stop=False, return_none = False):
        self.name = name
        self.calls = calls
        self.stop = stop
        self.return_none = return_none
    
    async def process(self, context):
        self.calls.append(self.name)
        if self.stop:
            context.stop_propagation()
        if self.return_none:
            return None
        return context

def make_context() -> PipelineContext:
    """造一个最小可用的测试上下文."""
    return PipelineContext(
        user_id=uuid4(),
        session_id="test",
        event_data={},
    )

@pytest.mark.asyncio
async def test_execute_runs_all_stages_in_order():
    calls = []
    s1 = FakeStage("s1", calls)
    s2 = FakeStage("s2", calls)
    s3 = FakeStage("s3", calls)
    result = await PipelineScheduler([s1, s2, s3]).execute(make_context())

    assert calls == ["s1", "s2", "s3"]
    assert result.stopped is False
    assert result.event_data == {}
    
@pytest.mark.asyncio
async def test_execute_stops_when_stage_stops():
    calls = []
    s1 = FakeStage("s1", calls)
    s1.stop = True
    s2 = FakeStage("s2", calls)
    s3 = FakeStage("s3", calls)
    result = await PipelineScheduler([s1, s2, s3]).execute(make_context())

    assert calls == ["s1"]
    assert result.stopped is True

@pytest.mark.asyncio
async def test_execute_stops_when_stage_returns_none():
    calls = []
    s1 = FakeStage("s1", calls)
    s2 = FakeStage("s2", calls)
    s2.return_none = True
    s3 = FakeStage("s3", calls)
    result = await PipelineScheduler([s1, s2, s3]).execute(make_context())


    assert calls == ["s1", "s2"]
    assert result.stopped is True

@pytest.mark.asyncio
async def test_execute_empty_stages():
    ctx = make_context()
    result = await PipelineScheduler([]).execute(ctx)
    assert result is ctx
    assert result.stopped is False
    




        