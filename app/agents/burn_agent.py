import json
import re

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.prompts.burn_extraction import BURN_CHAT_EXTRACTION_PROMPT
from app.schemas.burn_extraction import (
    BurnChatExtraction,
    BurnFlow,
    BurnMetricSource,
)


def _strip_json_block(text: str) -> str:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        return m.group(1).strip()
    return text


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.QWEN_MODEL,
        api_key=settings.DASHSCOPE_API_KEY,
        base_url=settings.DASHSCOPE_BASE_URL,
        temperature=0.2,
    )


def parse_burn_extraction_json(raw: str) -> BurnChatExtraction:
    cleaned = _strip_json_block(raw)
    return BurnChatExtraction.model_validate(json.loads(cleaned))


async def extract_burn_chat(context_for_model: str, user_body_block: str) -> BurnChatExtraction:
    body = user_body_block.strip() or "（未填写，请按常识保守估计。）"
    prompt = BURN_CHAT_EXTRACTION_PROMPT.replace(
        "【用户身体信息】\n\n【用户消息】\n",
        f"【用户身体信息】\n{body}\n\n【用户消息】\n",
    )
    llm = _get_llm()
    resp = await llm.ainvoke([HumanMessage(content=prompt + context_for_model)])
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    return parse_burn_extraction_json(content)


def normalize_burn_extraction(extraction: BurnChatExtraction) -> BurnChatExtraction:
    if extraction.flow != BurnFlow.burn_ready:
        return extraction
    if not extraction.items:
        return BurnChatExtraction(
            flow=BurnFlow.need_clarify,
            items=[],
            clarify_message=extraction.clarify_message or "请说明做了什么运动、大概多久、强度如何？",
        )
    for it in extraction.items:
        if (
            it.duration_source == BurnMetricSource.unknown
            or it.kcal_source == BurnMetricSource.unknown
            or it.duration_minutes is None
            or it.duration_minutes <= 0
            or it.kcal is None
            or it.kcal <= 0
        ):
            return BurnChatExtraction(
                flow=BurnFlow.need_clarify,
                items=[],
                clarify_message=extraction.clarify_message
                or "请补充运动时长或消耗热量，以便准确记录。",
            )
    return extraction
