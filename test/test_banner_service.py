import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_retrieve_returns_content_strings():
    mock_doc = MagicMock()
    mock_doc.content = "每天摄入谷物250-400克"

    with patch("app.services.rag_service._embed", new_callable=AsyncMock) as mock_embed, \
         patch("app.services.rag_service._query_similar", new_callable=AsyncMock) as mock_query:
        mock_embed.return_value = [0.1] * 1536
        mock_query.return_value = [mock_doc]

        from app.services.rag_service import retrieve
        result = await retrieve("高脂肪摄入", categories=["fats"], top_k=1, db=AsyncMock())

    assert result == ["每天摄入谷物250-400克"]


def test_derive_categories_high_fat():
    from app.services.rag_service import derive_categories
    cats = derive_categories(avg_fat_pct=40, avg_protein_pct=20, days_without_burn=0, has_high_salt=False)
    assert "fats" in cats
    assert "general" in cats


def test_derive_categories_low_exercise():
    from app.services.rag_service import derive_categories
    cats = derive_categories(avg_fat_pct=20, avg_protein_pct=20, days_without_burn=5, has_high_salt=False)
    assert "exercise" in cats


@pytest.mark.asyncio
async def test_generate_card_drafts_returns_list():
    with patch("app.agents.banner_agent._get_llm") as mock_get_llm:
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = MagicMock(
            content='[{"title":"高蛋白早餐","desc":"适合增肌","image_prompt":"grilled chicken","category":"diet"}]'
        )
        mock_get_llm.return_value = mock_llm

        from app.agents.banner_agent import generate_card_drafts
        drafts = await generate_card_drafts(
            guideline_chunks=["每天摄入谷物250克"],
            user_body_block="身高180cm，体重75kg",
            intake_summary="近7天：鸡胸肉、燕麦",
            burn_summary="近7天：跑步30分钟×3",
            red_cut_titles=[],
            count=1,
        )

    assert len(drafts) == 1
    assert drafts[0]["title"] == "高蛋白早餐"
    assert drafts[0]["category"] == "diet"
