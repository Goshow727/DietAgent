"""饮食 Agent LangGraph：路由 → 子流水线 → HITL interrupt → 写库。"""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from loguru import logger

from app.graphs.diet_chat_state import DietChatState

_DONE = "done"


def _clear_draft_state(reply: str) -> dict:
    return {
        "reply": reply,
        "hitl_phase": "idle",
        "pending_confirm_kind": "none",
        "intake_draft_lines": [],
        "burn_draft_lines": [],
        "body_patch_dict": {},
        "preference_items": [],
    }


def _after_pipeline(state: DietChatState) -> str:
    if state.get("hitl_phase") == "awaiting_confirm":
        return "human_confirm"
    return _DONE


def _dispatch_route(state: DietChatState) -> str:
    intent = state.get("routed_intent") or "log_intake"
    m = {
        "general": "general_advice",
        "log_burn": "burn_pipeline",
        "log_intake": "intake_pipeline",
        "update_body_metrics": "body_pipeline",
        "update_preferences": "preference_pipeline",
    }
    return m.get(intent, "intake_pipeline")


async def route_intent_node(state: DietChatState, config: RunnableConfig) -> dict:
    from app.agents.diet_agent import route_chat_intent
    from app.schemas.chat_intent import ChatIntentRoute, ChatRouteIntent

    msg = state["last_user_text"]
    burn_pending = state.get("burn_pending_context")
    intake_pending = state.get("intake_pending_context")
    updates: dict = {}
    if burn_pending and intake_pending:
        updates["burn_pending_context"] = None
        burn_pending = None
    if burn_pending:
        route_ctx = burn_pending + "\n【用户补充说明】\n" + msg
    elif intake_pending:
        route_ctx = intake_pending + "\n【用户补充说明】\n" + msg
    else:
        route_ctx = msg
    try:
        routed = await route_chat_intent(route_ctx)
        intent = routed.intent.value
    except Exception as e:
        logger.warning(f"route_chat_intent failed, default log_intake: {e}")
        intent = ChatRouteIntent.log_intake.value
    updates["routed_intent"] = intent
    return updates


async def general_advice_node(state: DietChatState, config: RunnableConfig) -> dict:
    from app.agents.diet_agent import generate_general_advice

    msg = state["last_user_text"]
    try:
        reply = await generate_general_advice(msg)
    except Exception as e:
        logger.exception(f"generate_general_advice failed: {e}")
        raise
    return {
        "reply": reply,
        "intake_pending_context": None,
        "burn_pending_context": None,
        "intake_draft_lines": [],
        "burn_draft_lines": [],
        "body_patch_dict": {},
        "preference_items": [],
        "hitl_phase": "idle",
        "pending_confirm_kind": "none",
    }


async def burn_pipeline(state: DietChatState, config: RunnableConfig) -> dict:
    from app.agents.burn_agent import extract_burn_chat, normalize_burn_extraction
    from app.agents.diet_agent import generate_general_advice
    from app.schemas.burn_draft import BurnDraftLine
    from app.schemas.burn_extraction import BurnFlow
    from app.services import agent_service
    from app.services.user_body_context import format_user_context_for_model

    db = config["configurable"]["db"]
    user = config["configurable"]["user"]
    msg = state["last_user_text"]
    burn_pending = state.get("burn_pending_context")
    body_block = await format_user_context_for_model(db, user)
    context_for_model = burn_pending + "\n【用户补充说明】\n" + msg if burn_pending else msg
    try:
        raw_burn = await extract_burn_chat(context_for_model, body_block)
    except Exception as e:
        logger.exception(f"extract_burn_chat failed: {e}")
        try:
            reply = await generate_general_advice(msg)
            return {
                "reply": reply,
                "burn_pending_context": None,
                "intake_pending_context": None,
                "intake_draft_lines": [],
            }
        except Exception:
            raise
    burn_ex = normalize_burn_extraction(raw_burn)
    if burn_ex.flow == BurnFlow.need_clarify:
        clar = burn_ex.clarify_message.strip() or "请说说做了什么运动、多久、强度如何？"
        return {
            "reply": clar,
            "burn_pending_context": context_for_model,
            "intake_pending_context": None,
            "intake_draft_lines": [],
        }
    draft_items: list[BurnDraftLine] = []
    for it in burn_ex.items:
        draft_items.append(
            BurnDraftLine(
                exercise_type=it.exercise_type,  # type: ignore[arg-type]
                intensity=it.intensity,
                duration_minutes=int(it.duration_minutes or 0),
                kcal=float(it.kcal or 0),
                activity_note=it.activity_note or "",
            )
        )
    preview = agent_service._build_burn_preview(draft_items)
    return {
        "reply": preview,
        "burn_pending_context": None,
        "intake_pending_context": None,
        "intake_draft_lines": [],
        "burn_draft_lines": [d.model_dump() for d in draft_items],
        "pending_confirm_kind": "burn",
        "hitl_phase": "awaiting_confirm",
    }


