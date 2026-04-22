from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.core.response import R
from app.schemas.agent import ChatIn, ChatOut
from app.services import agent_service

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/chat", response_model=R[ChatOut])
async def chat(payload: ChatIn, current_user: CurrentUser, db: DbSession) -> R[ChatOut]:
    out = await agent_service.chat(payload, db, current_user)
    return R.ok(out)
