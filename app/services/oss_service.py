import uuid
from functools import lru_cache

import oss2

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


def upload_banner_image(data: bytes) -> str:
    key = f"banners/{uuid.uuid4().hex}.jpg"
    _bucket().put_object(key, data, headers={"Content-Type": "image/jpeg"})
    return f"{settings.OSS_BASE_URL}/{key}"
