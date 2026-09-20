"""Agent 入口类 — 对外统一接口

封装 LangGraph 的状态图组装和调用逻辑。
外部调用者（API 路由）只需创建 Agent 实例并调用 run() 或 stream()。
"""

import uuid
from collections.abc import AsyncGenerator

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

# 触发 builtin 工具的注册（注册是导入 app.core.agent.builtins 的副作用，
# 其是否注册 shell/file_write 由 config 的 ENABLE_SHELL / ENABLE_FILE_WRITE 决定）。
import app.core.agent.builtins  # noqa: F401
from app.core.agent.builtins.kb_query import set_kb_user
from app.core.agent.graph import create_compiled_agent_graph
from app.core.agent.prompts import resolve_system_prompt
from app.core.agent.provider import ProviderManager
from app.core.agent.state import AgentState
from app.core.agent.tools import ToolRegistry
from app.core.config import settings
from app.core.db.sqlmodel_models import User
from app.core.pipeline.hooks import hook_bus


class Agent:
    """LangGraph ReAct Agent 入口类

    封装了以下逻辑：
    1. 从数据库获取 LLM 模型（ProviderManager）
    2. 获取可用工具列表（ToolRegistry）
    3. 组装初始 AgentState
    4. 调用编译后的 LangGraph 图
    5. 返回结果

    用法：
        agent = Agent(session=db_session)
        result = await agent.run("北京天气怎么样")
    """

    def __init__(
        self,
        session: Session,
        provider_id: uuid.UUID | None = None,
        model_name: str | None = None,
        temperature: float = 0.0,
        conversation_id: str | None = None,
        user_id: str | None = None,
    ):
        """初始化 Agent

        Args:
            session: SQLAlchemy 数据库会话
            provider_id: 指定 Provider ID，None 则用默认
            model_name: 指定模型名称，None 则用 Provider 配置的默认模型
            temperature: LLM 温度参数，越高越随机
            conversation_id: 对话 ID，用于消息持久化
            user_id: 用户 ID，用于权限隔离
        """
        self.session = session
        self.provider_id = provider_id
        self.model_name = model_name
        self.temperature = temperature
        self.conversation_id = conversation_id or str(uuid.uuid4())
        self.user_id = user_id or ""

        # 解析 user_id（str → UUID），供系统提示词查询与 Provider 归属过滤共用。
        # 非法/缺失 UUID 视为「无身份」：提示词退回默认，Provider 解析 fail closed。
        user_uuid: uuid.UUID | None = None
        if self.user_id:
            try:
                user_uuid = uuid.UUID(self.user_id)
            except ValueError:
                user_uuid = None

        # 存为实例属性：run/stream 每次运行前要把它挂到 ContextVar 上
        self.user_uuid = user_uuid
        # 读取当前用户的自定义系统提示词（未设置/为空时 resolve 回落默认）。
        # 用已有 session + user_id 查库，WS 路由与 Pipeline 两条链路都无需改动。
        self.system_prompt: str | None = None
        if user_uuid is not None:
            try:
                user = session.get(User, user_uuid)
                if user is not None:
                    self.system_prompt = user.system_prompt
            except SQLAlchemyError:
                # 查询失败：退回默认提示词，不阻断会话
                self.system_prompt = None

        # 创建 LLM 模型实例。
        # ⚠️ 必须传 user_id：Provider 解析按归属过滤，否则会取到别人的默认源。
        provider_mgr = ProviderManager(session)
        self.llm = provider_mgr.get_chat_model(
            user_id=user_uuid,
            provider_id=provider_id,
            model_name=model_name,
            temperature=temperature,
        )

        # 获取所有注册的工具
        self.tools = ToolRegistry.instance().get_all_tools()

        # 编译图
        self.graph = create_compiled_agent_graph()

    def _build_initial_state(self, messages: list) -> AgentState:
        """组装初始 AgentState

        Args:
            messages: 对话消息列表（已有历史 + 新消息）

        Returns:
            完整的 AgentState 字典，传给 LangGraph 图
        """
        return {
            "messages": messages,
            "tools": self.tools,
            "llm": self.llm,
            "knowledge_base": None,  # Phase 7 填充
            "max_steps": settings.MAX_AGENT_STEPS,
            "step_count": 0,
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
        }

    async def run(self, user_message: str, history: list | None = None) -> dict:
        """运行 Agent（非流式）

        等图全部跑完，返回最终结果。

        Args:
            user_message: 用户输入的消息文本
            history: 历史消息列表（可选），用于多轮对话

        Returns:
            最终的 AgentState 字典
        """
        # 把当前用户身份挂到任务上下文，供 kb_query 等工具在任意深度读取
        set_kb_user(self.user_uuid)

        # 组装消息列表：系统提示词（最前）+ 历史消息 + 新用户消息
        messages: list = [
            SystemMessage(content=resolve_system_prompt(self.system_prompt))
        ]
        messages.extend(history or [])
        messages.append(HumanMessage(content=user_message))

        # 组装初始状态
        initial_state = self._build_initial_state(messages)

        # 内部钩子：LLM 调用前（Phase 12.4）
        await hook_bus.emit("on_llm_request", messages=messages)

        # 调用图，获取最终状态
        result = await self.graph.ainvoke(initial_state)

        await hook_bus.emit("on_llm_response", response=result)
        await hook_bus.emit("on_agent_done", result=result)
        return result

    async def stream(
        self, user_message: str, history: list | None = None
    ) -> AsyncGenerator:
        """运行 Agent（流式）

        边跑边产出事件，用于 WebSocket 实时推送。

        Args:
            user_message: 用户输入的消息文本
            history: 历史消息列表（可选）

        Yields:
            LangGraph 的 astream_events 事件字典
        """
        # 把当前用户身份挂到任务上下文，供 kb_query 等工具在任意深度读取
        set_kb_user(self.user_uuid)

        # 组装消息列表：系统提示词（最前）+ 历史消息 + 新用户消息
        messages: list = [
            SystemMessage(content=resolve_system_prompt(self.system_prompt))
        ]
        messages.extend(history or [])
        messages.append(HumanMessage(content=user_message))

        initial_state = self._build_initial_state(messages)

        # 内部钩子：LLM 调用前（Phase 12.4）
        await hook_bus.emit("on_llm_request", messages=messages)

        # 流式调用图
        async for event in self.graph.astream_events(initial_state, version="v2"):
            yield event

        # 流式没有一次性 result，只在结束点发 on_agent_done
        await hook_bus.emit("on_agent_done", result=None)
