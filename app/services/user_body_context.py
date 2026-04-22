from app.models.user import User


def format_user_body_context(user: User) -> str:
    """供结构化 LLM 使用的身体信息摘要；缺项标「未填写」。"""
    h = f"{user.height:g} cm" if user.height is not None else "未填写"
    w = f"{user.weight:g} kg" if user.weight is not None else "未填写"
    a = str(user.age) if user.age is not None else "未填写"
    g = user.gender or "未填写"
    return f"身高：{h}；体重：{w}；年龄：{a}；性别：{g}"
