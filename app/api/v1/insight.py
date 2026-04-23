from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.core.response import R
from app.schemas.insight import HomeInsightData
from app.services import insight_service

router = APIRouter(prefix="/users/me", tags=["insight"])


@router.get("/home-insight", response_model=R[HomeInsightData])
async def get_home_insight(
    db: DbSession,
    current: CurrentUser,
) -> R[HomeInsightData]:
    data = await insight_service.build_home_insight(db, current.id)
    return R.ok(data)
