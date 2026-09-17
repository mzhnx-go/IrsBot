"""Pipeline core module — 洋葱模型消息处理流水线.

对外暴露 Pipeline 的核心类型，方便外部 `from app.core.pipeline import PipelineScheduler`。
"""

from app.core.pipeline.base import (
    EventKey,
    PipelineContext,
    PipelineScheduler,
    Stage,
)

__all__ = [
    "EventKey",
    "PipelineContext",
    "Stage",
    "PipelineScheduler",
]
