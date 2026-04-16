from loguru import logger

from app.agents.diet_agent import run_diet_agent
from app.core.error_code import ErrorCode
from app.core.exceptions import BusinessException
from app.schemas.agent import ChatIn, ChatOut


async def chat(payload: ChatIn) -> ChatOut:
    try:
        reply = await run_diet_agent(payload.message)
    except Exception as e:
        logger.exception(f"diet_agent failed: {e}")
        raise BusinessException(ErrorCode.AGENT_INVOKE_FAILED, str(e)) from e
    return ChatOut(reply=reply)
