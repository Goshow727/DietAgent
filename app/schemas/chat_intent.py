from enum import Enum

from pydantic import BaseModel


class ChatRouteIntent(str, Enum):
    """第一层：意图路由（仅分类，不抽取槽位）。"""

    general = "general"
    log_intake = "log_intake"
    log_burn = "log_burn"
    update_body_metrics = "update_body_metrics"
    update_preferences = "update_preferences"


class ChatIntentRoute(BaseModel):
    intent: ChatRouteIntent
