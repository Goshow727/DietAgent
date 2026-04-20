from datetime import date

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.core.response import R
from app.schemas.food import BurnLogCreate, BurnLogRead, FoodRead, IntakeLogCreate, IntakeLogRead
from app.services import burn_service, food_service, intake_service

food_router = APIRouter(prefix="/foods", tags=["foods"])
intake_router = APIRouter(prefix="/intakes", tags=["intakes"])
burn_router = APIRouter(prefix="/burns", tags=["burns"])


@food_router.get("", response_model=R[list[FoodRead]])
async def search_foods(
    db: DbSession,
    q: str = Query(default="", max_length=64),
) -> R[list[FoodRead]]:
    foods = await food_service.search_foods(db, q)
    return R.ok([FoodRead.model_validate(f) for f in foods])


@intake_router.post("", response_model=R[IntakeLogRead])
async def create_intake(
    payload: IntakeLogCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> R[IntakeLogRead]:
    log = await intake_service.create_intake(db, current_user.id, payload)
    return R.ok(IntakeLogRead.model_validate(log))


@intake_router.get("", response_model=R[list[IntakeLogRead]])
async def list_intakes(
    db: DbSession,
    current_user: CurrentUser,
    log_date: date = Query(alias="date", default_factory=date.today),
) -> R[list[IntakeLogRead]]:
    logs = await intake_service.list_intakes(db, current_user.id, log_date)
    return R.ok([IntakeLogRead.model_validate(l) for l in logs])


@intake_router.delete("/{intake_id}", response_model=R[None])
async def delete_intake(
    intake_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> R[None]:
    await intake_service.delete_intake(db, current_user.id, intake_id)
    return R.ok()


@burn_router.post("", response_model=R[BurnLogRead])
async def create_burn(
    payload: BurnLogCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> R[BurnLogRead]:
    log = await burn_service.create_burn(db, current_user.id, payload)
    return R.ok(BurnLogRead.model_validate(log))


@burn_router.get("", response_model=R[list[BurnLogRead]])
async def list_burns(
    db: DbSession,
    current_user: CurrentUser,
    log_date: date = Query(alias="date", default_factory=date.today),
) -> R[list[BurnLogRead]]:
    logs = await burn_service.list_burns(db, current_user.id, log_date)
    return R.ok([BurnLogRead.model_validate(l) for l in logs])


@burn_router.delete("/{burn_id}", response_model=R[None])
async def delete_burn(
    burn_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> R[None]:
    await burn_service.delete_burn(db, current_user.id, burn_id)
    return R.ok()
