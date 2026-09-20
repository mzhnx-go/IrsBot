"""频率限制 Stage — 滑动窗口限制单用户请求频率."""

import time
from collections import defaultdict, deque

from app.core.config import settings
from app.core.pipeline.base import EventKey, PipelineContext, Stage


class RateLimitStage(Stage):
    """每用户每窗口最多允许 max_requests 次请求."""

    def __init__(
        self,
        max_requests: int | None = None,
        window_seconds: int | None = None,
    ):
        self.max_requests = (
            max_requests if max_requests is not None else settings.RATE_LIMIT_REQUESTS
        )
        self.window_seconds = (
            window_seconds if window_seconds is not None else settings.RATE_LIMIT_WINDOW
        )
        self._requests: dict[str, deque[float]] = defaultdict(deque)

    async def process(self, context: PipelineContext) -> PipelineContext | None:
        now = time.monotonic()
        key = str(context.user_id)
        window = self._requests[key]

        # 移除窗口外的旧时间戳
        while window and now - window[0] > self.window_seconds:
            window.popleft()

        if len(window) >= self.max_requests:
            context.stop_propagation()
            context.event_data[EventKey.RATE_LIMITED] = True
            return context

        window.append(now)
        return context


# 共享单例：限流计数必须跨请求累计才有意义。
# 若每次请求 new 一个实例（REST 路由旧做法），窗口永远是空的，限流形同虚设。
_shared_rate_limit_stage: RateLimitStage | None = None


def get_rate_limit_stage() -> RateLimitStage:
    """返回进程级共享的 RateLimitStage 实例（WS 与 REST 共用同一份计数）."""
    global _shared_rate_limit_stage
    if _shared_rate_limit_stage is None:
        _shared_rate_limit_stage = RateLimitStage()
    return _shared_rate_limit_stage
