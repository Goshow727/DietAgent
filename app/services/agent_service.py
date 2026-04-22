import json
import re

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.burn_agent import extract_burn_chat, normalize_burn_extraction
from app.agents.diet_agent import (
    _get_llm,
    extract_intake_chat,
    generate_general_advice,
    normalize_extraction,
    route_chat_intent,
)
from app.core.error_code import ErrorCode
from app.core.exceptions import BusinessException
from app.prompts import format_food_per_100g_estimate_prompt
from app.models.food import Food
from app.models.intake_log import IntakeLog
from app.models.user import User
from app.schemas.agent import ChatIn, ChatOut
from app.schemas.burn_draft import BurnConfirmDraft, BurnDraftLine
from app.schemas.burn_extraction import BurnFlow
from app.schemas.chat_intent import ChatIntentRoute, ChatRouteIntent
from app.schemas.food import BurnLogCreate
from app.schemas.intake_draft import IntakeConfirmDraft, IntakeDraftLine
from app.schemas.intake_extraction import ChatFlow, IntakeChatExtraction
from app.services import burn_service, chat_pending_service
from app.services.user_body_context import format_user_body_context

# 食物名开头的「一个」「200克」等量词+单位，入库前应去掉（如「一个鸡蛋」→「鸡蛋」）
_LEADING_QTY_UNIT = re.compile(
    r"^(?:[一二两三四五六七八九十百千万零半几\d\.]+)?"
    r"(?:个|只|根|条|块|片|碗|碟|盘|盏|杯|份|颗|粒|串|斤|克|g)\s*",
    re.IGNORECASE,
)


def _strip_leading_quantity_prefix(name: str) -> str:
    s = (name or "").strip()
    while True:
        ns = _LEADING_QTY_UNIT.sub("", s).strip()
        if ns == s:
            break
        s = ns
    return s


def _canonical_food_display_names(lookup_name: str, uttered_name: str) -> tuple[str, str]:
    lu = _strip_leading_quantity_prefix(lookup_name)
    ut = _strip_leading_quantity_prefix(uttered_name)
    if not lu and ut:
        lu = ut
    if not ut and lu:
        ut = lu
    return lu, ut


_INVALID_SINGLE_FOOD_NAME = frozenset("一两几半些点啥")

_ONLY_NUMBER_OR_MEASURE = re.compile(
    r"^(?:[一二两三四五六七八九十百千万零半几多点\d\.]+)?"
    r"(?:碗|碟|盘|盏|杯|个|只|根|片|勺|份|块|条|袋|盒|瓶|斤|克|g|毫升|ml|mL|L)?$",
    re.IGNORECASE,
)


def _is_valid_food_name(name: str) -> bool:
    s = (name or "").strip()
    if not s:
        return False
    if re.fullmatch(r"\d+\.?\d*", s):
        return False
    if len(s) == 1 and s in _INVALID_SINGLE_FOOD_NAME:
        return False
    if _ONLY_NUMBER_OR_MEASURE.fullmatch(s):
        return False
    return True


def _validate_extraction_foods(extraction: IntakeChatExtraction) -> tuple[bool, str]:
    if extraction.flow != ChatFlow.intake_ready:
        return True, ""
    for item in extraction.foods:
        lu, ut = _canonical_food_display_names(item.lookup_name, item.uttered_name)
        if not _is_valid_food_name(ut) or not _is_valid_food_name(lu):
            return (
                False,
                "请说明具体是哪种食物；若只说「一碗」「两碗」等而没有说是米饭、面条等，请补充食物名称。",
            )
    return True, ""


async def _find_food_by_names(
    db: AsyncSession, lookup_name: str, uttered_name: str | None
) -> Food | None:
    for term in (lookup_name, uttered_name):
        if not term or not term.strip():
            continue
        q = term.strip()
        result = await db.execute(select(Food).where(Food.name.ilike(f"%{q}%")).limit(1))
        hit = result.scalar_one_or_none()
        if hit:
            return hit
    return None


