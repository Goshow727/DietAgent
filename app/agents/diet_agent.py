import json
import re
from functools import lru_cache

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.prompts import (
    BODY_METRICS_EXTRACTION_PROMPT,
    CHAT_INTENT_ROUTER_PROMPT,
    DIET_ADVISOR_SYSTEM_PROMPT,
    INTAKE_CHAT_EXTRACTION_PROMPT,
    PREFERENCE_EXTRACTION_PROMPT,
    format_general_advice_user_message,
)
from app.schemas.body_patch import BodyMetricsExtraction
from app.schemas.chat_intent import ChatIntentRoute
from app.schemas.intake_extraction import (
    AmountSource,
    ChatFlow,
    IntakeChatExtraction,
)
from app.schemas.preference_extraction import PreferenceExtraction


def _strip_json_block(text: str) -> str:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        return m.group(1).strip()
    return text


@lru_cache
def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.QWEN_MODEL,
        api_key=settings.DASHSCOPE_API_KEY,
        base_url=settings.DASHSCOPE_BASE_URL,
        temperature=0.2,
    )


def parse_intent_route_json(raw: str) -> ChatIntentRoute:
    cleaned = _strip_json_block(raw)
    return ChatIntentRoute.model_validate(json.loads(cleaned))


def parse_extraction_json(raw: str) -> IntakeChatExtraction:
    cleaned = _strip_json_block(raw)
    data = json.loads(cleaned)
    return IntakeChatExtraction.model_validate(data)


def parse_body_metrics_json(raw: str) -> BodyMetricsExtraction:
    cleaned = _strip_json_block(raw)
    return BodyMetricsExtraction.model_validate(json.loads(cleaned))


def parse_preference_json(raw: str) -> PreferenceExtraction:
    cleaned = _strip_json_block(raw)
    return PreferenceExtraction.model_validate(json.loads(cleaned))


async def route_chat_intent(context_for_model: str) -> ChatIntentRoute:
    """第一层：仅意图分类，不抽取食物。"""
    llm = _get_llm()
    resp = await llm.ainvoke(
        [HumanMessage(content=CHAT_INTENT_ROUTER_PROMPT + context_for_model)]
    )
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    return parse_intent_route_json(content)


async def extract_intake_chat(
    context_for_model: str, user_body_block: str = ""
) -> IntakeChatExtraction:
    """第二层：摄入槽位（须在 route 为 log_intake 后调用）。"""
    body = user_body_block.strip() or "（未填写，请按常识保守估计份量。）"
    prompt = INTAKE_CHAT_EXTRACTION_PROMPT.replace(
        "【用户身体信息】\n\n【用户消息】\n",
        f"【用户身体信息】\n{body}\n\n【用户消息】\n",
    )
    llm = _get_llm()
    resp = await llm.ainvoke([HumanMessage(content=prompt + context_for_model)])
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    return parse_extraction_json(content)


async def extract_body_metrics_chat(
    context_for_model: str, user_body_block: str = ""
) -> BodyMetricsExtraction:
    body = user_body_block.strip() or "（未填写。）"
    prompt = BODY_METRICS_EXTRACTION_PROMPT.replace(
        "【用户身体信息】\n\n【用户消息】\n",
        f"【用户身体信息】\n{body}\n\n【用户消息】\n",
    )
    llm = _get_llm()
    resp = await llm.ainvoke([HumanMessage(content=prompt + context_for_model)])
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    return parse_body_metrics_json(content)


async def extract_preferences_chat(
    context_for_model: str, user_body_block: str = ""
) -> PreferenceExtraction:
    body = user_body_block.strip() or "（未填写。）"
    prompt = PREFERENCE_EXTRACTION_PROMPT.replace(
        "【用户身体信息】\n\n【用户消息】\n",
        f"【用户身体信息】\n{body}\n\n【用户消息】\n",
    )
    llm = _get_llm()
    resp = await llm.ainvoke([HumanMessage(content=prompt + context_for_model)])
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    return parse_preference_json(content)


async def generate_general_advice(user_message: str) -> str:
    llm = _get_llm()
    resp = await llm.ainvoke(
        [
            SystemMessage(content=DIET_ADVISOR_SYSTEM_PROMPT),
            HumanMessage(content=format_general_advice_user_message(user_message)),
        ]
    )
    return resp.content if isinstance(resp.content, str) else str(resp.content)


def normalize_extraction(extraction: IntakeChatExtraction) -> IntakeChatExtraction:
    """将模型输出收紧为安全状态：intake_ready 必须每条有正数克重且非 unknown。"""
    if extraction.flow != ChatFlow.intake_ready:
        return extraction

    foods = extraction.foods
    if not foods:
        return IntakeChatExtraction(
            flow=ChatFlow.need_clarify,
            foods=[],
            clarify_message=extraction.clarify_message
            or "请说明具体吃了什么食物，大概多少？",
        )

    for item in foods:
        if item.amount_source == AmountSource.unknown or item.amount_g is None or item.amount_g <= 0:
            return IntakeChatExtraction(
                flow=ChatFlow.need_clarify,
                foods=[],
                clarify_message=extraction.clarify_message
                or "请补充每种食物大概吃了多少克，或用碗/个等方式描述。",
            )

    return extraction
