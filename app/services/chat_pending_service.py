import json
from typing import Any

from loguru import logger

from app.db.redis import get_redis_client
from app.schemas.body_patch import BodyMetricsPatch
from app.schemas.burn_draft import BurnConfirmDraft
from app.schemas.intake_draft import IntakeConfirmDraft
from app.schemas.preference_extraction import PreferenceConfirmDraft

_PENDING_PREFIX = "intake_chat:pending"
_CONFIRM_PREFIX = "intake_chat:confirm"
_BURN_PENDING_PREFIX = "burn_chat:pending"
_BURN_CONFIRM_PREFIX = "burn_chat:confirm"
_BODY_CONFIRM_PREFIX = "body_chat:confirm"
_PREF_CONFIRM_PREFIX = "pref_chat:confirm"
_DEFAULT_TTL_SEC = 1800


def _sid(session_id: str | None) -> str:
    return (session_id or "default").strip() or "default"


def _key(user_id: int, session_id: str | None) -> str:
    return f"{_PENDING_PREFIX}:{user_id}:{_sid(session_id)}"


def _confirm_key(user_id: int, session_id: str | None) -> str:
    return f"{_CONFIRM_PREFIX}:{user_id}:{_sid(session_id)}"


def _burn_pending_key(user_id: int, session_id: str | None) -> str:
    return f"{_BURN_PENDING_PREFIX}:{user_id}:{_sid(session_id)}"


def _burn_confirm_key(user_id: int, session_id: str | None) -> str:
    return f"{_BURN_CONFIRM_PREFIX}:{user_id}:{_sid(session_id)}"


def _body_confirm_key(user_id: int, session_id: str | None) -> str:
    return f"{_BODY_CONFIRM_PREFIX}:{user_id}:{_sid(session_id)}"


def _pref_confirm_key(user_id: int, session_id: str | None) -> str:
    return f"{_PREF_CONFIRM_PREFIX}:{user_id}:{_sid(session_id)}"


async def get_pending_context(user_id: int, session_id: str | None = None) -> str | None:
    try:
        r = get_redis_client()
        raw = await r.get(_key(user_id, session_id))
        if not raw:
            return None
        data = json.loads(raw)
        return data.get("context") if isinstance(data, dict) else None
    except Exception as e:
        logger.warning(f"get_pending_context failed: {e}")
        return None


async def set_pending_context(
    user_id: int,
    context: str,
    session_id: str | None = None,
    extra: dict[str, Any] | None = None,
    ttl_sec: int = _DEFAULT_TTL_SEC,
) -> None:
    try:
        r = get_redis_client()
        payload: dict[str, Any] = {"context": context}
        if extra:
            payload.update(extra)
        await r.setex(_key(user_id, session_id), ttl_sec, json.dumps(payload, ensure_ascii=False))
    except Exception as e:
        logger.warning(f"set_pending_context failed: {e}")


async def clear_pending(user_id: int, session_id: str | None = None) -> None:
    try:
        r = get_redis_client()
        await r.delete(_key(user_id, session_id))
    except Exception as e:
        logger.warning(f"clear_pending failed: {e}")


async def get_confirm_draft(
    user_id: int, session_id: str | None = None
) -> IntakeConfirmDraft | None:
    try:
        r = get_redis_client()
        raw = await r.get(_confirm_key(user_id, session_id))
        if not raw:
            return None
        return IntakeConfirmDraft.model_validate_json(raw)
    except Exception as e:
        logger.warning(f"get_confirm_draft failed: {e}")
        return None


async def set_confirm_draft(
    user_id: int,
    draft: IntakeConfirmDraft,
    session_id: str | None = None,
    ttl_sec: int = _DEFAULT_TTL_SEC,
) -> None:
    try:
        r = get_redis_client()
        await r.setex(
            _confirm_key(user_id, session_id),
            ttl_sec,
            draft.model_dump_json(),
        )
    except Exception as e:
        logger.warning(f"set_confirm_draft failed: {e}")


async def clear_confirm_draft(user_id: int, session_id: str | None = None) -> None:
    try:
        r = get_redis_client()
        await r.delete(_confirm_key(user_id, session_id))
    except Exception as e:
        logger.warning(f"clear_confirm_draft failed: {e}")


async def get_burn_pending_context(user_id: int, session_id: str | None = None) -> str | None:
    try:
        r = get_redis_client()
        raw = await r.get(_burn_pending_key(user_id, session_id))
        if not raw:
            return None
        data = json.loads(raw)
        return data.get("context") if isinstance(data, dict) else None
    except Exception as e:
        logger.warning(f"get_burn_pending_context failed: {e}")
        return None


