from fastapi import APIRouter, File, UploadFile

from app.api.deps import CurrentUser
from app.core.response import R
from app.schemas.vision import AnalyzePhotoData
from app.services.vision_service import analyze_photo_bytes

router = APIRouter(prefix="/vision", tags=["vision"])


@router.post("/analyze-photo", response_model=R[AnalyzePhotoData])
async def analyze_photo(
    _current: CurrentUser,
    file: UploadFile = File(..., description="图片文件"),
) -> R[AnalyzePhotoData]:
    """需要登录。返回饮食/运动/不确定识别草稿，不落库。"""
    raw = await file.read()
    ct = file.content_type or "image/jpeg"
    data = await analyze_photo_bytes(raw, ct)
    return R.ok(data)
