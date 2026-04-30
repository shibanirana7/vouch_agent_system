"""
Backfill existing PurchaseRecord.opinion_text rows into SharedMemory (pgvector).
Run once from the project root:
    python experiments/backfill_shared_memory.py
"""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))


def load_dotenv(path: Path) -> None:
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


load_dotenv(ROOT / ".env")

from sqlalchemy import select
from vouch.database import AsyncSessionLocal
from vouch.models.purchase import PurchaseRecord
from vouch.data.catalog import PRODUCT_CATALOG
from vouch.memory.shared_memory import SharedMemory

CATALOG_BY_NAME: dict[str, dict] = {p["name"].lower(): p for p in PRODUCT_CATALOG}


async def load_records() -> list:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PurchaseRecord).where(PurchaseRecord.opinion_text.isnot(None))
        )
        return result.scalars().all()


def backfill() -> None:
    records = asyncio.run(load_records())
    print(f"Found {len(records)} purchase records with opinion_text")
    if not records:
        print("Nothing to backfill.")
        return

    shared = SharedMemory()
    ok = 0
    skipped = 0
    for r in records:
        if not r.opinion_text or not r.opinion_text.strip():
            skipped += 1
            continue
        product = CATALOG_BY_NAME.get(r.product_name.lower(), {})
        category = product.get("category", "general")
        rating = r.satisfaction_score if r.satisfaction_score is not None else 3
        try:
            shared.contribute_review(
                agent_id=r.agent_id,
                product=r.product_name,
                category=category,
                review_text=r.opinion_text,
                rating=rating,
            )
            print(f"  [OK] [{r.agent_id[:8]}] {r.product_name!r} ({category})")
            ok += 1
        except Exception as e:
            print(f"  [FAIL] [{r.agent_id[:8]}] {r.product_name!r}: {e}")
            skipped += 1

    print(f"\nDone: {ok} embedded, {skipped} skipped.")


if __name__ == "__main__":
    backfill()
