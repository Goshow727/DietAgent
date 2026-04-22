from fastapi import APIRouter, BackgroundTasks, Query

from app.api.deps import CurrentUser, DbSession
from app.core.error_code import ErrorCode
from app.core.exceptions import BusinessException
from app.core.response import R
from app.db.session import AsyncSessionLocal
from app.schemas.banner import BannerListOut, CardOut, RedCutOut
from app.services import banner_service

router = APIRouter(prefix="/banners", tags=["banners"])


async def _bg_ensure_pool(user_id: int) -> None:
    async with AsyncSessionLocal() as db:
        await banner_service.ensure_pool(user_id, db)


@router.get("", response_model=R[BannerListOut])
async def get_banners(
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    db: DbSession,
    count: int = Query(default=5, ge=1, le=10),
) -> R[BannerListOut]:
    cards = await banner_service.get_ready_cards(current_user.id, count, db)
    total_ready = await banner_service._ready_count(current_user.id, db)
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
) -> R[RedCutOut]:
    card = await banner_service.red_cut_card(card_id, current_user.id, db)
    if card is None:
        raise BusinessException(ErrorCode.NOT_FOUND, f"Card {card_id} not found")
    next_card = await banner_service.next_ready_card(current_user.id, db)
    background_tasks.add_task(_bg_ensure_pool, current_user.id)
    next_out = CardOut.model_validate(next_card) if next_card else None
    return R.ok(RedCutOut(card=next_out))


@router.post("/init", response_model=R[None])
async def init_banner_pool(
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    db: DbSession,
) -> R[None]:
    total_ready = await banner_service._ready_count(current_user.id, db)
    if total_ready < banner_service.POOL_THRESHOLD:
        background_tasks.add_task(_bg_ensure_pool, current_user.id)
    return R.ok(None)
