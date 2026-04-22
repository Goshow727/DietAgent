"""食物营养：新建 Food 时每 100g 估算。调整话术只改本文件。"""


def format_food_per_100g_estimate_prompt(food_name: str) -> str:
    return (
        f"估算[{food_name}]每100g的营养成分，只返回JSON，不要其他内容。\n"
        '格式：{"kcal": 数字, "protein": 数字, "carb": 数字, "fat": 数字}'
    )
