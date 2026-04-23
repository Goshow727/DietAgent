from fastapi import APIRouter, BackgroundTasks, Body, Query

from app.api.deps import CurrentUser, DbSession
from app.core.error_code import ErrorCode
from app.core.exceptions import BusinessException
from app.core.response import R
from app.db.session import AsyncSessionLocal
from app.schemas.banner import BannerListOut, CardOut, RedCutIn, RedCutOut
from app.services import banner_service

router = APIRouter(prefix="/banners", tags=["banners"])


def _parse_exclude_ids(raw: str | None) -> set[str] | None:
    if not raw or not raw.strip():
        return None
    ids = {p.strip() for p in raw.split(",") if p.strip()}
    return ids or None


async def _bg_ensure_pool(user_id: int) -> None:
    async with AsyncSessionLocal() as db:
        await banner_service.ensure_pool(user_id, db)


@router.get("", response_model=R[BannerListOut])
async def get_banners(
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    db: DbSession,
    count: int = Query(default=1, ge=1, le=10),
    exclude_ids: str | None = Query(
        default=None,
        description="Comma-separated recommendation_card ids to exclude (e.g. already on device)",
    ),
) -> R[BannerListOut]:
    exclude = _parse_exclude_ids(exclude_ids)
    await banner_service.consume_banner_get_quota(current_user.id, db)
    cards = await banner_service.get_ready_cards(
        current_user.id, count, db, exclude_ids=exclude
    )
    total_ready = await banner_service.ready_count(current_user.id, db)
    if total_ready < banner_service.POOL_THRESHOLD:
        background_tasks.add_task(_bg_ensure_pool, current_user.id)
    out = [CardOut.model_validate(c) for c in cards]
    return R.ok(BannerListOut(cards=out))


@router.put("/{card_id}/red-cut", response_model=R[RedCutOut])
async def red_cut_banner(
    card_id: str,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    db: DbSession,
    body: RedCutIn = Body(default_factory=RedCutIn),
) -> R[RedCutOut]:
    _ = body  # 保留 body 以兼容旧客户端；下一张请用 GET ?count=1&exclude_ids=
    card = await banner_service.red_cut_card(card_id, current_user.id, db)
    if card is None:
        raise BusinessException(ErrorCode.NOT_FOUND, f"Card {card_id} not found")
    background_tasks.add_task(_bg_ensure_pool, current_user.id)
    return R.ok(RedCutOut(card=None))


@router.post("/init", response_model=R[None])
async def init_banner_pool(
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    db: DbSession,
) -> R[None]:
    total_ready = await banner_service.ready_count(current_user.id, db)
    if total_ready < banner_service.POOL_THRESHOLD:
        background_tasks.add_task(_bg_ensure_pool, current_user.id)
    return R.ok(None)
