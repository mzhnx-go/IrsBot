"""langGraph 节点函数
每个节点是图上的一个"站",接收AgentState, 返回部分更新。
LangGraph 按照图的定义， 自动在节点之间驱动执行。
"""

from langchain_core.messages import SystemMessage, ToolMessage
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.core.agent.state import AgentState
from app.core.agent.tools import ToolExecutor
from app.core.config import settings


async def inject_knowledge_node(state: AgentState) -> dict:
    """注入知识库检索结果到messages"""
    # TODO: Phase 7 实现后，在这里查询知识库，将结果作为 SystemMessage 注入
    # if state.get("knowledge_base"):
    #     retriever = state["knowledge_base"].get_retriever()
    #     docs = await retriever.ainvoke(state["messages"][-1].content)
    #     context = "\n\n".join([d.page_content for d in docs])
    #     return {"messages": [SystemMessage(content=f"[知识库上下文]\n{context}")]}
    return {}


async def inject_skills_node(state: AgentState) -> dict:
    """注入 Skill 清单提示词到 messages（渐进式披露第 1 步）

    从 SkillManager 获取所有可用技能的清单，
    作为 SystemMessage 注入，让 LLM 知道有哪些技能可用。
    """
    from app.core.skills.manager import SkillManager

    prompt = SkillManager.instance().build_skills_prompt()
    if prompt:
        return {"messages": [SystemMessage(content=prompt)]}
    return {}


async def invoke_llm_node(state: AgentState) -> dict:
    """调用 LLM 进行推理
    流程：
    1. 从 state中获取 LLM 实例和工具列表
    2.如果有工具,给LLM绑定工具(让LLM知道它可以调用哪些工具)
    3.调用LLM, 获取响应（空输出自动重试，指数退避最多 3 次）
    4.将响应追加到messages, 同时更新步数计数
    """
    llm = state["llm"]
    tools = state.get("tools", [])
    if tools:
        llm_with_tools = llm.bind_tools(tools)
    else:
        llm_with_tools = llm

    messages = state["messages"]
    response = await _invoke_with_retry(llm_with_tools, messages)

    return {
        "messages": [response],
        "step_count": state.get("step_count", 0),
    }


def _is_empty_response(response) -> bool:
    """判定响应是否为「空输出」：无文本也无工具调用."""
    return not getattr(response, "content", "") and not getattr(
        response, "tool_calls", None
    )


class _EmptyOutputError(Exception):
    """LLM 空输出信号，仅供 tenacity 识别重试."""


def _is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, _EmptyOutputError)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    retry=retry_if_exception(_is_retryable),
    reraise=True,
)
async def _invoke_with_retry(llm_with_tools, messages):
    """调用 LLM；空输出视为可重试异常，指数退避最多 3 次（Phase 12.5）."""
    response = await llm_with_tools.ainvoke(messages)
    if _is_empty_response(response):
        raise _EmptyOutputError("LLM 返回空输出（无文本且无工具调用）")
    return response


def should_continue(state: AgentState) -> str:
    """判断 Agent是否应该继续调用工具，还是结束

    返回值:
    "tools": LLM 请求了工具调用， 继续执行 call_tools 节点
    "end": LLM没有请求工具调用，对话结束

    """

    last_message = state["messages"][-1]

    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        step_count = state.get("step_count", 0)
        max_steps = state.get("max_steps", 30)
        if step_count >= max_steps:
            return "end"
        return "tools"
    return "end"


async def call_tools_node(state: AgentState) -> dict:
    """执行 LLM请求的工具调用
    流程:
    1. 获取LLM最后一条回复中的 tool_calls
    2. 遍历每个tool_call, 找到对应的工具并执行
    3. 将工具执行结果作为 ToolMessage 追加到 messages
    4. 步数 +1
    """
    last_message = state["messages"][-1]

    tool_calls = last_message.tool_calls

    all_tools = state.get("tools", [])
    tools_by_name = {t.name: t for t in all_tools}
    executor = ToolExecutor()
    result_messages = []
    for tool_call in tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool_id = tool_call["id"]
        tool_obj = tools_by_name.get(tool_name)
        if tool_obj is None:
            result_messages.append(
                ToolMessage(
                    content=f"错误：工具 '{tool_name}'不存在",
                    tool_call_id=tool_id,
                )
            )
        else:
            # 超时统一走 settings.TOOL_CALL_TIMEOUT（Phase 12.5）
            tool_result = await executor.execute(
                tool_obj, tool_args, timeout=settings.TOOL_CALL_TIMEOUT
            )
            result_messages.append(
                ToolMessage(
                    content=str(tool_result),
                    tool_call_id=tool_id,
                )
            )
    new_step_count = state.get("step_count", 0) + 1
    return {
        "messages": result_messages,
        "step_count": new_step_count,
    }
