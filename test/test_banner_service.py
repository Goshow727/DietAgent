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


@pytest.mark.asyncio
async def test_derive_categories_high_fat():
    from app.services.rag_service import derive_categories
    cats = derive_categories(avg_fat_pct=40, avg_protein_pct=20, days_without_burn=0, has_high_salt=False)
    assert "fats" in cats
    assert "general" in cats


@pytest.mark.asyncio
async def test_derive_categories_low_exercise():
    from app.services.rag_service import derive_categories
    cats = derive_categories(avg_fat_pct=20, avg_protein_pct=20, days_without_burn=5, has_high_salt=False)
    assert "exercise" in cats
