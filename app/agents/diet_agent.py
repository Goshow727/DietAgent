import json
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
    intent: str    # "add_log" | "general"
    food_name: str
    amount_g: float
    reply: str


@lru_cache
def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.QWEN_MODEL,
        api_key=settings.DASHSCOPE_API_KEY,
        base_url=settings.DASHSCOPE_BASE_URL,
        temperature=0.3,
    )


async def _classify_intent(state: DietState) -> DietState:
    llm = _get_llm()
    prompt = (
        "判断用户意图，只返回JSON，不要其他内容。\n"
        f"用户消息：{state['user_message']}\n"
        '返回格式：{"intent": "add_log"} 或 {"intent": "general"}\n'
        "add_log: user says they ate something (e.g. wo chile..., gang chi wan...)\n"
        "general: everything else (asking for advice, nutrition questions, etc.)"
    )
    resp = await llm.ainvoke([HumanMessage(content=prompt)])
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    try:
        data = json.loads(content.strip())
        intent = data.get("intent", "general")
    except Exception:
        intent = "general"
    return {**state, "intent": intent}


async def _parse_food(state: DietState) -> DietState:
    llm = _get_llm()
    prompt = (
        "从用户消息中提取食物名称和重量，只返回JSON，不要其他内容。\n"
        f"用户消息：{state['user_message']}\n"
        '返回格式：{"food_name": "食物名称", "amount_g": 重量数字}\n'
        "如果消息未提及重量，amount_g默认为200。"
    )
    resp = await llm.ainvoke([HumanMessage(content=prompt)])
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    try:
        data = json.loads(content.strip())
        food_name = str(data.get("food_name", ""))
        amount_g = float(data.get("amount_g", 200))
    except Exception:
        food_name = state["user_message"]
        amount_g = 200.0
    return {**state, "food_name": food_name, "amount_g": amount_g}


async def _generate_advice(state: DietState) -> DietState:
    llm = _get_llm()
    prompt = f"用户问题: {state['user_message']}\n请给出针对性的膳食建议。"
    resp = await llm.ainvoke(
        [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]
    )
    return {**state, "reply": resp.content if isinstance(resp.content, str) else str(resp.content)}


def _route_after_classify(state: DietState) -> str:
    return "parse_food" if state["intent"] == "add_log" else "generate_advice"


@lru_cache
def _build_graph():
    graph = StateGraph(DietState)
    graph.add_node("classify_intent", _classify_intent)
    graph.add_node("parse_food", _parse_food)
    graph.add_node("generate_advice", _generate_advice)
    graph.set_entry_point("classify_intent")
    graph.add_conditional_edges("classify_intent", _route_after_classify)
    graph.add_edge("parse_food", END)
    graph.add_edge("generate_advice", END)
    return graph.compile()


async def run_diet_agent(user_message: str) -> DietState:
    app = _build_graph()
    initial: DietState = {
        "user_message": user_message,
        "intent": "",
        "food_name": "",
        "amount_g": 0.0,
        "reply": "",
    }
    return await app.ainvoke(initial)
