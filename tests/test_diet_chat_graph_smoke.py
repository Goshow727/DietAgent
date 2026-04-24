import pytest

from app.graphs.diet_chat_graph import compile_diet_chat_graph_checkpointer_memory


@pytest.mark.asyncio
async def test_graph_compiles_and_runs_noop() -> None:
    g = compile_diet_chat_graph_checkpointer_memory()
    out = await g.ainvoke(
        {
            "user_id": 1,
            "session_id": "s",
            "last_user_text": "hi",
            "hitl_phase": "idle",
        },
        config={"configurable": {"thread_id": "1:s"}},
    )
    assert out.get("reply") == "ok"
