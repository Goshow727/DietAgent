"""饮食/运动洞察总结 — 与 Deepseek JSON 协议."""

INSIGHT_SYSTEM_JSON = (
    "你是营养与运动总结助手。仅根据用户给出的结构化数据输出一段中文总结，"
    "并给出 0～4 个标签（label 为简短中文（类似高蛋白、低脂，字数不超过4个字），tabTemp 为 0、1 或 2 表示三档色温/语义）。\n"
    "必须只输出一个 JSON 对象，不要 markdown 代码块，不要其他文字。JSON 与下列字段一致：\n"
    '{"desc": "字符串", "tags": [{"label": "示例", "tabTemp": 0}]}\n'
    "tabTemp 只能是 0、1 或 2 的整数；desc 为一段通顺的总结（可含换行，JSON 中需转义）。"
)


def build_user_payload(
    *,
    kind: str,
    period_text: str,
    intake_bullets: str,
    burn_bullets: str,
) -> str:
    """kind: daily|week| month；period_text 为可读区间说明。"""
    return (
        f"总结类型: {kind}\n"
        f"统计/展示区间: {period_text}\n\n"
        f"【摄入相关】\n{intake_bullets or '（无）'}\n\n"
        f"【运动消耗相关】\n{burn_bullets or '（无）'}\n"
    )
