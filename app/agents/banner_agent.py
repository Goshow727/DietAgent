import json
import re

import httpx
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.diet_agent import _get_llm
from app.core.config import settings
from app.prompts import BANNER_CONTENT_SYSTEM, format_banner_content_prompt
from app.services.oss_service import upload_banner_image


def _strip_json(text: str) -> str:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    return m.group(1).strip() if m else text


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
    headers = {
        "Authorization": f"Bearer {settings.ARK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.ARK_IMAGE_MODEL,
        "prompt": image_prompt,
        "n": 1,
        "size": "1024x1024",
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(settings.ARK_IMAGE_URL, json=payload, headers=headers)
            resp.raise_for_status()
            image_url = resp.json()["data"][0]["url"]
            img_resp = await client.get(image_url, timeout=30.0)
            img_resp.raise_for_status()
            oss_url = upload_banner_image(img_resp.content)
            return oss_url
    except Exception:
        return None
