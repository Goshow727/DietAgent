# Recommendation Banner Cards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a personalized AI-generated banner card pool with RAG-enhanced content, Doubao-Seedream-4.0 image generation, and real API integration replacing the existing mock banner system.

**Architecture:** DB-only pool (`recommendation_cards` table). Two-stage generation pipeline: Qwen LLM produces card text using top-5 pgvector chunks from the 2022 Chinese Dietary Guidelines; Doubao-Seedream-4.0 (Ark API via httpx) generates images stored to OSS. FastAPI `BackgroundTask` fires `ensure_pool` after GET and red-cut to maintain POOL_THRESHOLD=8 ready cards per user.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL + pgvector, Alembic, Qwen via DashScope, Doubao-Seedream-4.0 via Ark REST API, httpx, Aliyun OSS (oss2), React Native (frontend).

---

## File Map

**Backend — New:**
- `app/models/recommendation_card.py`
- `app/schemas/banner.py`
- `app/prompts/banner_content.py`
- `app/agents/banner_agent.py`
- `app/services/rag_service.py`
- `app/services/banner_service.py`
- `app/api/v1/banner.py`
- `alembic/versions/c3d4e5f6a7b8_add_recommendation_cards.py`
- `alembic/versions/d4e5f6a7b8c9_add_vector_docs_category.py`
- `scripts/ingest_dietary_guidelines.py`
- `test/test_banner_service.py`
- `test/test_banner_api.py`

**Backend — Modified:**
- `app/core/config.py` — add `ARK_API_KEY`, `ARK_IMAGE_MODEL`
- `app/services/oss_service.py` — add `upload_banner_image`
- `app/models/__init__.py` — import `RecommendationCard`
- `app/api/v1/router.py` — include `banner.router`

**Frontend — New:**
- `src/api/banner.js`

**Frontend — Modified:**
- `src/context/LogsContext.js` — expose `token` in context value
- `src/components/BannerCarousel.js` — `GlassCard` supports `image_url`
- `src/screens/HomeScreen.js` — replace mock API with real `banner.js` calls

---

## Task 1: Config — Ark API settings

**Files:**
- Modify: `app/core/config.py`

- [ ] **Step 1: Add Ark settings to Settings class**

In `app/core/config.py`, add two fields after `QWEN_MODEL`:

```python
ARK_API_KEY: str = "ark-5630aaf3-aa54-442c-bcac-a38103e7029a-af269"
ARK_IMAGE_MODEL: str = "api-key-20260421124338"
ARK_IMAGE_URL: str = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
```

- [ ] **Step 2: Verify settings load**

```bash
cd D:/AgentDemo/dietAgent_demo1
python -c "from app.core.config import settings; print(settings.ARK_API_KEY[:8])"
```

Expected output: `ark-5630`

- [ ] **Step 3: Commit**

```bash
git add app/core/config.py
git commit -m "feat: add Ark image generation config"
```

---

## Task 2: OSS helper — upload_banner_image

**Files:**
- Modify: `app/services/oss_service.py`

- [ ] **Step 1: Add upload_banner_image function**

Append to `app/services/oss_service.py` after the existing `upload_avatar` function:

```python
def upload_banner_image(data: bytes) -> str:
    key = f"banners/{uuid.uuid4().hex}.jpg"
    _bucket().put_object(key, data, headers={"Content-Type": "image/jpeg"})
    return f"{settings.OSS_BASE_URL}/{key}"
```

- [ ] **Step 2: Commit**

```bash
git add app/services/oss_service.py
git commit -m "feat: add upload_banner_image to oss_service"
```

---

## Task 3: DB Model — RecommendationCard

**Files:**
- Create: `app/models/recommendation_card.py`
- Modify: `app/models/__init__.py`

- [ ] **Step 1: Create the model**

Create `app/models/recommendation_card.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class RecommendationCard(Base):
    __tablename__ = "recommendation_cards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[int] = mapped_column(index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    desc: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    image_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="diet")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    red_cut_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 2: Register in models __init__**

In `app/models/__init__.py`, add the import and update `__all__`:

```python
from app.models.burn_log import BurnLog
from app.models.food import Food
from app.models.intake_log import IntakeLog
from app.models.recommendation_card import RecommendationCard
from app.models.user import User
from app.models.vector_doc import VectorDoc

