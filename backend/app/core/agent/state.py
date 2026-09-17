"""
langGraph Agent 状态定义

定义在图的节点之间流动的状态数据。
每个节点可以读取和修改这些字段。
"""


from typing import Annotated, Any

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """LangGraph ReAct Agent的状态
    这个字典在图的每个节点之间传递，
    节点可以读取其中的数据，也可以更新它。
    
    """
    messages: Annotated[list[AnyMessage], add_messages]
    tools: list
    llm:Any
    knowledge_base: Any
    max_steps: int
    step_count: int
    conversation_id: str
    user_id: str

