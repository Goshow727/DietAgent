import json
import re

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from app.agents.diet_agent import _get_llm
from app.core.config import settings
from app.prompts import BANNER_CONTENT_SYSTEM, format_banner_content_prompt
from app.services.oss_service import upload_banner_image


def _strip_json(text: str) -> str:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    return m.group(1).strip() if m else text


def _prompt_snippet(image_prompt: str, max_len: int = 80) -> str:
    s = (image_prompt or "").strip()
    if len(s) <= max_len:
        return s
    return s[:max_len] + "…"


def _url_snippet(url: str, max_len: int = 100) -> str:
    s = url or ""
    if len(s) <= max_len:
        return s
    return s[:max_len] + "…"


async def generate_card_drafts(
    guideline_chunks: list[str],
    user_body_block: str,
    intake_summary: str,
    burn_summary: str,
    red_cut_titles: list[str],
    count: int,
) -> list[dict]:
    prompt = format_banner_content_prompt(
        guideline_chunks=guideline_chunks,
        user_body_block=user_body_block,
        intake_summary=intake_summary,
        burn_summary=burn_summary,
        red_cut_titles=red_cut_titles,
        count=count,
    )
    llm = _get_llm()
    resp = await llm.ainvoke(
        [SystemMessage(content=BANNER_CONTENT_SYSTEM), HumanMessage(content=prompt)]
    )
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    data = json.loads(_strip_json(content))
    if not isinstance(data, list):
        data = [data]
    return data[:count]


async def generate_image_and_upload(image_prompt: str) -> str | None:
    snippet = _prompt_snippet(image_prompt)
    headers = {
        "Authorization": f"Bearer {settings.ARK_API_KEY}",
        "Content-Type": "application/json",
    }
    # 与火山 Ark Seedream 图像 API 示例一致（非 DALL·E 的 n + 1024x1024 形态）
    payload = {
        "model": settings.ARK_IMAGE_MODEL,
        "prompt": image_prompt,
        "size": settings.ARK_IMAGE_SIZE,
        "output_format": "png",
        "watermark": False,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(settings.ARK_IMAGE_URL, json=payload, headers=headers)
            resp.raise_for_status()
        except Exception:
            logger.exception("banner_image:ark_request failed prompt_snippet={!r}", snippet)
            return None
        try:
            data = resp.json()
            image_url = data["data"][0]["url"]
        except (KeyError, IndexError, TypeError, ValueError):
            logger.exception("banner_image:ark_request invalid response prompt_snippet={!r}", snippet)
            return None
        try:
            img_resp = await client.get(image_url, timeout=30.0)
            img_resp.raise_for_status()
        except Exception:
            logger.exception(
                "banner_image:image_fetch failed url={!r} prompt_snippet={!r}",
                _url_snippet(image_url),
                snippet,
            )
            return None
        try:
            return upload_banner_image(img_resp.content, content_type="image/png")
        except Exception:
            logger.exception(
                "banner_image:oss_upload failed bucket={} endpoint={} prompt_snippet={!r}",
                settings.OSS_BUCKET,
                settings.OSS_ENDPOINT,
                snippet,
            )
            return None
