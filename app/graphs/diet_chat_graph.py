from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.graphs.diet_chat_state import DietChatState


async def _noop_node(state: DietChatState) -> dict[str, str]:
    return {"reply": "ok"}


def build_diet_chat_graph() -> StateGraph:
    g: StateGraph = StateGraph(DietChatState)
    g.add_node("noop", _noop_node)
    g.add_edge(START, "noop")
    g.add_edge("noop", END)
    return g


def compile_diet_chat_graph_checkpointer_memory():
    """编译图并挂载内存 checkpointer（单测 / 本地）。"""
    return build_diet_chat_graph().compile(checkpointer=MemorySaver())
