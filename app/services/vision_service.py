import asyncio
import base64
import json
import traceback
from logging import getLogger

from volcenginesdkarkruntime import Ark
from volcenginesdkarkruntime.types.responses.response import Response

from app.core.config import settings
from app.schemas.vision import AnalyzePhotoData, BurnEstimatePayload, IntakeEstimatePayload

logger = getLogger(__name__)

_UNCERTAIN = "无法识别，请重试或换一张图"

_VISION_TEXT = """
你是饮食与运动识别助手。根据用户照片判断主要内容，只输出**一个** JSON 对象，不要代码块、不要解释文字，保证可被 json.loads 解析。

字段要求：
- result_type: 仅允许 "intake" | "burn" | "uncertain"
- 若图片主要是食物/餐饮：result_type 为 "intake"，并填 intake 对象：name(食物名称), kcal_per_100g, protein_per_100g, carb_per_100g, fat_per_100g（均为每100克估计，数字）, suggested_food_id(无法确定则 null)
- 若图片主要是运动/训练场景：result_type 为 "burn"，并填 burn 对象：exercise_type 为 "cardio" 或 "anaerobic", intensity(1-5), duration_minutes(正整数), kcal(估算正数)
- 若均不明显或无法判断：result_type 为 "uncertain"，可填 message(简短中文)

示例（仅说明结构，勿照抄数值）:
{"result_type":"intake","intake":{"name":"米饭","kcal_per_100g":130,"protein_per_100g":2.7,"carb_per_100g":28.2,"fat_per_100g":0.3,"suggested_food_id":null}}
"""


def _mime_for_content_type(content_type: str) -> str:
    ct = (content_type or "image/jpeg").lower()
    if "png" in ct:
        return "image/png"
    if "webp" in ct:
        return "image/webp"
    return "image/jpeg"


def _data_url_for_image(image_bytes: bytes, content_type: str) -> str:
    mime = _mime_for_content_type(content_type)
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _text_from_response(resp: Response) -> str:
    parts: list[str] = []
    for item in resp.output or []:
        if getattr(item, "type", None) != "message":
            continue
        for c in getattr(item, "content", None) or []:
            if getattr(c, "type", None) == "output_text":
                parts.append(c.text)
    return "".join(parts).strip()


def _extract_json_object(text: str) -> dict | None:
    text = text.strip()
    if not text:
        return None
    l = text.find("{")
    r = text.rfind("}")
    if l < 0 or r <= l:
        return None
    try:
        return json.loads(text[l : r + 1])
    except json.JSONDecodeError:
        return None


def _normalize_to_analyze(d: dict) -> AnalyzePhotoData:
    """Accept slight key variants from the model and coerce to AnalyzePhotoData."""
    rt = d.get("result_type", "").lower()
    if rt not in ("intake", "burn", "uncertain"):
        raise ValueError("invalid result_type")
    if rt == "uncertain":
        msg = d.get("message")
        if not isinstance(msg, str) or not msg.strip():
            msg = _UNCERTAIN
        return AnalyzePhotoData(result_type="uncertain", message=msg)
    if rt == "intake":
        raw = d.get("intake") or {}
        sid = raw.get("suggested_food_id")
        if sid is not None and not isinstance(sid, int):
            try:
                sid = int(sid) if str(sid).isdigit() else None
            except (TypeError, ValueError):
                sid = None
        payload = IntakeEstimatePayload(
            name=str(raw.get("name", "未知食物"))[:200],
            kcal_per_100g=float(raw.get("kcal_per_100g", 0)),
            protein_per_100g=float(raw.get("protein_per_100g", 0)),
            carb_per_100g=float(raw.get("carb_per_100g", 0)),
            fat_per_100g=float(raw.get("fat_per_100g", 0)),
            suggested_food_id=sid,
        )
        return AnalyzePhotoData(result_type="intake", intake=payload, message=None)
    raw = d.get("burn") or {}
    et = str(raw.get("exercise_type", "cardio")).lower()
    if et not in ("cardio", "anaerobic"):
        et = "cardio"
    intensity = int(raw.get("intensity", 3) or 3)
    intensity = min(5, max(1, intensity))
    duration_minutes = int(raw.get("duration_minutes", 15) or 15)
    duration_minutes = max(1, duration_minutes)
    kcal = float(raw.get("kcal", 0) or 0)
    kcal = max(kcal, 1.0)
    payload = BurnEstimatePayload(
        exercise_type=et,  # type: ignore[arg-type]
        intensity=intensity,
        duration_minutes=duration_minutes,
        kcal=kcal,
    )
    return AnalyzePhotoData(result_type="burn", burn=payload, message=None)


def _call_ark_sync(image_bytes: bytes, content_type: str) -> AnalyzePhotoData:
    if not (settings.ARK_API_KEY or "").strip():
        logger.warning("ARK_API_KEY 未配置")
        return AnalyzePhotoData(result_type="uncertain", message="服务未配置视觉密钥")

    data_url = _data_url_for_image(image_bytes, content_type)
    user_content: list[dict] = [
        {"type": "input_image", "image_url": data_url},
        {"type": "input_text", "text": _VISION_TEXT},
    ]
    user_msg = {"role": "user", "content": user_content}
    input_body: list[dict] = [user_msg]

    client = Ark(
        base_url=settings.ARK_VISION_BASE_URL,
        api_key=settings.ARK_API_KEY,
    )
    try:
        resp = client.responses.create(
            model=settings.ARK_VISION_MODEL,
            input=input_body,
        )
    except Exception as e:  # noqa: BLE001
        logger.error("Ark 调用失败: %s\n%s", e, traceback.format_exc())
        return AnalyzePhotoData(result_type="uncertain", message="识别服务暂不可用，请稍后再试")

    if getattr(resp, "error", None) is not None:
        return AnalyzePhotoData(result_type="uncertain", message="模型返回错误")
    st = getattr(resp, "status", None)
    if st and st not in ("completed", "incomplete"):
        if st == "failed":
            return AnalyzePhotoData(result_type="uncertain", message="模型未能完成分析")

    text = _text_from_response(resp)
    parsed = _extract_json_object(text)
    if not parsed:
        logger.warning("无法从模型输出中解析 JSON: %s", text[:500])
        return AnalyzePhotoData(result_type="uncertain", message=_UNCERTAIN)
    try:
        return _normalize_to_analyze(parsed)
    except (ValueError, TypeError) as e:
        logger.warning("JSON 与 schema 不一致: %s | %s", e, text[:500])
        return AnalyzePhotoData(result_type="uncertain", message=_UNCERTAIN)


MAX_UPLOAD_BYTES = 10 * 1024 * 1024


async def analyze_photo_bytes(image_bytes: bytes, content_type: str) -> AnalyzePhotoData:
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        return AnalyzePhotoData(
            result_type="uncertain",
            message="图片请小于 10MB",
        )
    return await asyncio.to_thread(_call_ark_sync, image_bytes, content_type or "image/jpeg")