async def _get_or_create_food(db: AsyncSession, lookup_name: str, uttered_name: str | None) -> Food:
    food = await _find_food_by_names(db, lookup_name, uttered_name)
    if food:
        return food

    store_name = lookup_name.strip()
    llm = _get_llm()
    from langchain_core.messages import HumanMessage

    resp = await llm.ainvoke(
        [HumanMessage(content=format_food_per_100g_estimate_prompt(store_name))]
    )
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    try:
        data = json.loads(content.strip())
        kcal = float(data.get("kcal", 200))
        protein = float(data.get("protein", 5))
        carb = float(data.get("carb", 30))
        fat = float(data.get("fat", 5))
    except Exception:
        kcal, protein, carb, fat = 200.0, 5.0, 30.0, 5.0
    food = Food(
        name=store_name,
        kcal_per_100g=kcal,
        protein_per_100g=protein,
        carb_per_100g=carb,
        fat_per_100g=fat,
    )
    db.add(food)
    await db.commit()
    await db.refresh(food)
    return food


async def _handle_add_log(
    db: AsyncSession,
    user_id: int,
    lookup_name: str,
    display_name: str,
    amount_g: float,
) -> str:
    food = await _get_or_create_food(db, lookup_name, display_name if display_name != lookup_name else None)
    ratio = amount_g / 100
    log_name = display_name.strip() if display_name.strip() else food.name
    log = IntakeLog(
        user_id=user_id,
        food_id=food.id,
        food_name=log_name,
        weight_grams=amount_g,
        protein_g=round(food.protein_per_100g * ratio, 2),
        carb_g=round(food.carb_per_100g * ratio, 2),
        fat_g=round(food.fat_per_100g * ratio, 2),
        kcal=round(food.kcal_per_100g * ratio, 2),
    )
    db.add(log)
    await db.commit()
    kcal = round(food.kcal_per_100g * ratio)
    return f"已记录：{log_name} {amount_g:.0f}g，约 {kcal} kcal"


def _session_id(payload: ChatIn) -> str | None:
    sid = payload.session_id
    return sid.strip() if isinstance(sid, str) and sid.strip() else None


def _parse_confirm_intent(text: str) -> str | None:
    raw = text.strip()
    low = raw.lower()
    for w in ("取消", "不录", "不要", "算了", "放弃"):
        if w in raw:
            return "cancel"
    if low in ("n", "no"):
        return "cancel"
    for w in ("确认", "确定", "保存", "录入"):
        if w in raw:
            return "confirm"
    if low in ("ok", "yes", "y"):
        return "confirm"
    if raw in ("好", "行", "嗯", "恩", "可以", "好的", "好吧"):
        return "confirm"
    return None


def _exercise_cn(exercise_type: str) -> str:
    return "有氧" if exercise_type == "cardio" else "无氧"


async def _build_confirm_preview(db: AsyncSession, items: list[IntakeDraftLine]) -> str:
    lines: list[str] = []
    for i, it in enumerate(items, start=1):
        lu, ut = _canonical_food_display_names(it.lookup_name, it.uttered_name)
        name = ut or lu
        food = await _find_food_by_names(db, lu, ut)
        if food:
            kcal = round(food.kcal_per_100g * it.amount_g / 100)
            lines.append(
                f"{i}. {name}：{it.amount_g:.0f}g，约 {kcal} kcal（按已有「{food.name}」估算）"
            )
        else:
            lines.append(
                f"{i}. {name}：{it.amount_g:.0f}g（确认后将新建食物并估算营养后写入）"
            )
    body = "\n".join(lines)
    return f"将为您记录以下摄入（尚未写入）：\n{body}\n\n请回复「确认」写入饮食记录，或「取消」放弃。"


def _build_burn_preview(items: list[BurnDraftLine]) -> str:
    lines: list[str] = []
    for i, it in enumerate(items, start=1):
        note = f"「{it.activity_note}」" if it.activity_note.strip() else ""
        lines.append(
            f"{i}. {_exercise_cn(it.exercise_type)}{note}：强度 {it.intensity}/5，"
            f"{it.duration_minutes} 分钟，约 {round(it.kcal)} kcal"
        )
    body = "\n".join(lines)
    return (
        f"将为您记录以下运动消耗（尚未写入）：\n{body}\n\n"
        f"请回复「确认」写入消耗记录，或「取消」放弃。"
    )