async def intake_pipeline(state: DietChatState, config: RunnableConfig) -> dict:
    from app.agents.diet_agent import extract_intake_chat, generate_general_advice, normalize_extraction
    from app.schemas.intake_draft import IntakeDraftLine
    from app.schemas.intake_extraction import ChatFlow
    from app.services import agent_service
    from app.services.user_body_context import format_user_context_for_model

    db = config["configurable"]["db"]
    user = config["configurable"]["user"]
    msg = state["last_user_text"]
    intake_pending = state.get("intake_pending_context")
    body_block = await format_user_context_for_model(db, user)
    context_for_model = intake_pending + "\n【用户补充说明】\n" + msg if intake_pending else msg
    try:
        raw_extraction = await extract_intake_chat(context_for_model, body_block)
    except Exception as e:
        logger.exception(f"extract_intake_chat failed: {e}")
        try:
            reply = await generate_general_advice(msg)
            return {
                "reply": reply,
                "intake_pending_context": None,
                "burn_pending_context": None,
                "burn_draft_lines": [],
            }
        except Exception:
            raise
    extraction = normalize_extraction(raw_extraction)
    if extraction.flow == ChatFlow.need_clarify:
        clar = extraction.clarify_message.strip() or "请具体说说吃了什么、大概多少？"
        return {
            "reply": clar,
            "intake_pending_context": context_for_model,
            "burn_pending_context": None,
            "burn_draft_lines": [],
        }
    ok, hint = agent_service._validate_extraction_foods(extraction)
    if not ok:
        return {
            "reply": hint,
            "intake_pending_context": context_for_model,
            "burn_pending_context": None,
            "burn_draft_lines": [],
        }
    draft_lines: list[IntakeDraftLine] = []
    for item in extraction.foods:
        lu, ut = agent_service._canonical_food_display_names(item.lookup_name, item.uttered_name)
        draft_lines.append(
            IntakeDraftLine(lookup_name=lu, uttered_name=ut, amount_g=float(item.amount_g))
        )
    preview = await agent_service._build_confirm_preview(db, draft_lines)
    return {
        "reply": preview,
        "intake_pending_context": None,
        "burn_pending_context": None,
        "burn_draft_lines": [],
        "intake_draft_lines": [d.model_dump() for d in draft_lines],
        "pending_confirm_kind": "intake",
        "hitl_phase": "awaiting_confirm",
    }


def _body_preview(patch) -> str:
    from app.schemas.body_patch import BodyMetricsPatch

    p = patch if isinstance(patch, BodyMetricsPatch) else BodyMetricsPatch.model_validate(patch)
    parts: list[str] = []
    if p.height is not None:
        parts.append(f"身高 {p.height:g} cm")
    if p.weight is not None:
        parts.append(f"体重 {p.weight:g} kg")
    if p.age is not None:
        parts.append(f"年龄 {p.age}")
    if p.gender is not None and str(p.gender).strip():
        parts.append(f"性别 {p.gender}")
    body = "；".join(parts) if parts else "（无具体字段）"
    return (
        f"将为您更新身体信息（尚未写入）：\n{body}\n\n"
        f"请回复「确认」保存，或「取消」放弃。"
    )


