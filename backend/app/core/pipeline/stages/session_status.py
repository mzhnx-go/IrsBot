"""会话状态 Stage — 检查会话级启用/停用开关（Phase 12.1 决策表）."""

from app.core.pipeline.base import EventKey, PipelineContext, Stage


class SessionStatusStage(Stage):
    """会话被停用（Conversation.is_enabled=False）时拦截消息.

    前置条件：路由必须把 Conversation 对象放进 event_data[EventKey.CONVERSATION]。
    """

    async def process(self, context: PipelineContext) -> PipelineContext | None:
        conversation = context.event_data.get(EventKey.CONVERSATION)
        if conversation is not None and not conversation.is_enabled:
            context.stop_propagation()
            context.event_data[EventKey.ERROR] = "会话已停用"
        return context
