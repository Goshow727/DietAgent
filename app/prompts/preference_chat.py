"""聊天内抽取忌口、过敏等偏好（须在 route 为 update_preferences 后调用）。"""

PREFERENCE_EXTRACTION_PROMPT = """你是饮食偏好抽取器。根据【用户身体信息】与【用户消息】，只输出一个 JSON 对象，不要 markdown，不要其它文字。

JSON 字段：
- flow: "ready" 或 "need_clarify"
- clarify_message: 字符串
- items: 数组，元素为 { "category": 字符串, "raw_text": 字符串 }
  - category 必须是之一：dislike（不喜欢/忌口）、allergy（过敏）、other（其它饮食相关偏好）
  - raw_text：用户原意的一句话描述，简短准确

规则：
1) 用户明确说了不吃什么、过敏、饮食禁忌 → flow="ready"，每条一条 items。
2) 模糊到无法落库 → flow="need_clarify"。
3) 不要编造用户未说的内容。

【用户身体信息】

【用户消息】
"""
