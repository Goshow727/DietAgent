from fastapi import APIRouter, File, UploadFile
from loguru import logger

from app.api.deps import CurrentUser
from app.core.response import R
from app.services.nls_service import create_nls_token, recognize_audio_http

router = APIRouter(prefix="/nls", tags=["nls"])

_MIN_AUDIO_BYTES = 1000


@router.get("/token")
async def get_nls_token(_: CurrentUser) -> R:
    token_info = await create_nls_token()
    return R.ok(token_info)


@router.post("/recognize")
async def recognize(_: CurrentUser, audio: UploadFile = File(...)) -> R:
    audio_bytes = await audio.read()
    logger.info(
        f"POST /nls/recognize: {len(audio_bytes)} bytes "
        f"filename={audio.filename} content_type={audio.content_type}"
    )
    if len(audio_bytes) < _MIN_AUDIO_BYTES:
        logger.warning("recognize: audio too short, returning empty")
        return R.ok({"text": ""})
    text = await recognize_audio_http(audio_bytes)
    logger.info(f"POST /nls/recognize: result='{text}'")
    return R.ok({"text": text})
