from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.core.response import R
from app.schemas.agent import ChatIn, ChatOut
from app.services import agent_service

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/chat", response_model=R[ChatOut])
async def chat(payload: ChatIn, _: CurrentUser) -> R[ChatOut]:
    out = await agent_service.chat(payload)
    return R.ok(out)
