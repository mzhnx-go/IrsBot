"""Pipeline 基础框架 — 上下文、Stage、调度器."""

from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class EventKey:
    """event_data 标准键名，防止魔法字符串."""

    USER_MESSAGE = "user_message"
    HISTORY = "history"
    SESSION = "session"
    AGENT_RESULT = "agent_result"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"


class PipelineContext(BaseModel):
    """一次消息请求的上下文，在流水线的所有 Stage 之间共享.

    event_data 标准键契约（各 Stage 通过 EventKey 读写）:
        user_message: str    用户消息（路由写入，PreProcess 清洗后写回）
        history: list        历史消息（路由写入）
        session: Session     数据库会话（路由写入）
        agent_result: dict   Agent 运行结果（Process 写入，PostProcess 消费）
        rate_limited: bool   是否被限流（RateLimit 写入）
        error: str           错误信息（各 Stage 写入）
    """

    user_id: UUID
    session_id: str
    event_data: dict[str, Any]
    conversation_id: UUID | None = None
    stopped: bool = False

    def stop_propagation(self) -> None:
        """停止流水线继续传播."""
        self.stopped = True

class Stage(ABC):
    """流水线中的一个处理环节.

    每个 Stage 只负责一件事。返回 None 表示终止流水线。
    """

    @abstractmethod
    async def process(self, context: PipelineContext) -> PipelineContext | None:
        """处理上下文，返回上下文或 None（终止）."""
        raise NotImplementedError

class PipelineScheduler:
    """按顺序执行所有 Stage 的调度器."""
    def __init__(self, stages: list[Stage]):
        self.stages = stages

    async def execute(self, context: PipelineContext) -> PipelineContext:
        """让 context 依次穿过所有 Stage，返回最终上下文."""
        for stage in self.stages:
            if context.stopped:
                break
            result = await stage.process(context)
            if result is None:
                context.stop_propagation()
                break
        return context

    