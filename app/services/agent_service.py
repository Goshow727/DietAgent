import json

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.diet_agent import DietState, _get_llm, run_diet_agent
from app.core.error_code import ErrorCode
from app.core.exceptions import BusinessException
from app.models.food import Food
from app.models.intake_log import IntakeLog
from app.schemas.agent import ChatIn, ChatOut


async def _get_or_create_food(db: AsyncSession, food_name: str) -> Food:
    result = await db.execute(select(Food).where(Food.name.ilike(f"%{food_name}%")).limit(1))
    food = result.scalar_one_or_none()
    if food:
        return food
    llm = _get_llm()
    from langchain_core.messages import HumanMessage
    prompt = (
        f"估算[{food_name}]每100g的营养成分，只返回JSON，不要其他内容。\n"
        '格式：{"kcal": 数字, "protein": 数字, "carb": 数字, "fat": 数字}'
    )
    resp = await llm.ainvoke([HumanMessage(content=prompt)])
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
        name=food_name,
        kcal_per_100g=kcal,
        protein_per_100g=protein,
        carb_per_100g=carb,
        fat_per_100g=fat,
    )
    db.add(food)
    await db.commit()
    await db.refresh(food)
    return food


async def _handle_add_log(db: AsyncSession, user_id: int, food_name: str, amount_g: float) -> str:
    food = await _get_or_create_food(db, food_name)
    ratio = amount_g / 100
    log = IntakeLog(
        user_id=user_id,
        food_id=food.id,
        food_name=food.name,
        weight_grams=amount_g,
        protein_g=round(food.protein_per_100g * ratio, 2),
        carb_g=round(food.carb_per_100g * ratio, 2),
        fat_g=round(food.fat_per_100g * ratio, 2),
        kcal=round(food.kcal_per_100g * ratio, 2),
    )
    db.add(log)
    await db.commit()
    kcal = round(food.kcal_per_100g * ratio)
    return f"已记录：{food.name} {amount_g:.0f}g，约 {kcal} kcal"


async def chat(payload: ChatIn, db: AsyncSession, user_id: int) -> ChatOut:
    try:
        state: DietState = await run_diet_agent(payload.message)
        if state["intent"] == "add_log" and state["food_name"]:
            reply = await _handle_add_log(db, user_id, state["food_name"], state["amount_g"])
        else:
            reply = state["reply"]
    except Exception as e:
        logger.exception(f"diet_agent failed: {e}")
        raise BusinessException(ErrorCode.AGENT_INVOKE_FAILED, str(e)) from e
    return ChatOut(reply=reply)
