import asyncio
import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import HTTPException

from app.core.config import settings
from app.db.redis import get_redis_client

_NLS_TOKEN_KEY = "nls:token"


def _percent_encode(s: str) -> str:
    return urllib.parse.quote(str(s), safe="")


def _build_signature(access_key_secret: str, params: dict[str, str]) -> str:
    sorted_params = sorted(params.items())
    canonical = "&".join(
        f"{_percent_encode(k)}={_percent_encode(v)}" for k, v in sorted_params
    )
    string_to_sign = f"POST&{_percent_encode('/')}&{_percent_encode(canonical)}"
    key = (access_key_secret + "&").encode()
    digest = hmac.new(key, string_to_sign.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def _fetch_token_sync(access_key_id: str, access_key_secret: str) -> dict:
    params: dict[str, str] = {
        "Action": "CreateToken",
        "AccessKeyId": access_key_id,
        "Format": "JSON",
        "RegionId": "cn-shanghai",
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": str(uuid.uuid4()),
        "SignatureVersion": "1.0",
        "Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "Version": "2019-02-28",
    }
    params["Signature"] = _build_signature(access_key_secret, params)
    body = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(
        "https://nls-meta.cn-shanghai.aliyuncs.com/",
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        raise HTTPException(
            status_code=502,
            detail=f"NLS token request failed [{e.code}]: {body_text}",
        ) from e
    t = result["Token"]
    return {"token": t["Id"], "expire_time": t["ExpireTime"]}


async def create_nls_token() -> dict:
    redis = get_redis_client()
    cached = await redis.get(_NLS_TOKEN_KEY)
    if cached:
        data = json.loads(cached)
        if data["expire_time"] - time.time() > 3600:
            return data

    key_id = settings.NLS_ACCESS_KEY_ID or settings.OSS_ACCESS_KEY_ID
    key_secret = settings.NLS_ACCESS_KEY_SECRET or settings.OSS_ACCESS_KEY_SECRET
    result = await asyncio.to_thread(_fetch_token_sync, key_id, key_secret)

    ttl = int(result["expire_time"] - time.time() - 3600)
    if ttl > 0:
        await redis.set(_NLS_TOKEN_KEY, json.dumps(result), ex=ttl)

    return result


_NLS_ASR_URL = "https://nls-gateway.cn-shanghai.aliyuncs.com/stream/v1/asr"


async def recognize_audio_http(
    audio_bytes: bytes,
    fmt: str = "aac",
) -> str:
    """One-sentence recognition via Aliyun NLS HTTP API (≤60 s audio).

    Supported format strings: pcm, wav, opus, ogg, mp3, aac.
    For compressed formats (aac/mp3/opus) sample_rate is read from the file header —
    do NOT send sample_rate or it may conflict with what is in the container.
    """
    from loguru import logger

    token_info = await create_nls_token()
    params = {
        "appkey": settings.NLS_APP_KEY,
        "format": fmt,
        "enable_punctuation_prediction": "true",
        "enable_inverse_text_normalization": "true",
    }
    headers = {
        "X-NLS-Token": token_info["token"],
        "Content-Type": "application/octet-stream",
    }
    logger.info(
        f"recognize_audio_http: fmt={fmt} size={len(audio_bytes)}B "
        f"token_prefix={token_info['token'][:8]}"
    )
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _NLS_ASR_URL,
            params=params,
            headers=headers,
            content=audio_bytes,
            timeout=30,
        )
    result = resp.json()
    logger.info(
        f"recognize_audio_http: http={resp.status_code} "
        f"nls_status={result.get('status')} result='{result.get('result', '')}'"
    )
    if result.get("status") != 20000000:
        raise RuntimeError(
            f"NLS ASR [{result.get('status')}]: {result.get('message', 'unknown')}"
        )
    return result.get("result", "")