async def chat(payload: ChatIn, db: AsyncSession, user: User) -> ChatOut:
    user_id = user.id
    session = _session_id(payload)
    body_block = format_user_body_context(user)
    msg = payload.message

    confirm_draft = await chat_pending_service.get_confirm_draft(user_id, session)
    if confirm_draft is not None:
        decision = _parse_confirm_intent(msg)
        if decision == "confirm":
            await chat_pending_service.clear_confirm_draft(user_id, session)
            try:
                lines: list[str] = []
                for it in confirm_draft.items:
                    lu, ut = _canonical_food_display_names(it.lookup_name, it.uttered_name)
                    lines.append(await _handle_add_log(db, user_id, lu, ut, float(it.amount_g)))
                return ChatOut(reply="已确认并写入：\n" + "\n".join(lines))
            except Exception as e:
                logger.exception(f"confirm intake commit failed: {e}")
                raise BusinessException(ErrorCode.AGENT_INVOKE_FAILED, str(e)) from e
        if decision == "cancel":
            await chat_pending_service.clear_confirm_draft(user_id, session)
            return ChatOut(reply="已取消，未写入饮食记录。")
        try:
            routed_quick = await route_chat_intent(msg)
            if routed_quick.intent == ChatRouteIntent.general:
                await chat_pending_service.clear_all_chat_state(user_id, session)
                try:
                    reply = await generate_general_advice(msg)
                except Exception as e:
                    logger.exception(f"generate_general_advice failed: {e}")
                    raise BusinessException(ErrorCode.AGENT_INVOKE_FAILED, str(e)) from e
                return ChatOut(reply=reply)
        except Exception:
            pass
        preview = await _build_confirm_preview(db, confirm_draft.items)
        return ChatOut(reply=preview)

    burn_confirm = await chat_pending_service.get_burn_confirm_draft(user_id, session)
    if burn_confirm is not None:
        decision = _parse_confirm_intent(msg)
        if decision == "confirm":
            await chat_pending_service.clear_burn_confirm_draft(user_id, session)
            try:
                out_lines: list[str] = []
                for it in burn_confirm.items:
                    await burn_service.create_burn(
                        db,
                        user_id,
                        BurnLogCreate(
                            exercise_type=it.exercise_type,
                            intensity=it.intensity,
                            duration_minutes=it.duration_minutes,
                            kcal=float(it.kcal),
                        ),
                    )
                    note = f"「{it.activity_note}」" if it.activity_note.strip() else ""
                    out_lines.append(
                        f"已记录：{_exercise_cn(it.exercise_type)}{note} "
                        f"{it.duration_minutes} 分钟，约 {round(it.kcal)} kcal"
                    )
                return ChatOut(reply="已确认并写入消耗：\n" + "\n".join(out_lines))
            except Exception as e:
                logger.exception(f"confirm burn commit failed: {e}")
                raise BusinessException(ErrorCode.AGENT_INVOKE_FAILED, str(e)) from e
        if decision == "cancel":
            await chat_pending_service.clear_burn_confirm_draft(user_id, session)
            return ChatOut(reply="已取消，未写入消耗记录。")
        try:
            routed_b = await route_chat_intent(msg)
            if routed_b.intent == ChatRouteIntent.general:
                await chat_pending_service.clear_all_chat_state(user_id, session)
                try:
                    reply = await generate_general_advice(msg)
                except Exception as e:
                    logger.exception(f"generate_general_advice failed: {e}")
                    raise BusinessException(ErrorCode.AGENT_INVOKE_FAILED, str(e)) from e
                return ChatOut(reply=reply)
        except Exception:
            pass
        return ChatOut(reply=_build_burn_preview(burn_confirm.items))

    burn_pending = await chat_pending_service.get_burn_pending_context(user_id, session)
    intake_pending = await chat_pending_service.get_pending_context(user_id, session)
    if burn_pending and intake_pending:
        await chat_pending_service.clear_burn_pending(user_id, session)
        burn_pending = None

    if burn_pending:
        route_ctx = burn_pending + "\n【用户补充说明】\n" + msg
    elif intake_pending:
        route_ctx = intake_pending + "\n【用户补充说明】\n" + msg
    else:
        route_ctx = msg

    try:
        routed = await route_chat_intent(route_ctx)
    except Exception as e:
        logger.warning(f"route_chat_intent failed, default log_intake: {e}")
        routed = ChatIntentRoute(intent=ChatRouteIntent.log_intake)

    if routed.intent == ChatRouteIntent.general:
        await chat_pending_service.clear_all_chat_state(user_id, session)
        try:
            reply = await generate_general_advice(msg)
        except Exception as e:
            logger.exception(f"generate_general_advice failed: {e}")
            raise BusinessException(ErrorCode.AGENT_INVOKE_FAILED, str(e)) from e
        return ChatOut(reply=reply)

    if routed.intent == ChatRouteIntent.log_burn:
        await chat_pending_service.clear_pending(user_id, session)
        await chat_pending_service.clear_confirm_draft(user_id, session)
        context_for_model = (
            burn_pending + "\n【用户补充说明】\n" + msg if burn_pending else msg
        )
        try:
            raw_burn = await extract_burn_chat(context_for_model, body_block)
        except Exception as e:
            logger.exception(f"extract_burn_chat failed: {e}")
            try:
                reply = await generate_general_advice(msg)
                await chat_pending_service.clear_burn_pending(user_id, session)
                return ChatOut(reply=reply)
            except Exception:
                raise BusinessException(ErrorCode.AGENT_INVOKE_FAILED, str(e)) from e

        burn_ex = normalize_burn_extraction(raw_burn)
        if burn_ex.flow == BurnFlow.need_clarify:
            clar = burn_ex.clarify_message.strip() or "请说说做了什么运动、多久、强度如何？"
            await chat_pending_service.set_burn_pending_context(
                user_id, context_for_model, session
            )
            return ChatOut(reply=clar)

        await chat_pending_service.clear_burn_pending(user_id, session)
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
        await chat_pending_service.set_burn_confirm_draft(
            user_id, BurnConfirmDraft(items=draft_items), session
        )
        return ChatOut(reply=_build_burn_preview(draft_items))

    # log_intake
    await chat_pending_service.clear_burn_pending(user_id, session)
    await chat_pending_service.clear_burn_confirm_draft(user_id, session)
    context_for_model = (
        intake_pending + "\n【用户补充说明】\n" + msg if intake_pending else msg
    )

    try:
        raw_extraction = await extract_intake_chat(context_for_model, body_block)
    except Exception as e:
        logger.exception(f"extract_intake_chat failed: {e}")
        try:
            reply = await generate_general_advice(msg)
            await chat_pending_service.clear_pending(user_id, session)
            return ChatOut(reply=reply)
        except Exception:
            raise BusinessException(ErrorCode.AGENT_INVOKE_FAILED, str(e)) from e

    extraction = normalize_extraction(raw_extraction)

    if extraction.flow == ChatFlow.need_clarify:
        clar = extraction.clarify_message.strip() or "请具体说说吃了什么、大概多少？"
        await chat_pending_service.set_pending_context(user_id, context_for_model, session)
        return ChatOut(reply=clar)

    ok, hint = _validate_extraction_foods(extraction)
    if not ok:
        await chat_pending_service.set_pending_context(user_id, context_for_model, session)
        return ChatOut(reply=hint)

    await chat_pending_service.clear_pending(user_id, session)

    draft_lines: list[IntakeDraftLine] = []
    for item in extraction.foods:
        lu, ut = _canonical_food_display_names(item.lookup_name, item.uttered_name)
        draft_lines.append(
            IntakeDraftLine(lookup_name=lu, uttered_name=ut, amount_g=float(item.amount_g))
        )
    draft = IntakeConfirmDraft(items=draft_lines)
    await chat_pending_service.set_confirm_draft(user_id, draft, session)
    try:
        preview = await _build_confirm_preview(db, draft_lines)
        return ChatOut(reply=preview)
    except Exception as e:
        logger.exception(f"build confirm preview failed: {e}")
        await chat_pending_service.clear_confirm_draft(user_id, session)
        raise BusinessException(ErrorCode.AGENT_INVOKE_FAILED, str(e)) from e


__all__ = ["chat", "_is_valid_food_name"]
