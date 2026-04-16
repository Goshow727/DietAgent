from functools import lru_cache
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from app.core.config import settings

SYSTEM_PROMPT = (
    "你是一名专业的膳食营养顾问，回答要求："
    "1) 先简要分析用户需求；"
    "2) 给出可执行的饮食建议，注意营养均衡；"
    "3) 语言简洁友好，使用中文。"
)


class DietState(TypedDict):
    user_message: str
    intent: str
    reply: str


@lru_cache
def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.QWEN_MODEL,
        api_key=settings.DASHSCOPE_API_KEY,
        base_url=settings.DASHSCOPE_BASE_URL,
        temperature=0.3,
    )


async def _parse_intent(state: DietState) -> DietState:
    msg = state["user_message"].strip()
    if any(k in msg for k in ("减肥", "瘦", "控重", "低卡")):
        intent = "weight_loss"
    elif any(k in msg for k in ("增肌", "健身", "蛋白")):
        intent = "muscle_gain"
    else:
        intent = "general"
    return {**state, "intent": intent}


async def _generate_advice(state: DietState) -> DietState:
    llm = _get_llm()
    prompt = (
        f"用户意图标签: {state['intent']}\n"
        f"用户问题: {state['user_message']}\n"
        "请给出针对性的膳食建议。"
    )
    resp = await llm.ainvoke(
        [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]
    )
    return {**state, "reply": resp.content if isinstance(resp.content, str) else str(resp.content)}


@lru_cache
def _build_graph():
    graph = StateGraph(DietState)
    graph.add_node("parse_intent", _parse_intent)
    graph.add_node("generate_advice", _generate_advice)
    graph.set_entry_point("parse_intent")
    graph.add_edge("parse_intent", "generate_advice")
    graph.add_edge("generate_advice", END)
    return graph.compile()


async def run_diet_agent(user_message: str) -> str:
    app = _build_graph()
    initial: DietState = {"user_message": user_message, "intent": "", "reply": ""}
    final_state = await app.ainvoke(initial)
    return final_state["reply"]
