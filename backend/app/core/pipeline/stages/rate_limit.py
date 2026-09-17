"""频率限制 Stage — 滑动窗口限制单用户请求频率."""
import time
from collections import defaultdict, deque

from app.core.pipeline.base import EventKey
from app.core.config import settings
from app.core.pipeline.base import PipelineContext, Stage


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
