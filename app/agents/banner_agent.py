import json
import re

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from loguru import logger

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


def _ark_image_size(size: str) -> str:
    """Ark v3 Seedream 部分模型对 size=1K 返回 400，低清改用合法像素规格。"""
    s = (size or "").strip()
    if s.upper() == "1K":
        return "1024x1024"
    return s


def _image_content_type(img_resp: httpx.Response) -> str:
    ct = (img_resp.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ct.startswith("image/"):
        return ct
    return "image/png"


def _get_llm_for_banner(*, enable_search: bool) -> ChatOpenAI:
    if enable_search:
        return ChatOpenAI(
            model=settings.QWEN_MODEL,
            api_key=settings.DASHSCOPE_API_KEY,
            base_url=settings.DASHSCOPE_BASE_URL,
            temperature=0.2,
            extra_body={"enable_search": True},
        )
    return ChatOpenAI(
        model=settings.QWEN_MODEL,
        api_key=settings.DASHSCOPE_API_KEY,
        base_url=settings.DASHSCOPE_BASE_URL,
        temperature=0.2,
    )


async def generate_card_drafts(
    guideline_chunks: list[str],
    user_body_block: str,
    intake_summary: str,
    burn_summary: str,
    red_cut_titles: list[str],
    count: int,
    user_id: int | None = None,
) -> list[dict]:
    prompt = format_banner_content_prompt(
        guideline_chunks=guideline_chunks,
        user_body_block=user_body_block,
        intake_summary=intake_summary,
        burn_summary=burn_summary,
        red_cut_titles=red_cut_titles,
        count=count,
    )
    messages = [
        SystemMessage(content=BANNER_CONTENT_SYSTEM),
        HumanMessage(content=prompt),
    ]
    use_net = bool(settings.BANNER_ENABLE_NETWORK_SEARCH)
    if use_net:
        try:
            llm = _get_llm_for_banner(enable_search=True)
            resp = await llm.ainvoke(messages)
        except Exception as e:
            logger.warning(
                "banner: card draft with enable_search failed user_id={} err={!r}",
                user_id,
                e,
            )
            llm = _get_llm_for_banner(enable_search=False)
            resp = await llm.ainvoke(messages)
    else:
        llm = _get_llm_for_banner(enable_search=False)
        resp = await llm.ainvoke(messages)
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
    # Seedream 4 文档常不支持 output_format；需 response_format / sequential_image_generation 等字段
    payload = {
        "model": settings.ARK_IMAGE_MODEL,
        "prompt": image_prompt,
        "size": _ark_image_size(settings.ARK_IMAGE_SIZE),
        "sequential_image_generation": "disabled",
        "stream": False,
        "response_format": "url",
        "watermark": False,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(settings.ARK_IMAGE_URL, json=payload, headers=headers)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            body = (e.response.text or "")[:800]
            logger.exception(
                "banner_image:ark_request HTTP status={} body_snippet={!r} prompt_snippet={!r}",
                e.response.status_code,
                body,
                snippet,
            )
            return None
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
            ct = _image_content_type(img_resp)
            return upload_banner_image(img_resp.content, content_type=ct)
        except Exception:
            logger.exception(
                "banner_image:oss_upload failed bucket={} endpoint={} prompt_snippet={!r}",
                settings.OSS_BUCKET,
                settings.OSS_ENDPOINT,
                snippet,
            )
            return None
