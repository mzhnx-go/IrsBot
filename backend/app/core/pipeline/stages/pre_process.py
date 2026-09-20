from app.core.config import settings
from app.core.pipeline.base import EventKey, PipelineContext, Stage


class PreProcessStage(Stage):
    """清洗用户消息：去空白、空消息拒绝、超长截断."""

    def __init__(self, max_len: int | None = None):
        self.max_len = (
            max_len if max_len is not None else settings.MAX_USER_MESSAGE_LENGTH
        )

    async def process(self, context: PipelineContext) -> PipelineContext | None:
        text = str(context.event_data.get(EventKey.USER_MESSAGE, ""))
        text = text.strip()
        if not text:
            context.stop_propagation()
            context.event_data[EventKey.ERROR] = "用户消息为空"
            return context
        if len(text) > self.max_len:
            text = text[: self.max_len]
        context.event_data[EventKey.USER_MESSAGE] = text
        return context
