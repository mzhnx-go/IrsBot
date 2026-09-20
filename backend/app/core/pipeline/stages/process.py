"""核心处理 Stage — 调用 Agent 生成回复."""

from app.core.agent.agent import Agent
from app.core.pipeline.base import EventKey, PipelineContext, Stage


class ProcessStage(Stage):
    """调用 Agent 处理用户消息，结果存入 event_data['agent_result']."""

    async def process(self, context: PipelineContext) -> PipelineContext | None:
        session = context.event_data[EventKey.SESSION]
        user_message = context.event_data[EventKey.USER_MESSAGE]
        history = context.event_data.get(EventKey.HISTORY, [])

        agent = Agent(
            session=session,
            user_id=str(context.user_id),
            conversation_id=str(context.conversation_id)
            if context.conversation_id
            else None,
        )

        context.event_data[EventKey.AGENT_RESULT] = await agent.run(
            user_message, history=history
        )
        return context
