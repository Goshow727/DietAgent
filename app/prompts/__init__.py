"""集中存放 LLM 提示词，按业务分文件，便于统一维护。"""

from app.prompts.body_metrics_chat import BODY_METRICS_EXTRACTION_PROMPT
from app.prompts.burn_extraction import BURN_CHAT_EXTRACTION_PROMPT
from app.prompts.chat_intent_router import CHAT_INTENT_ROUTER_PROMPT
from app.prompts.diet_advisor import (
    DIET_ADVISOR_SYSTEM_PROMPT,
    format_general_advice_user_message,
)
from app.prompts.food_nutrition import format_food_per_100g_estimate_prompt
from app.prompts.intake_extraction import INTAKE_CHAT_EXTRACTION_PROMPT
from app.prompts.preference_chat import PREFERENCE_EXTRACTION_PROMPT
from app.prompts.banner_content import BANNER_CONTENT_SYSTEM, format_banner_content_prompt

__all__ = [
    "BODY_METRICS_EXTRACTION_PROMPT",
    "BURN_CHAT_EXTRACTION_PROMPT",
    "CHAT_INTENT_ROUTER_PROMPT",
    "DIET_ADVISOR_SYSTEM_PROMPT",
    "INTAKE_CHAT_EXTRACTION_PROMPT",
    "PREFERENCE_EXTRACTION_PROMPT",
    "format_food_per_100g_estimate_prompt",
    "format_general_advice_user_message",
    "BANNER_CONTENT_SYSTEM",
    "format_banner_content_prompt",
]
