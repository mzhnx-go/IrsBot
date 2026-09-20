"""后处理 Stage — 将 Agent 运行记录写入数据库."""

from app.core.db.models import AgentRun
from app.core.pipeline.base import EventKey, PipelineContext, Stage


class PostProcessStage(Stage):
    """记录 AgentRun：把一次运行持久化到 agent_runs 表."""

    async def process(self, context: PipelineContext) -> PipelineContext | None:
        session = context.event_data[EventKey.SESSION]
        result = context.event_data[EventKey.AGENT_RESULT]
        user_message = context.event_data[EventKey.USER_MESSAGE]

        run = AgentRun(
            user_id=context.user_id,
            conversation_id=context.conversation_id,
            input_text=user_message,
            output_text=result["messages"][-1].content,
            status="completed",
            tool_calls_made=result.get("step_count", 0),
        )
        session.add(run)
        session.commit()
        return context