__all__ = ["User", "VectorDoc", "Food", "IntakeLog", "BurnLog", "RecommendationCard"]
```

- [ ] **Step 3: Verify import**

```bash
python -c "from app.models import RecommendationCard; print(RecommendationCard.__tablename__)"
```

Expected: `recommendation_cards`

- [ ] **Step 4: Commit**

```bash
git add app/models/recommendation_card.py app/models/__init__.py
git commit -m "feat: add RecommendationCard model"
```

---

## Task 4: Alembic Migrations

**Files:**
- Create: `alembic/versions/c3d4e5f6a7b8_add_recommendation_cards.py`
- Create: `alembic/versions/d4e5f6a7b8c9_add_vector_docs_category.py`

- [ ] **Step 1: Create migration for recommendation_cards table**

Create `alembic/versions/c3d4e5f6a7b8_add_recommendation_cards.py`:

```python
"""add recommendation cards

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-22 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recommendation_cards",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("desc", sa.Text(), nullable=False),
        sa.Column("image_url", sa.String(512), nullable=True),
        sa.Column("image_prompt", sa.Text(), nullable=True),
        sa.Column("category", sa.String(32), nullable=False, server_default="diet"),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("red_cut_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_recommendation_cards_user_id", "recommendation_cards", ["user_id"]
    )
    op.create_index(
        "ix_recommendation_cards_user_status",
        "recommendation_cards",
        ["user_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_recommendation_cards_user_status", table_name="recommendation_cards")
    op.drop_index("ix_recommendation_cards_user_id", table_name="recommendation_cards")
    op.drop_table("recommendation_cards")
```

- [ ] **Step 2: Create migration for vector_docs category column**

Create `alembic/versions/d4e5f6a7b8c9_add_vector_docs_category.py`:

```python
"""add category to vector_docs

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-22 10:05:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vector_docs",
        sa.Column("category", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("vector_docs", "category")
```

- [ ] **Step 3: Also add category field to VectorDoc model**

In `app/models/vector_doc.py`, add `category` field after `content`:

```python
from pgvector.sqlalchemy import Vector
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

EMBEDDING_DIM = 1536


class VectorDoc(Base, TimestampMixin):
    __tablename__ = "vector_docs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
```

- [ ] **Step 4: Run migrations**

```bash
alembic upgrade head
```

Expected output ends with: `Running upgrade b2c3d4e5f6a7 -> c3d4e5f6a7b8 ... Running upgrade c3d4e5f6a7b8 -> d4e5f6a7b8c9`

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/c3d4e5f6a7b8_add_recommendation_cards.py
git add alembic/versions/d4e5f6a7b8c9_add_vector_docs_category.py
git add app/models/vector_doc.py
git commit -m "feat: add recommendation_cards table and vector_docs.category column"
```

---

## Task 5: Pydantic Schemas

**Files:**
- Create: `app/schemas/banner.py`

- [ ] **Step 1: Create banner schemas**

Create `app/schemas/banner.py`:

```python
from pydantic import BaseModel


class CardOut(BaseModel):
    id: str
    title: str
    desc: str
    image_url: str | None
    category: str

    model_config = {"from_attributes": True}


class BannerListOut(BaseModel):
    cards: list[CardOut]


class RedCutOut(BaseModel):
    card: CardOut | None
```

- [ ] **Step 2: Verify import**

```bash
python -c "from app.schemas.banner import CardOut, BannerListOut, RedCutOut; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add app/schemas/banner.py
git commit -m "feat: add banner Pydantic schemas"
```

---

## Task 6: RAG Service

**Files:**
- Create: `app/services/rag_service.py`

- [ ] **Step 1: Write the failing test**

Create `test/test_banner_service.py`:

```python
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
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest test/test_banner_service.py::test_retrieve_returns_content_strings -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'app.services.rag_service'`

- [ ] **Step 3: Create rag_service.py**

Create `app/services/rag_service.py`:

```python
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.vector_doc import VectorDoc, EMBEDDING_DIM

_ALWAYS_INCLUDE = {"general"}

_HIGH_FAT_CATEGORIES = {"fats", "general"}
_LOW_PROTEIN_CATEGORIES = {"protein", "general"}
_LOW_EXERCISE_CATEGORIES = {"exercise", "general"}
_HIGH_SALT_CATEGORIES = {"salt_sugar", "general"}


def derive_categories(
    avg_fat_pct: float,
    avg_protein_pct: float,
    days_without_burn: int,
    has_high_salt: bool,
) -> list[str]:
    cats: set[str] = set(_ALWAYS_INCLUDE)
    if avg_fat_pct > 35:
        cats |= _HIGH_FAT_CATEGORIES
    if avg_protein_pct < 15:
        cats |= _LOW_PROTEIN_CATEGORIES
    if days_without_burn >= 3:
        cats |= _LOW_EXERCISE_CATEGORIES
    if has_high_salt:
        cats |= _HIGH_SALT_CATEGORIES
    return sorted(cats)


async def _embed(text: str) -> list[float]:
    client = AsyncOpenAI(
        api_key=settings.DASHSCOPE_API_KEY,
        base_url=settings.DASHSCOPE_BASE_URL,
    )
    resp = await client.embeddings.create(
        model="text-embedding-v2",
        input=text,
        encoding_format="float",
    )
    return resp.data[0].embedding


async def _query_similar(
    db: AsyncSession,
    embedding: list[float],
    categories: list[str],
    top_k: int,
) -> list[VectorDoc]:
    from pgvector.sqlalchemy import Vector
    from sqlalchemy import cast

    stmt = (
        select(VectorDoc)
        .where(VectorDoc.source == "dietary_guidelines_2022")
        .where(VectorDoc.category.in_(categories))
        .order_by(VectorDoc.embedding.op("<=>")(cast(embedding, Vector(EMBEDDING_DIM))))
        .limit(top_k)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def retrieve(
    query: str,
    categories: list[str],
    top_k: int,
    db: AsyncSession,
) -> list[str]:
    embedding = await _embed(query)
    docs = await _query_similar(db, embedding, categories, top_k)
    return [d.content for d in docs]
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
pytest test/test_banner_service.py::test_retrieve_returns_content_strings -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add app/services/rag_service.py test/test_banner_service.py
git commit -m "feat: add rag_service with pgvector retrieval"
```

---

## Task 7: Banner Content Prompt

**Files:**
- Create: `app/prompts/banner_content.py`

- [ ] **Step 1: Create the prompt module**

Create `app/prompts/banner_content.py`:

```python
BANNER_CONTENT_SYSTEM = (
    "你是一位专业营养顾问，严格依据《中国居民膳食指南（2022版）》为用户提供个性化建议。"
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
  "title": "不超过20字的标题",
  "desc": "2-4句描述，结合用户实际记录给出具体建议",
  "image_prompt": "English prompt for food or fitness image, photorealistic style, no text",
  "category": "diet or fitness"
}}"""
```

- [ ] **Step 2: Add to prompts __init__**

In `app/prompts/__init__.py`, add:

```python
from app.prompts.banner_content import BANNER_CONTENT_SYSTEM, format_banner_content_prompt
```

Check the existing imports in `app/prompts/__init__.py` and append these two lines without removing anything.

- [ ] **Step 3: Verify import**

```bash
python -c "from app.prompts import BANNER_CONTENT_SYSTEM; print(BANNER_CONTENT_SYSTEM[:20])"
```

Expected: `你是一位专业营养顾`

- [ ] **Step 4: Commit**

```bash
git add app/prompts/banner_content.py app/prompts/__init__.py
git commit -m "feat: add banner content LLM prompt"
```

---

## Task 8: Banner Agent — Content + Image Generation

**Files:**
- Create: `app/agents/banner_agent.py`

- [ ] **Step 1: Write the failing test**

Add to `test/test_banner_service.py`:

```python
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
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest test/test_banner_service.py::test_generate_card_drafts_returns_list -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'app.agents.banner_agent'`

- [ ] **Step 3: Create banner_agent.py**

Create `app/agents/banner_agent.py`:

```python
import json
import re

import httpx
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.diet_agent import _get_llm
from app.core.config import settings
from app.prompts import BANNER_CONTENT_SYSTEM, format_banner_content_prompt
from app.services.oss_service import upload_banner_image


def _strip_json(text: str) -> str:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    return m.group(1).strip() if m else text


async def generate_card_drafts(
    guideline_chunks: list[str],
    user_body_block: str,
    intake_summary: str,
    burn_summary: str,
    red_cut_titles: list[str],
    count: int,
) -> list[dict]:
    prompt = format_banner_content_prompt(
        guideline_chunks=guideline_chunks,
        user_body_block=user_body_block,
        intake_summary=intake_summary,
        burn_summary=burn_summary,
        red_cut_titles=red_cut_titles,
        count=count,
    )
    llm = _get_llm()
    resp = await llm.ainvoke(
        [SystemMessage(content=BANNER_CONTENT_SYSTEM), HumanMessage(content=prompt)]
    )
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    data = json.loads(_strip_json(content))
    if not isinstance(data, list):
        data = [data]
    return data[:count]


async def generate_image_and_upload(image_prompt: str) -> str | None:
    headers = {
        "Authorization": f"Bearer {settings.ARK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.ARK_IMAGE_MODEL,
        "prompt": image_prompt,
        "n": 1,
        "size": "1024x1024",
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(settings.ARK_IMAGE_URL, json=payload, headers=headers)
            resp.raise_for_status()
            image_url = resp.json()["data"][0]["url"]
            img_resp = await client.get(image_url, timeout=30.0)
            img_resp.raise_for_status()
            oss_url = upload_banner_image(img_resp.content)
            return oss_url
    except Exception:
        return None
```

- [ ] **Step 4: Run tests**

```bash
pytest test/test_banner_service.py -v
```

Expected: both tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add app/agents/banner_agent.py test/test_banner_service.py
git commit -m "feat: add banner_agent with Qwen content + Seedream image generation"
```

---

## Task 9: Banner Service — Pool Management

**Files:**
- Create: `app/services/banner_service.py`

- [ ] **Step 1: Write the failing test**

Add to `test/test_banner_service.py`:

```python
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest test/test_banner_service.py::test_ensure_pool_triggers_generation_when_below_threshold test/test_banner_service.py::test_ensure_pool_skips_generation_when_full -v
```

Expected: both `FAILED`

- [ ] **Step 3: Create banner_service.py**

Create `app/services/banner_service.py`:

```python
from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.banner_agent import generate_card_drafts, generate_image_and_upload
from app.models.intake_log import IntakeLog
from app.models.burn_log import BurnLog
from app.models.recommendation_card import RecommendationCard
from app.models.user import User
from app.services import rag_service
from app.services.user_body_context import format_user_body_context

POOL_THRESHOLD = 8
_HIGH_SALT_FOOD_KEYWORDS = ["腌", "咸", "泡菜", "酱", "火锅", "薯片", "培根"]


async def _ready_count(user_id: int, db: AsyncSession) -> int:
    stmt = select(func.count()).where(
        RecommendationCard.user_id == user_id,
        RecommendationCard.status == "ready",
    )
    result = await db.execute(stmt)
    return result.scalar() or 0


async def _get_last7_intake(user_id: int, db: AsyncSession) -> list[IntakeLog]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    stmt = (
        select(IntakeLog)
        .where(IntakeLog.user_id == user_id, IntakeLog.logged_at >= cutoff)
        .order_by(IntakeLog.logged_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _get_last7_burn(user_id: int, db: AsyncSession) -> list[BurnLog]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    stmt = (
        select(BurnLog)
        .where(BurnLog.user_id == user_id, BurnLog.logged_at >= cutoff)
        .order_by(BurnLog.logged_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


def _intake_summary(logs: list[IntakeLog]) -> str:
    if not logs:
        return "近7天无饮食记录"
    lines = [f"- {l.food_name} {l.weight_grams:.0f}g ({l.kcal:.0f}kcal)" for l in logs[:15]]
    return "\n".join(lines)


def _burn_summary(logs: list[BurnLog]) -> str:
    if not logs:
        return "近7天无运动记录"
    lines = [f"- {l.exercise_type} {l.duration_minutes}分钟 ({l.kcal:.0f}kcal)" for l in logs]
    return "\n".join(lines)


def _derive_rag_categories(
    intake_logs: list[IntakeLog], burn_logs: list[BurnLog]
) -> list[str]:
    total_kcal = sum(l.kcal for l in intake_logs) or 1
    total_fat_kcal = sum(l.fat_g * 9 for l in intake_logs)
    total_protein_kcal = sum(l.protein_g * 4 for l in intake_logs)
    avg_fat_pct = (total_fat_kcal / total_kcal) * 100
    avg_protein_pct = (total_protein_kcal / total_kcal) * 100

    # find days with no burn in last 7 days
    burn_dates = {l.logged_at.date() for l in burn_logs if l.logged_at}
    from datetime import date
    all_days = {(date.today() - timedelta(days=i)) for i in range(7)}
    days_without_burn = len(all_days - burn_dates)

    has_high_salt = any(
        kw in l.food_name for l in intake_logs for kw in _HIGH_SALT_FOOD_KEYWORDS
    )

    return rag_service.derive_categories(
        avg_fat_pct=avg_fat_pct,
        avg_protein_pct=avg_protein_pct,
        days_without_burn=days_without_burn,
        has_high_salt=has_high_salt,
    )


async def _red_cut_titles(user_id: int, db: AsyncSession) -> list[str]:
    stmt = select(RecommendationCard.title).where(
        RecommendationCard.user_id == user_id,
        RecommendationCard.status == "red_cut",
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def generate_cards(user_id: int, count: int, db: AsyncSession) -> None:
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        return

    intake_logs = await _get_last7_intake(user_id, db)
    burn_logs = await _get_last7_burn(user_id, db)
    red_cut = await _red_cut_titles(user_id, db)
    categories = _derive_rag_categories(intake_logs, burn_logs)

    query_text = _intake_summary(intake_logs)[:200] + " " + _burn_summary(burn_logs)[:100]

    try:
        chunks = await rag_service.retrieve(
            query=query_text, categories=categories, top_k=5, db=db
        )
    except Exception as e:
        logger.warning(f"RAG retrieval failed: {e}")
        chunks = []

    try:
        drafts = await generate_card_drafts(
            guideline_chunks=chunks,
            user_body_block=format_user_body_context(user),
            intake_summary=_intake_summary(intake_logs),
            burn_summary=_burn_summary(burn_logs),
            red_cut_titles=red_cut,
            count=count,
        )
    except Exception as e:
        logger.error(f"Banner content generation failed for user {user_id}: {e}")
        return

    for draft in drafts:
        card = RecommendationCard(
            user_id=user_id,
            title=(draft.get("title") or "")[:200],
            desc=draft.get("desc") or "",
            image_prompt=draft.get("image_prompt"),
            category=draft.get("category", "diet"),
            status="queued",
        )
        db.add(card)
        await db.commit()
        await db.refresh(card)

        image_url = None
        if card.image_prompt:
            image_url = await generate_image_and_upload(card.image_prompt)

        card.image_url = image_url
        card.status = "ready"
        await db.commit()


async def ensure_pool(user_id: int, db: AsyncSession) -> None:
    count = await _ready_count(user_id, db)
    deficit = POOL_THRESHOLD - count
    if deficit > 0:
        await generate_cards(user_id=user_id, count=deficit, db=db)


async def get_ready_cards(user_id: int, count: int, db: AsyncSession) -> list[RecommendationCard]:
    stmt = (
        select(RecommendationCard)
        .where(
            RecommendationCard.user_id == user_id,
            RecommendationCard.status == "ready",
        )
        .order_by(RecommendationCard.created_at.asc())
        .limit(count)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def red_cut_card(card_id: str, user_id: int, db: AsyncSession) -> RecommendationCard | None:
    stmt = select(RecommendationCard).where(
        RecommendationCard.id == card_id,
        RecommendationCard.user_id == user_id,
    )
    result = await db.execute(stmt)
    card = result.scalar_one_or_none()
    if card is None:
        return None
    card.status = "red_cut"
    card.red_cut_at = datetime.now(timezone.utc)
    await db.commit()
    return card


async def next_ready_card(user_id: int, db: AsyncSession) -> RecommendationCard | None:
    stmt = (
        select(RecommendationCard)
        .where(
            RecommendationCard.user_id == user_id,
            RecommendationCard.status == "ready",
        )
        .order_by(RecommendationCard.created_at.asc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
```

- [ ] **Step 4: Run tests**

```bash
pytest test/test_banner_service.py -v
```

Expected: all 4 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add app/services/banner_service.py test/test_banner_service.py
git commit -m "feat: add banner_service with pool management"
```

---

## Task 10: API Endpoints

**Files:**
- Create: `app/api/v1/banner.py`
- Modify: `app/api/v1/router.py`

- [ ] **Step 1: Write the failing API test**

Create `test/test_banner_api.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app


def _make_card(card_id="abc", title="测试卡片", status="ready"):
    card = MagicMock()
    card.id = card_id
    card.title = title
    card.desc = "描述内容"
    card.image_url = None
    card.category = "diet"
    card.status = status
    return card


@pytest.mark.asyncio
async def test_get_banners_returns_cards():
    with patch("app.api.v1.banner.banner_service.get_ready_cards", new_callable=AsyncMock) as mock_get, \
         patch("app.api.v1.banner.banner_service._ready_count", new_callable=AsyncMock) as mock_count, \
         patch("app.api.deps.get_current_user") as mock_user:

        mock_user.return_value = MagicMock(id=1)
        mock_get.return_value = [_make_card()]
        mock_count.return_value = 8

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/api/v1/banners?count=3",
                headers={"Authorization": "Bearer test-token"},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert len(data["data"]["cards"]) == 1
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest test/test_banner_api.py::test_get_banners_returns_cards -v
```

Expected: `FAILED` — `404 Not Found` or import error

- [ ] **Step 3: Create banner.py API endpoints**

Create `app/api/v1/banner.py`:

```python
from fastapi import APIRouter, BackgroundTasks, Query

from app.api.deps import CurrentUser, DbSession
from app.core.error_code import ErrorCode
from app.core.exceptions import BusinessException
from app.core.response import R
from app.db.session import AsyncSessionLocal
from app.schemas.banner import BannerListOut, CardOut, RedCutOut
from app.services import banner_service

router = APIRouter(prefix="/banners", tags=["banners"])


async def _bg_ensure_pool(user_id: int) -> None:
    async with AsyncSessionLocal() as db:
        await banner_service.ensure_pool(user_id, db)


@router.get("", response_model=R[BannerListOut])
async def get_banners(
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    db: DbSession,
    count: int = Query(default=5, ge=1, le=10),
) -> R[BannerListOut]:
    cards = await banner_service.get_ready_cards(current_user.id, count, db)
    total_ready = await banner_service._ready_count(current_user.id, db)
    if total_ready < banner_service.POOL_THRESHOLD:
        background_tasks.add_task(_bg_ensure_pool, current_user.id)
    out = [CardOut.model_validate(c) for c in cards]
    return R.ok(BannerListOut(cards=out))


@router.put("/{card_id}/red-cut", response_model=R[RedCutOut])
async def red_cut_banner(
    card_id: str,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    db: DbSession,
) -> R[RedCutOut]:
    card = await banner_service.red_cut_card(card_id, current_user.id, db)
    if card is None:
        raise BusinessException(ErrorCode.NOT_FOUND, f"Card {card_id} not found")
    next_card = await banner_service.next_ready_card(current_user.id, db)
    background_tasks.add_task(_bg_ensure_pool, current_user.id)
    next_out = CardOut.model_validate(next_card) if next_card else None
    return R.ok(RedCutOut(card=next_out))


@router.post("/init", response_model=R[None])
async def init_banner_pool(
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    db: DbSession,
) -> R[None]:
    total_ready = await banner_service._ready_count(current_user.id, db)
    if total_ready < banner_service.POOL_THRESHOLD:
        background_tasks.add_task(_bg_ensure_pool, current_user.id)
    return R.ok(None)
```

- [ ] **Step 4: Register router**

In `app/api/v1/router.py`, add:

```python
from fastapi import APIRouter

from app.api.v1 import agent, auth, banner, nls, user
from app.api.v1.food import burn_router, food_router, intake_router

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(user.router)
api_router.include_router(agent.router)
api_router.include_router(banner.router)
api_router.include_router(nls.router)
api_router.include_router(food_router)
api_router.include_router(intake_router)
api_router.include_router(burn_router)
```

- [ ] **Step 5: Check ErrorCode has NOT_FOUND**

```bash
python -c "from app.core.error_code import ErrorCode; print(ErrorCode.NOT_FOUND)"
```

If `NOT_FOUND` does not exist, check what error codes are available with:
```bash
python -c "from app.core.error_code import ErrorCode; print([e.name for e in ErrorCode])"
```

Use the closest equivalent (e.g., `RESOURCE_NOT_FOUND` or define `NOT_FOUND = 404`).

- [ ] **Step 6: Run API test**

```bash
pytest test/test_banner_api.py -v
```

Expected: `PASSED`

- [ ] **Step 7: Commit**

```bash
git add app/api/v1/banner.py app/api/v1/router.py test/test_banner_api.py
git commit -m "feat: add banner API endpoints GET/PUT/POST"
```

---

## Task 11: Dietary Guidelines Ingestion Script

**Files:**
- Create: `scripts/ingest_dietary_guidelines.py`

This script is run once manually to populate `vector_docs`. It expects the guidelines text at `docs/dietary_guidelines_2022.txt` (one section per paragraph, blank lines between sections).

- [ ] **Step 1: Create the ingestion script**

Create `scripts/ingest_dietary_guidelines.py`:

```python
"""
One-time script to ingest the 2022 Chinese Dietary Guidelines into vector_docs.

Usage:
    python scripts/ingest_dietary_guidelines.py docs/dietary_guidelines_2022.txt

The text file should have sections separated by blank lines. Each non-empty
paragraph becomes one chunk. Add a comment on the first line of each section
to tag its category: # category: grains
"""
import asyncio
import sys
from pathlib import Path

from openai import AsyncOpenAI
from sqlalchemy import select

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.vector_doc import VectorDoc, EMBEDDING_DIM

VALID_CATEGORIES = {
    "grains", "vegetables", "fruits", "protein",
    "dairy", "fats", "salt_sugar", "exercise", "hydration", "general",
}

SOURCE = "dietary_guidelines_2022"


def parse_chunks(filepath: str) -> list[tuple[str, str]]:
    """Returns list of (content, category) tuples."""
    text = Path(filepath).read_text(encoding="utf-8")
    raw_blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    chunks = []
    for block in raw_blocks:
        lines = block.splitlines()
        category = "general"
        content_lines = []
        for line in lines:
            if line.startswith("# category:"):
                cat = line.split(":", 1)[1].strip()
                if cat in VALID_CATEGORIES:
                    category = cat
            else:
                content_lines.append(line)
        content = "\n".join(content_lines).strip()
        if content:
            chunks.append((content, category))
    return chunks


async def embed(text: str) -> list[float]:
    client = AsyncOpenAI(
        api_key=settings.DASHSCOPE_API_KEY,
        base_url=settings.DASHSCOPE_BASE_URL,
    )
    resp = await client.embeddings.create(
        model="text-embedding-v2",
        input=text,
        encoding_format="float",
    )
    return resp.data[0].embedding


async def main(filepath: str) -> None:
    chunks = parse_chunks(filepath)
    print(f"Parsed {len(chunks)} chunks from {filepath}")

    async with AsyncSessionLocal() as db:
        inserted = 0
        skipped = 0
        for content, category in chunks:
            # idempotency check
            existing = await db.execute(
                select(VectorDoc).where(
                    VectorDoc.source == SOURCE,
                    VectorDoc.content == content,
                ).limit(1)
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue

            embedding = await embed(content)
            doc = VectorDoc(
                source=SOURCE,
                content=content,
                category=category,
                embedding=embedding,
            )
            db.add(doc)
            await db.commit()
            inserted += 1
            print(f"  [{inserted}] Inserted: {content[:50]}...")

    print(f"Done. Inserted {inserted}, skipped {skipped} duplicates.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/ingest_dietary_guidelines.py <path_to_txt>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
```

- [ ] **Step 2: Place the guidelines text file**

Place the 2022 Chinese Dietary Guidelines text at `docs/dietary_guidelines_2022.txt`. Each section separated by a blank line. Prefix each section with `# category: <name>` to tag it. Example format:

```
# category: grains
平衡膳食准则一：食物多样，合理搭配
每天的膳食应包括谷薯类、蔬菜水果、畜禽鱼蛋奶和豆类食物。
每天摄入谷类食物200-300克，其中包含全谷物和杂豆50-150克。

# category: vegetables
平衡膳食准则二：多吃蔬果、奶类、全谷、大豆
蔬菜水果、全谷物和奶制品是平衡膳食的重要组成部分。
餐餐有蔬菜，保证每天摄入不少于300克的新鲜蔬菜。
```

- [ ] **Step 3: Run the ingestion**

```bash
python scripts/ingest_dietary_guidelines.py docs/dietary_guidelines_2022.txt
```

Expected: prints chunk count and insertion progress, ends with `Done. Inserted N, skipped 0 duplicates.`

- [ ] **Step 4: Commit**

```bash
git add scripts/ingest_dietary_guidelines.py
git commit -m "feat: add dietary guidelines RAG ingestion script"
```

---

## Task 12: Frontend — API Client

**Files:**
- Create: `src/api/banner.js` (in `D:/AgentDemo/front/app_demo/demo_2/src/api/`)

- [ ] **Step 1: Create banner.js**

Create `D:/AgentDemo/front/app_demo/demo_2/src/api/banner.js`:

```javascript
import { API_BASE_URL, fetchWithTimeout, authHeader, jsonAuthHeader } from './client';

export async function initBannerPool(token) {
  try {
    await fetchWithTimeout(
      `${API_BASE_URL}/api/v1/banners/init`,
      { method: 'POST', headers: jsonAuthHeader(token) },
    );
  } catch (_) {
    // fire-and-forget, ignore errors
  }
}

export async function getBanners(token, count = 5) {
  const resp = await fetchWithTimeout(
    `${API_BASE_URL}/api/v1/banners?count=${count}`,
    { method: 'GET', headers: authHeader(token) },
  );
  if (!resp.ok) return [];
  const json = await resp.json();
  return json?.data?.cards ?? [];
}

export async function redCutBanner(token, cardId) {
  try {
    const resp = await fetchWithTimeout(
      `${API_BASE_URL}/api/v1/banners/${cardId}/red-cut`,
      { method: 'PUT', headers: authHeader(token) },
    );
    if (!resp.ok) return null;
    const json = await resp.json();
    return json?.data?.card ?? null;
  } catch (_) {
    return null;
  }
}
```

- [ ] **Step 2: Commit**

```bash
cd "D:/AgentDemo/front/app_demo/demo_2"
git add src/api/banner.js
git commit -m "feat: add banner API client"
```

---

## Task 13: Frontend — GlassCard image_url Support

**Files:**
- Modify: `D:/AgentDemo/front/app_demo/demo_2/src/components/BannerCarousel.js`

The `GlassCard` component is defined inline in `BannerCarousel.js` at line 164. Currently it renders `item.image` (a `require()` result). We need it to also handle `item.image_url` (an OSS https URL).

- [ ] **Step 1: Update GlassCard image block**

In `BannerCarousel.js`, find this block inside `GlassCard` (around line 199):

```javascript
      <Animated.View style={[g.imgBox, imageAnim]}>
        {item.image
          ? <Image source={item.image} style={g.imgFill} resizeMode="cover" />
          : <Text style={g.emoji}>{item.emoji}</Text>}
      </Animated.View>
```

Replace it with:

```javascript
      <Animated.View style={[g.imgBox, imageAnim]}>
        {item.image_url
          ? <Image source={{ uri: item.image_url }} style={g.imgFill} resizeMode="cover" />
          : item.image
            ? <Image source={item.image} style={g.imgFill} resizeMode="cover" />
            : <Text style={g.emoji}>{item.emoji ?? '🍽️'}</Text>}
      </Animated.View>
```

- [ ] **Step 2: Commit**

```bash
git add src/components/BannerCarousel.js
git commit -m "feat: GlassCard supports image_url OSS remote images"
```

---

## Task 14: Frontend — HomeScreen Real API Integration

**Files:**
- Modify: `D:/AgentDemo/front/app_demo/demo_2/src/context/LogsContext.js` — expose `token`
- Modify: `D:/AgentDemo/front/app_demo/demo_2/src/screens/HomeScreen.js` — replace mock API

- [ ] **Step 1: Expose token from LogsContext**

In `LogsContext.js`, the `LogsProvider` already receives `token` as a prop. Add it to the context value on line 84:

Find:
```javascript
  return (
    <LogsContext.Provider value={{ intakeLogs, burnLogs, refresh, addIntakeItem, addBurnEntry }}>
```

Replace with:
```javascript
  return (
    <LogsContext.Provider value={{ token, intakeLogs, burnLogs, refresh, addIntakeItem, addBurnEntry }}>
```

- [ ] **Step 2: Update HomeScreen imports**

In `HomeScreen.js`, find line 22:

```javascript
import { initBannerStack, unlikeBanner, fetchNewBanner } from '../mocks/mockApi';
```

Replace with:

```javascript
import { initBannerPool, getBanners, redCutBanner } from '../api/banner';
```

Also add `LogsContext` import after the existing imports at the top:

```javascript
import { LogsContext } from '../context/LogsContext';
```

- [ ] **Step 3: Read token from context in HomeScreen**

In `HomeScreen`, after the `useHomeData()` call (around line 94), add:

```javascript
  const { token } = React.useContext(LogsContext);
```

If `React` is not imported directly, use `import React from 'react'` or destructure `useContext` from the existing React import. Check the existing imports — `useEffect, useState, useRef, useCallback` are already imported from `'react'`, so add `useContext` to that import list.

- [ ] **Step 4: Replace the init useEffect**

Find the existing init useEffect (lines 106–111):

```javascript
  useEffect(() => {
    initBannerStack().then(({ count, banners: initBanners }) => {
      bannerCapacityRef.current = count;
      setBanners(initBanners);
    });
  }, []);
```

Replace with:

```javascript
  useEffect(() => {
    if (!token) return;
    initBannerPool(token);
    getBanners(token, 5).then(cards => {
      if (cards.length > 0) setBanners(cards);
    });
  }, [token]);
```

- [ ] **Step 5: Replace handleRedCut**

Find the existing `handleRedCut` callback (lines 114–126):

```javascript
  const handleRedCut = useCallback((slotIndex) => {
    const item = bannersRef.current[slotIndex];
    setBanners(prev => prev.filter((_, i) => i !== slotIndex));
    unlikeBanner({ userId: 1001, action: 'UNLIKE', bannerId: item?.id }).catch(() => {});
    fetchNewBanner().then(newBanner => {
      if (newBanner) {
        setBanners(prev => {
          if (prev.length < bannerCapacityRef.current) return [...prev, newBanner];
          return prev;
        });
      }
    }).catch(() => {});
  }, []);
```

Replace with:

```javascript
  const handleRedCut = useCallback((slotIndex) => {
    const item = bannersRef.current[slotIndex];
    if (!item?.id) return;
    setBanners(prev => prev.filter((_, i) => i !== slotIndex));
    redCutBanner(token, item.id).then(newCard => {
      if (newCard) {
        setBanners(prev => [...prev, newCard]);
      }
    }).catch(() => {});
  }, [token]);
```

- [ ] **Step 6: Remove bannerCapacityRef (no longer needed)**

Delete these two lines (around line 98–99):

```javascript
  const bannerCapacityRef = useRef(5);
```

And delete `bannerCapacityRef.current = count;` which no longer exists after the useEffect replacement. Verify the file has no remaining reference to `bannerCapacityRef`.

- [ ] **Step 7: Test the integration manually**

Start the backend:
```bash
cd D:/AgentDemo/dietAgent_demo1
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Start the frontend (Expo):
```bash
cd D:/AgentDemo/front/app_demo/demo_2
npx expo start
```

Open the app, log in, navigate to HomeScreen. Verify:
1. Banner cards appear (may take a few seconds for first generation)
2. Left-swipe red-cut removes a card and the PUT `/api/v1/banners/{id}/red-cut` call succeeds
3. A new card slides in from the bottom-right if pool has ready cards

- [ ] **Step 8: Commit**

```bash
git add src/context/LogsContext.js src/screens/HomeScreen.js
git commit -m "feat: integrate real banner API into HomeScreen, replace mock"
```

---

## Self-Review Checklist

- [x] Config: `ARK_API_KEY`, `ARK_IMAGE_MODEL`, `ARK_IMAGE_URL` added
- [x] DB model: `recommendation_cards` table with all spec columns
- [x] Migrations: both created with correct `down_revision` chain
- [x] Schemas: `CardOut`, `BannerListOut`, `RedCutOut`
- [x] RAG: `derive_categories`, `retrieve`, pgvector `<=>` query
- [x] Prompt: system prompt + `format_banner_content_prompt`
- [x] Agent: `generate_card_drafts` (Qwen) + `generate_image_and_upload` (Seedream → OSS)
- [x] Service: `ensure_pool` (POOL_THRESHOLD=8), `generate_cards`, `get_ready_cards`, `red_cut_card`, `next_ready_card`
- [x] API: GET `/banners`, PUT `/banners/{id}/red-cut`, POST `/banners/init` — all fire BackgroundTask
- [x] BackgroundTask uses own `AsyncSessionLocal` session (not request-scoped)
- [x] Ingestion script: idempotent, category tagging, async embed
- [x] Frontend: `banner.js` client with `initBannerPool`, `getBanners`, `redCutBanner`
- [x] Frontend: `GlassCard` image_url → uri source → require fallback → emoji fallback
- [x] Frontend: `LogsContext` exposes `token`; `HomeScreen` reads it from context
- [x] Frontend: `handleRedCut` calls real `redCutBanner`, appends returned `newCard`
