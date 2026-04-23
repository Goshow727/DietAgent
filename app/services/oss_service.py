import uuid
from functools import lru_cache

import oss2
from loguru import logger

from app.core.config import settings


@lru_cache(maxsize=1)
def _bucket() -> oss2.Bucket:
    auth = oss2.Auth(settings.OSS_ACCESS_KEY_ID, settings.OSS_ACCESS_KEY_SECRET)
    return oss2.Bucket(auth, settings.OSS_ENDPOINT, settings.OSS_BUCKET)


def upload_avatar(data: bytes, content_type: str) -> str:
    ext = content_type.split("/")[-1]
    key = f"avatars/{uuid.uuid4().hex}.{ext}"
    _bucket().put_object(key, data, headers={"Content-Type": content_type})
    return f"{settings.OSS_BASE_URL}/{key}"


def upload_banner_image(data: bytes, content_type: str = "image/jpeg") -> str:
    ext = content_type.split("/")[-1]
    key = f"banners/{uuid.uuid4().hex}.{ext}"
    _bucket().put_object(key, data, headers={"Content-Type": content_type})
    return f"{settings.OSS_BASE_URL}/{key}"


def delete_banner_object_by_url(image_url: str | None) -> None:
    if not image_url or not image_url.strip():
        return
    base = settings.OSS_BASE_URL.rstrip("/")
    url = image_url.strip()
    prefix = base + "/"
    if not url.startswith(prefix):
        logger.warning("banner oss delete skip: url not under OSS_BASE_URL")
        return
    key = url[len(prefix) :]
    if not key:
        return
    try:
        _bucket().delete_object(key)
    except Exception:
        logger.exception("banner oss delete failed key={}", key[:120])