async def body_pipeline(state: DietChatState, config: RunnableConfig) -> dict:
    from app.agents.diet_agent import extract_body_metrics_chat
    from app.schemas.body_patch import BodyMetricsFlow, BodyMetricsPatch
    from app.services.user_body_context import format_user_context_for_model

    db = config["configurable"]["db"]
    user = config["configurable"]["user"]
    msg = state["last_user_text"]
    body_block = await format_user_context_for_model(db, user)
    ex = await extract_body_metrics_chat(msg, body_block)
    if ex.flow == BodyMetricsFlow.need_clarify:
        clar = (ex.clarify_message or "").strip() or "请说明要更新的身高、体重、年龄或性别。"
        return {"reply": clar}
    patch = ex.patch
    if patch is None:
        return {"reply": "请说明要更新的身高或体重等具体数值。"}
    data = patch.model_dump(exclude_none=True)
    if not data:
        return {"reply": "请说明要更新的身高或体重等具体数值。"}
    preview = _body_preview(patch)
    return {
        "reply": preview,
        "body_patch_dict": data,
        "pending_confirm_kind": "body",
        "hitl_phase": "awaiting_confirm",
    }


def _preference_preview(items: list) -> str:
    lines = []
    for i, it in enumerate(items, start=1):
        lines.append(f"{i}. [{it.category}] {it.raw_text}")
    body = "\n".join(lines)
    return (
        f"将为您记录以下饮食偏好（尚未写入）：\n{body}\n\n"
        f"请回复「确认」保存，或「取消」放弃。"
    )


async def preference_pipeline(state: DietChatState, config: RunnableConfig) -> dict:
    from app.agents.diet_agent import extract_preferences_chat
    from app.schemas.preference_extraction import PreferenceFlow, PreferenceItem
    from app.services.user_body_context import format_user_context_for_model

    db = config["configurable"]["db"]
    user = config["configurable"]["user"]
    msg = state["last_user_text"]
    body_block = await format_user_context_for_model(db, user)
    ex = await extract_preferences_chat(msg, body_block)
    if ex.flow == PreferenceFlow.need_clarify:
        clar = (ex.clarify_message or "").strip() or "请具体说说忌口、过敏或不想吃的东西。"
        return {"reply": clar}
    if not ex.items:
        return {"reply": "请具体说说忌口、过敏或不想吃的东西。"}
    items = ex.items
    preview = _preference_preview(items)
    return {
        "reply": preview,
        "preference_items": [i.model_dump() for i in items],
        "pending_confirm_kind": "preference",
        "hitl_phase": "awaiting_confirm",
    }


