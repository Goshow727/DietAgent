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


@pytest.mark.asyncio
async def test_ensure_pool_triggers_generation_when_below_threshold():
    mock_db = AsyncMock()

    # Simulate scalar() returning 3 (below POOL_THRESHOLD=8)
    mock_result = MagicMock()
    mock_result.scalar.return_value = 3
    mock_db.execute.return_value = mock_result

    with patch("app.services.banner_service.generate_cards", new_callable=AsyncMock) as mock_gen:
        from app.services.banner_service import ensure_pool
        await ensure_pool(user_id=1, db=mock_db)

    mock_gen.assert_called_once()
    call_kwargs = mock_gen.call_args
    assert call_kwargs.kwargs["count"] == 5  # 8 - 3


@pytest.mark.asyncio
async def test_ensure_pool_skips_generation_when_full():
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = 8
    mock_db.execute.return_value = mock_result

    with patch("app.services.banner_service.generate_cards", new_callable=AsyncMock) as mock_gen:
        from app.services.banner_service import ensure_pool
        await ensure_pool(user_id=1, db=mock_db)

    mock_gen.assert_not_called()


@pytest.mark.asyncio
async def test_next_ready_card_not_in_delegates_when_exclude_empty():
    mock_db = AsyncMock()
    sentinel = MagicMock()

    with patch(
        "app.services.banner_service.next_ready_card",
        new_callable=AsyncMock,
    ) as mock_next:
        mock_next.return_value = sentinel
        from app.services.banner_service import next_ready_card_not_in

        out = await next_ready_card_not_in(1, mock_db, set())

    mock_next.assert_awaited_once_with(1, mock_db)
    assert out is sentinel


@pytest.mark.asyncio
async def test_next_ready_card_not_in_returns_first_not_excluded():
    mock_db = AsyncMock()
    card = MagicMock()
    card.id = "next-id"
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = card
    mock_db.execute.return_value = mock_result

    from app.services.banner_service import next_ready_card_not_in

    out = await next_ready_card_not_in(1, mock_db, {"a", "b"})
    assert out is card
    mock_db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_ready_cards_passes_exclude_to_query():
    mock_db = AsyncMock()
    mock_row = MagicMock()
    mock_row.id = "keep"
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_row]
    mock_db.execute.return_value = mock_result

    from app.services.banner_service import get_ready_cards

    out = await get_ready_cards(1, 1, mock_db, exclude_ids={"gone"})
    assert out == [mock_row]
    mock_db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_image_and_upload_logs_oss_stage_on_upload_failure():
    from app.agents import banner_agent

    mock_post_resp = MagicMock()
    mock_post_resp.raise_for_status = MagicMock()
    mock_post_resp.json.return_value = {"data": [{"url": "https://cdn.example.com/out.png"}]}

    mock_get_resp = MagicMock()
    mock_get_resp.raise_for_status = MagicMock()
    mock_get_resp.content = b"\xff\xd8\xff fake jpeg"

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_post_resp)
    mock_client.get = AsyncMock(return_value=mock_get_resp)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch.object(banner_agent.httpx, "AsyncClient", return_value=mock_cm), \
         patch.object(banner_agent, "upload_banner_image", side_effect=RuntimeError("oss put failed")), \
         patch.object(banner_agent, "logger") as mock_logger:
        out = await banner_agent.generate_image_and_upload("a sunny breakfast plate")

    assert out is None
    mock_logger.exception.assert_called_once()
    fmt = mock_logger.exception.call_args[0][0]
    assert "banner_image:oss_upload" in fmt


@pytest.mark.asyncio
async def test_generate_image_and_upload_logs_ark_stage_on_http_error():
    from app.agents import banner_agent
    import httpx

    mock_post_resp = MagicMock()
    mock_post_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "401",
        request=MagicMock(),
        response=MagicMock(),
    )

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_post_resp)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch.object(banner_agent.httpx, "AsyncClient", return_value=mock_cm), \
         patch.object(banner_agent, "logger") as mock_logger:
        out = await banner_agent.generate_image_and_upload("prompt")

    assert out is None
    mock_logger.exception.assert_called_once()
    assert "banner_image:ark_request" in mock_logger.exception.call_args[0][0]


@pytest.mark.asyncio
async def test_generate_cards_warns_when_image_missing_despite_prompt():
    from app.services import banner_service

    user = MagicMock()
    user.id = 42
    user.height = None
    user.weight = None
    user.age = None
    user.gender = None

    def result_scalar_one(u):
        r = MagicMock()
        r.scalar_one_or_none.return_value = u
        return r

    def result_empty_logs():
        r = MagicMock()
        r.scalars.return_value.all.return_value = []
        return r

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(
        side_effect=[
            result_scalar_one(user),
            result_empty_logs(),
            result_empty_logs(),
            result_empty_logs(),
        ]
    )

    async def refresh_sets_id(card):
        card.id = "card-uuid-1"

    mock_db.refresh = AsyncMock(side_effect=refresh_sets_id)
    mock_db.commit = AsyncMock()
    mock_db.add = MagicMock()

    with patch.object(banner_service.rag_service, "retrieve", new_callable=AsyncMock, return_value=[]), \
         patch.object(banner_service, "generate_card_drafts", new_callable=AsyncMock) as mock_drafts, \
         patch.object(banner_service, "generate_image_and_upload", new_callable=AsyncMock) as mock_img, \
         patch.object(banner_service, "logger") as mock_logger:
        mock_drafts.return_value = [
            {"title": "t", "desc": "d", "image_prompt": "breakfast scene", "category": "diet"},
        ]
        mock_img.return_value = None

        await banner_service.generate_cards(user_id=42, count=1, db=mock_db)

    mock_logger.warning.assert_called()
    joined = " ".join(str(a) for c in mock_logger.warning.call_args_list for a in c[0])
    assert "42" in joined
    assert "card-uuid-1" in joined
