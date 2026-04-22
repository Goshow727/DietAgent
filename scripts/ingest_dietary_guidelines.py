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
