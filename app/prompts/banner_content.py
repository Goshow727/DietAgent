BANNER_CONTENT_SYSTEM = (
    "你是一位美食推荐家，根据用户身体信息、近7天饮食记录、近7天运动消耗，为用户推荐饮食食谱。"
    "若可联网，互联网信息仅作补充，须优先采用下方「膳食指南参考」、用户身体信息与近7天记录、已拒绝主题；"
    "表述为科普性、个体化建议，禁止将网页或模型输出当作疾病诊断、疗效承诺或替代专业医疗，"
    "与指南或用户记录冲突时以所给指南与记录为准、保守表述。"
    "请生成 JSON 格式的推荐卡片，不要输出任何额外内容，不要包含 markdown 代码块。"
)


def format_banner_content_prompt(
    guideline_chunks: list[str],
    user_body_block: str,
    intake_summary: str,
    burn_summary: str,
    red_cut_titles: list[str],
    count: int,
) -> str:
    chunks_text = "\n\n".join(guideline_chunks) if guideline_chunks else "（暂无相关指南内容）"
    red_cut_text = "\n".join(f"- {t}" for t in red_cut_titles) if red_cut_titles else "无"

    return f"""【膳食指南参考】
{chunks_text}

【用户身体信息】
{user_body_block}

【近7天饮食记录】
{intake_summary}

【近7天运动消耗】
{burn_summary}

【已拒绝主题（请勿重复）】
{red_cut_text}

【任务】
生成 {count} 张推荐卡片，类别为 "diet" 或 "fitness"。
返回 JSON 数组，每项格式：
{{
  "title": "不超过8字的标题，",
  "desc": "4-6句描述，结合用户实际记录给出的饮食食谱，不要假大空的干净饮食，可以教怎么去做美食"
  "image_prompt": "English prompt for food or fitness image, photorealistic style, no text",
  "category": "diet or fitness"
}}"""
