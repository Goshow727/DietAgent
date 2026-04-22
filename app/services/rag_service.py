from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.vector_doc import VectorDoc, EMBEDDING_DIM

_ALWAYS_INCLUDE = {"general"}


def derive_categories(
    avg_fat_pct: float,
    avg_protein_pct: float,
    days_without_burn: int,
    has_high_salt: bool,
) -> list[str]:
    cats: set[str] = set(_ALWAYS_INCLUDE)
    if avg_fat_pct > 35:
        cats.add("fats")
    if avg_protein_pct < 15:
        cats.add("protein")
    if days_without_burn >= 3:
        cats.add("exercise")
    if has_high_salt:
        cats.add("salt_sugar")
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
