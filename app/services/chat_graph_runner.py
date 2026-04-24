"""LangGraph 饮食对话入口：thread 级 checkpoint + interrupt 恢复。"""

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession

from app.graphs.diet_chat_graph import get_compiled_diet_chat_graph
from app.models.user import User
from app.schemas.agent import ChatIn, ChatOut


def _sid(session_id: str | None) -> str:
    return (session_id or "default").strip() or "default"


async def run_chat_turn(payload: ChatIn, db: AsyncSession, user: User) -> ChatOut:
    graph = get_compiled_diet_chat_graph()
    tid = f"{user.id}:{_sid(payload.session_id)}"
    config: RunnableConfig = {
        "configurable": {"thread_id": tid, "db": db, "user": user},
    }
    st = graph.get_state(config)
    if st.interrupts:
        out = await graph.ainvoke(Command(resume=payload.message), config=config)
    else:
        out = await graph.ainvoke(
            {
                "user_id": user.id,
                "session_id": _sid(payload.session_id),
                "last_user_text": payload.message,
            },
            config=config,
        )
    if out.get("__interrupt__"):
        intrs = out["__interrupt__"]
        if intrs:
            val = intrs[0].value
            if isinstance(val, dict) and val.get("preview"):
                return ChatOut(reply=str(val["preview"]))
        return ChatOut(reply=str(out.get("reply") or ""))
    return ChatOut(reply=str(out.get("reply") or ""))


__all__ = ["run_chat_turn"]
