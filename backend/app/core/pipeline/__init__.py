"""Pipeline core module — 顺序模型消息处理流水线.

对外暴露 Pipeline 的核心类型，方便外部 `from app.core.pipeline import PipelineScheduler`。
"""

from app.core.pipeline.base import (
    EventKey,
    PipelineContext,
    PipelineScheduler,
    Stage,
)
from app.core.pipeline.stages import (
    PreProcessStage,
    SessionStatusStage,
    get_rate_limit_stage,
)


async def run_entry_stages(context: PipelineContext) -> PipelineContext:
    """执行 WS 与 REST 共用的前置 Stage（按 STAGES_ORDER 顺序）.

    RateLimit → SessionStatus → PreProcess。Process 及之后的 Stage
    因两条通道的输出形态不同（流式 vs 一次性），由各自路由自行执行。

    判定结果通过 event_data 读取：
        rate_limited=True → 限流命中
        error 键存在      → 会话停用或消息为空
    """
    scheduler = PipelineScheduler(
        [
            get_rate_limit_stage(),
            SessionStatusStage(),
            PreProcessStage(),
        ]
    )
    return await scheduler.execute(context)


__all__ = [
    "EventKey",
    "PipelineContext",
    "Stage",
    "PipelineScheduler",
    "run_entry_stages",
]
