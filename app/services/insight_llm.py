"""使用 Deepseek（OpenAI 兼容）生成洞察 JSON：desc + tags。"""

import json
import re

from openai import AsyncOpenAI
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from app.prompts.insight_summary import INSIGHT_SYSTEM_JSON


class _InsightTagItem(BaseModel):
    label: str = Field(min_length=1, max_length=32)
    tabTemp: int = Field(ge=0, le=2)

    @field_validator("label")
    @classmethod
    def strip_label(cls, v: str) -> str:
        return v.strip()


class _InsightLlmOut(BaseModel):
    desc: str = Field(min_length=1, max_length=32_000)
    tags: list[_InsightTagItem] = Field(default_factory=list, max_length=20)


def _strip_json_block(text: str) -> str:
    t = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", t)
    if m:
        return m.group(1).strip()
    return t


def _client() -> AsyncOpenAI:
    if not settings.DEEPSEEK_API_KEY:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY，请在 .env 中设置。")
    return AsyncOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
    )


async def generate_insight_desc_tags(user_content: str) -> tuple[str, list[dict]]:
    """
    调用 Deepseek，返回 (desc, tags) 其中 tags 为 [{"label", "tabTemp"}, ...]。
    """
    client = _client()
    resp = await client.chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": INSIGHT_SYSTEM_JSON},
            {"role": "user", "content": user_content},
        ],
        temperature=0.3,
    )
    raw = (resp.choices[0].message.content or "").strip()
    cleaned = _strip_json_block(raw)
    data = json.loads(cleaned)
    out = _InsightLlmOut.model_validate(data)
    tags = [t.model_dump() for t in out.tags]
    return out.desc, tags