async def human_confirm(state: DietChatState, config: RunnableConfig) -> dict:
    from app.agents.diet_agent import generate_general_advice, route_chat_intent
    from app.core.error_code import ErrorCode
    from app.core.exceptions import BusinessException
    from app.schemas.chat_intent import ChatRouteIntent
    from app.schemas.body_patch import BodyMetricsPatch
    from app.schemas.burn_draft import BurnDraftLine
    from app.schemas.food import BurnLogCreate
    from app.schemas.intake_draft import IntakeDraftLine
    from app.schemas.user import UserUpdate
    from app.services import agent_service, burn_service, user_preference_service, user_service
    from app.services.chat_confirm_utils import parse_confirm_intent

    db = config["configurable"]["db"]
    user = config["configurable"]["user"]
    preview = state.get("reply") or ""
    kind = state.get("pending_confirm_kind") or "none"

    user_msg = interrupt({"preview": preview, "kind": kind})
    if not isinstance(user_msg, str):
        user_msg = str(user_msg)

    decision = parse_confirm_intent(user_msg)
    if decision == "cancel":
        return _clear_draft_state("已取消，未写入。")

    if decision == "confirm":
        try:
            if kind == "intake":
                lines_out: list[str] = []
                for d in state.get("intake_draft_lines") or []:
                    it = IntakeDraftLine.model_validate(d)
                    lu, ut = agent_service._canonical_food_display_names(it.lookup_name, it.uttered_name)
                    lines_out.append(
                        await agent_service._handle_add_log(db, user.id, lu, ut, float(it.amount_g))
                    )
                return _clear_draft_state("已确认并写入：\n" + "\n".join(lines_out))
            if kind == "burn":
                out_lines: list[str] = []
                for d in state.get("burn_draft_lines") or []:
                    it = BurnDraftLine.model_validate(d)
                    await burn_service.create_burn(
                        db,
                        user.id,
                        BurnLogCreate(
                            exercise_type=it.exercise_type,
                            intensity=it.intensity,
                            duration_minutes=it.duration_minutes,
                            kcal=float(it.kcal),
                        ),
                    )
                    note = f"「{it.activity_note}」" if it.activity_note.strip() else ""
                    ex_cn = agent_service._exercise_cn(it.exercise_type)
                    out_lines.append(
                        f"已记录：{ex_cn}{note} {it.duration_minutes} 分钟，约 {round(it.kcal)} kcal"
                    )
                return _clear_draft_state("已确认并写入消耗：\n" + "\n".join(out_lines))
            if kind == "body":
                patch = BodyMetricsPatch.model_validate(state.get("body_patch_dict") or {})
                payload = UserUpdate(**patch.model_dump(exclude_none=True))
                await user_service.update_user(db, user, payload)
                await db.refresh(user)
                return _clear_draft_state("已更新身体信息。")
            if kind == "preference":
                tuples = [
                    (str(x["category"]), str(x["raw_text"]))
                    for x in (state.get("preference_items") or [])
                ]
                await user_preference_service.add_preferences(db, user.id, tuples)
                return _clear_draft_state("已保存您的饮食偏好。")
        except Exception as e:
            logger.exception(f"human_confirm commit failed: {e}")
            raise BusinessException(ErrorCode.AGENT_INVOKE_FAILED, str(e)) from e

    try:
        quick = await route_chat_intent(user_msg)
        if quick.intent == ChatRouteIntent.general:
            reply = await generate_general_advice(user_msg)
            cleared = _clear_draft_state(reply)
            return cleared
    except Exception:
        pass
    return {"reply": preview}


def build_diet_chat_graph() -> StateGraph:
    g: StateGraph = StateGraph(DietChatState)
    g.add_node("route_intent", route_intent_node)
    g.add_node("general_advice", general_advice_node)
    g.add_node("burn_pipeline", burn_pipeline)
    g.add_node("intake_pipeline", intake_pipeline)
    g.add_node("body_pipeline", body_pipeline)
    g.add_node("preference_pipeline", preference_pipeline)
    g.add_node("human_confirm", human_confirm)

    g.add_edge(START, "route_intent")
    g.add_conditional_edges(
        "route_intent",
        _dispatch_route,
        {
            "general_advice": "general_advice",
            "burn_pipeline": "burn_pipeline",
            "intake_pipeline": "intake_pipeline",
            "body_pipeline": "body_pipeline",
            "preference_pipeline": "preference_pipeline",
        },
    )
    g.add_edge("general_advice", END)
    for n in ("burn_pipeline", "intake_pipeline", "body_pipeline", "preference_pipeline"):
        g.add_conditional_edges(
            n,
            _after_pipeline,
            {"human_confirm": "human_confirm", _DONE: END},
        )
    g.add_edge("human_confirm", END)
    return g


_compiled_memory = None


def get_compiled_diet_chat_graph():
    global _compiled_memory
    if _compiled_memory is None:
        _compiled_memory = build_diet_chat_graph().compile(checkpointer=MemorySaver())
    return _compiled_memory


def compile_diet_chat_graph_checkpointer_memory():
    """单测用：每次独立 MemorySaver，避免用全局单例。"""
    return build_diet_chat_graph().compile(checkpointer=MemorySaver())