async def set_burn_pending_context(
    user_id: int,
    context: str,
    session_id: str | None = None,
    ttl_sec: int = _DEFAULT_TTL_SEC,
) -> None:
    try:
        r = get_redis_client()
        await r.setex(
            _burn_pending_key(user_id, session_id),
            ttl_sec,
            json.dumps({"context": context}, ensure_ascii=False),
        )
    except Exception as e:
        logger.warning(f"set_burn_pending_context failed: {e}")


async def clear_burn_pending(user_id: int, session_id: str | None = None) -> None:
    try:
        r = get_redis_client()
        await r.delete(_burn_pending_key(user_id, session_id))
    except Exception as e:
        logger.warning(f"clear_burn_pending failed: {e}")


async def get_burn_confirm_draft(
    user_id: int, session_id: str | None = None
) -> BurnConfirmDraft | None:
    try:
        r = get_redis_client()
        raw = await r.get(_burn_confirm_key(user_id, session_id))
        if not raw:
            return None
        return BurnConfirmDraft.model_validate_json(raw)
    except Exception as e:
        logger.warning(f"get_burn_confirm_draft failed: {e}")
        return None


async def set_burn_confirm_draft(
    user_id: int,
    draft: BurnConfirmDraft,
    session_id: str | None = None,
    ttl_sec: int = _DEFAULT_TTL_SEC,
) -> None:
    try:
        r = get_redis_client()
        await r.setex(
            _burn_confirm_key(user_id, session_id),
            ttl_sec,
            draft.model_dump_json(),
        )
    except Exception as e:
        logger.warning(f"set_burn_confirm_draft failed: {e}")


async def clear_burn_confirm_draft(user_id: int, session_id: str | None = None) -> None:
    try:
        r = get_redis_client()
        await r.delete(_burn_confirm_key(user_id, session_id))
    except Exception as e:
        logger.warning(f"clear_burn_confirm_draft failed: {e}")


async def clear_all_chat_state(user_id: int, session_id: str | None = None) -> None:
    await clear_pending(user_id, session_id)
    await clear_confirm_draft(user_id, session_id)
    await clear_burn_pending(user_id, session_id)
    await clear_burn_confirm_draft(user_id, session_id)
    await clear_body_confirm_patch(user_id, session_id)
    await clear_preference_confirm_draft(user_id, session_id)


async def get_body_confirm_patch(
    user_id: int, session_id: str | None = None
) -> BodyMetricsPatch | None:
    try:
        r = get_redis_client()
        raw = await r.get(_body_confirm_key(user_id, session_id))
        if not raw:
            return None
        return BodyMetricsPatch.model_validate_json(raw)
    except Exception as e:
        logger.warning(f"get_body_confirm_patch failed: {e}")
        return None


async def set_body_confirm_patch(
    user_id: int,
    patch: BodyMetricsPatch,
    session_id: str | None = None,
    ttl_sec: int = _DEFAULT_TTL_SEC,
) -> None:
    try:
        r = get_redis_client()
        await r.setex(
            _body_confirm_key(user_id, session_id),
            ttl_sec,
            patch.model_dump_json(),
        )
    except Exception as e:
        logger.warning(f"set_body_confirm_patch failed: {e}")


async def clear_body_confirm_patch(user_id: int, session_id: str | None = None) -> None:
    try:
        r = get_redis_client()
        await r.delete(_body_confirm_key(user_id, session_id))
    except Exception as e:
        logger.warning(f"clear_body_confirm_patch failed: {e}")


async def get_preference_confirm_draft(
    user_id: int, session_id: str | None = None
) -> PreferenceConfirmDraft | None:
    try:
        r = get_redis_client()
        raw = await r.get(_pref_confirm_key(user_id, session_id))
        if not raw:
            return None
        return PreferenceConfirmDraft.model_validate_json(raw)
    except Exception as e:
        logger.warning(f"get_preference_confirm_draft failed: {e}")
        return None


async def set_preference_confirm_draft(
    user_id: int,
    draft: PreferenceConfirmDraft,
    session_id: str | None = None,
    ttl_sec: int = _DEFAULT_TTL_SEC,
) -> None:
    try:
        r = get_redis_client()
        await r.setex(
            _pref_confirm_key(user_id, session_id),
            ttl_sec,
            draft.model_dump_json(),
        )
    except Exception as e:
        logger.warning(f"set_preference_confirm_draft failed: {e}")


async def clear_preference_confirm_draft(user_id: int, session_id: str | None = None) -> None:
    try:
        r = get_redis_client()
        await r.delete(_pref_confirm_key(user_id, session_id))
    except Exception as e:
        logger.warning(f"clear_preference_confirm_draft failed: {e}")
