"""LangGraph ReAct Agent 状态图

将节点函数连接成图，定义 Agent 的执行流程：
START → inject_knowledge → inject_skills → invoke_llm → [条件路由]
                                                          ├─ "tools" → call_tools → invoke_llm (循环)
                                                          └─ "end" → END
"""
from langgraph.graph import END, StateGraph
from app.core.agent.nodes import (
    call_tools_node,
    inject_knowledge_node,
    inject_skills_node,
    invoke_llm_node,
    should_continue,
)
from app.core.agent.state import AgentState

def create_agent_graph() -> StateGraph:
    """创建 LangGraph ReAct Agent 状态图
    返回未编译的StateGraph， 调用者可以按需 complie()。
    分离创建和编译， 方便在编译前注入检查点等配置。
    Returns:
    StateGraph: 未编译的状态图
    """

    graph = StateGraph(AgentState)
    graph.add_node("inject_knowledge", inject_knowledge_node)
    graph.add_node("inject_skills", inject_skills_node)
    graph.add_node("invoke_llm", invoke_llm_node)
    graph.add_node("call_tools", call_tools_node)
    graph.add_edge("__start__", "inject_knowledge")
    graph.add_edge("inject_knowledge", "inject_skills")
    graph.add_edge("inject_skills", "invoke_llm")
    graph.add_conditional_edges(
        "invoke_llm",
        should_continue,
        {
            "tools": "call_tools",
            "end": END,
        },
    )

    graph.add_edge("call_tools", "invoke_llm")
    return graph

def create_compiled_agent_graph():
    """创建并编译 LangGraph ReAct Agent
    这是主要的入口函数， 返回编译后的可执行图。
    外部调用者（如 API路由）用这个函数获取Agent实例。
    Returns:
    CompliedGraph: 编译后的可执行图
    """
    graph = create_agent_graph()
    return graph.compile()