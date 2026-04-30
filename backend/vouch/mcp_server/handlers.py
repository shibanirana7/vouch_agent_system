"""
Business logic for each MCP tool.
Handlers call the DB + memory layer directly.
A fresh DB session is opened per call since MCP tools run outside FastAPI's request lifecycle.
"""
import logging
import random
import uuid as _uuid
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)
from ..database import AsyncSessionLocal
from ..models.wishlist import WishlistItem
from ..models.purchase import PurchaseRecord
from ..memory.agent_memory import AgentMemory
from ..memory.shared_memory import SharedMemory
from ..trust.graph import TrustNetwork
from ..data.catalog import PRODUCT_CATALOG, REPLACEMENT_DAYS
from sqlalchemy import select


async def generate_synthetic_history(agent_id: str, n: int = 20) -> None:
    """
    Seed an agent with synthetic purchase history up to n items.
    If the agent already has purchases, only adds the delta to reach n total.
    Writes PurchaseRecord rows to the DB and embeds them in ChromaDB.
    Preferences are NOT pre-seeded — the agent learns them from conversations.
    """
    import random as _random

    async with AsyncSessionLocal() as db:
        existing_count_result = await db.execute(
            select(PurchaseRecord).where(PurchaseRecord.agent_id == agent_id)
        )
        existing = existing_count_result.scalars().all()
        existing_names = {r.product_name.lower() for r in existing}
        to_add = n - len(existing)

    if to_add <= 0:
        return

    available = [p for p in PRODUCT_CATALOG if p["name"].lower() not in existing_names]
    sampled = _random.sample(available, min(to_add, len(available)))

    async with AsyncSessionLocal() as db:
        for product in sampled:
            satisfaction = _random.randint(3, 5)
            purchased_at = datetime.utcnow() - timedelta(days=_random.randint(7, 365))
            record = PurchaseRecord(
                agent_id=agent_id,
                product_name=product["name"],
                url=product["url"],
                price=product["price"],
                was_recommended=False,
                satisfaction_score=satisfaction,
                purchased_at=purchased_at,
            )
            db.add(record)
        await db.commit()

    mem = AgentMemory(agent_id)
    for product in sampled:
        mem.store_purchase(
            product=product["name"],
            price=product["price"],
            category=product["category"],
            satisfaction=_random.randint(3, 5),
        )


# ── Product search ────────────────────────────────────────────────────────────

async def search_products(query: str, max_price: float, category: str) -> list[dict]:
    query_lower = query.lower()

    # When a specific category is requested, restrict pool to that category only.
    # This ensures "find me a mascara" never returns foundations.
    pool = [p for p in PRODUCT_CATALOG if p["price"] <= max_price]
    if category != "general":
        cat_pool = [p for p in pool if p["category"] == category]
        if cat_pool:
            pool = cat_pool

    # Rank by query relevance within the pool
    results = []
    for p in pool:
        name_match = any(w in p["name"].lower() for w in query_lower.split())
        brand_match = query_lower in p["brand"].lower()
        ingr_match = any(query_lower in i for i in p["ingredients"])
        qual_match = any(query_lower in q for q in p["qualities"])
        if name_match or brand_match or ingr_match or qual_match:
            results.append(p)

    results.sort(key=lambda x: x["price"])
    # If no query-specific matches, return the whole category pool (still correct type)
    return results[:6] if results else pool[:6] if pool else random.sample(PRODUCT_CATALOG, min(4, len(PRODUCT_CATALOG)))


# ── Trust network ─────────────────────────────────────────────────────────────

async def query_trust_network(agent_id: str, category: str, query: str) -> list[dict]:
    async with AsyncSessionLocal() as db:
        network = TrustNetwork(agent_id=agent_id, db=db)
        return await network.get_recommendations(category=category, query=query)


# ── Wishlist ──────────────────────────────────────────────────────────────────

async def add_to_wishlist(
    agent_id: str,
    product_name: str,
    description: str,
    target_price: float | None,
    is_recurring: bool,
    recurrence_interval_days: int | None,
    priority: int,
) -> dict:
    async with AsyncSessionLocal() as db:
        # Skip if already in wishlist
        existing = await db.execute(
            select(WishlistItem).where(
                WishlistItem.agent_id == agent_id,
                WishlistItem.product_name == product_name,
            )
        )
        if existing.scalar_one_or_none():
            return {"product_name": product_name, "status": "already_in_wishlist"}

        item = WishlistItem(
            agent_id=agent_id,
            product_name=product_name,
            description=description,
            target_price=target_price,
            is_recurring=is_recurring,
            recurrence_interval_days=recurrence_interval_days,
            priority=priority,
        )
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return {"id": item.id, "product_name": item.product_name, "status": "added"}


async def check_and_refill_wishlist(agent_id: str) -> list[str]:
    """
    Check each purchased product against its category replacement interval.
    Auto-adds items to the wishlist when they're due for replacement.
    Returns list of product names added (empty if nothing was due).
    """
    async with AsyncSessionLocal() as db:
        purchases_result = await db.execute(
            select(PurchaseRecord).where(PurchaseRecord.agent_id == agent_id)
        )
        purchases = purchases_result.scalars().all()

        wishlist_result = await db.execute(
            select(WishlistItem.product_name).where(WishlistItem.agent_id == agent_id)
        )
        existing_names = {name.lower() for name in wishlist_result.scalars().all()}

        added: list[str] = []
        for purchase in purchases:
            product = next(
                (p for p in PRODUCT_CATALOG if p["name"].lower() == purchase.product_name.lower()),
                None,
            )
            if not product:
                continue
            interval = REPLACEMENT_DAYS.get(product["category"])
            if not interval:
                continue
            if not purchase.purchased_at:
                continue
            days_since = (datetime.now(timezone.utc).replace(tzinfo=None) - purchase.purchased_at).days
            if days_since >= interval and purchase.product_name.lower() not in existing_names:
                item = WishlistItem(
                    agent_id=agent_id,
                    product_name=purchase.product_name,
                    description=f"Due for replacement — last bought {days_since} days ago",
                    is_recurring=True,
                    recurrence_interval_days=interval,
                    priority=2,
                )
                db.add(item)
                existing_names.add(purchase.product_name.lower())
                added.append(purchase.product_name)

        if added:
            await db.commit()

    return added


async def get_wishlist(agent_id: str) -> list[dict]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(WishlistItem).where(WishlistItem.agent_id == agent_id)
        )
        items = result.scalars().all()
        return [
            {
                "id": i.id,
                "product_name": i.product_name,
                "description": i.description,
                "target_price": i.target_price,
                "priority": i.priority,
                "is_recurring": i.is_recurring,
            }
            for i in items
        ]


async def confirm_wishlist_purchase(wishlist_item_id: str, actual_price: float | None = None) -> dict:
    """Move a wishlist item into purchase history."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(WishlistItem).where(WishlistItem.id == wishlist_item_id)
        )
        item = result.scalar_one_or_none()
        if not item:
            return {"error": "Wishlist item not found"}

        price = actual_price if actual_price is not None else (item.target_price or 0.0)
        record = PurchaseRecord(
            agent_id=item.agent_id,
            product_name=item.product_name,
            price=price,
            url="",
            was_recommended=False,
        )
        db.add(record)
        await db.delete(item)
        await db.commit()
        await db.refresh(record)

    # Embed in agent memory
    mem = AgentMemory(item.agent_id)
    mem.store_purchase(product=item.product_name, price=price, category="makeup")

    return {
        "status": "purchased",
        "purchase_id": record.id,
        "product_name": item.product_name,
        "price": price,
    }


# ── Purchases ─────────────────────────────────────────────────────────────────

async def record_purchase(
    agent_id: str,
    product_name: str,
    price: float,
    category: str,
    url: str,
    was_recommended: bool,
    recommending_agent_id: str | None,
) -> dict:
    async with AsyncSessionLocal() as db:
        record = PurchaseRecord(
            agent_id=agent_id,
            product_name=product_name,
            price=price,
            url=url,
            was_recommended=was_recommended,
            recommending_agent_id=recommending_agent_id,
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)

    mem = AgentMemory(agent_id)
    mem.store_purchase(product=product_name, price=price, category=category)
    return {"id": record.id, "status": "recorded"}


async def update_preference(agent_id: str, preference_text: str) -> dict:
    mem = AgentMemory(agent_id)
    mem.store_preference(preference_text)
    return {"status": "stored", "preference": preference_text}


async def rate_recommendation(purchase_id: str, satisfaction_score: int, opinion_text: str | None = None) -> dict:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PurchaseRecord).where(PurchaseRecord.id == purchase_id)
        )
        record = result.scalar_one_or_none()
        if not record:
            return {"error": "Purchase not found"}
        record.satisfaction_score = satisfaction_score
        if opinion_text is not None:
            record.opinion_text = opinion_text
        await db.commit()
        return {"status": "rated", "purchase_id": purchase_id, "score": satisfaction_score}


async def contribute_review(
    agent_id: str,
    product: str,
    category: str,
    review_text: str,
    rating: int = 3,
) -> dict:
    logger.info("[%s] SHARED_MEMORY contribute product=%r category=%r",
                agent_id[:8], product, category)
    try:
        shared = SharedMemory()
        shared.contribute_review(
            agent_id=agent_id,
            product=product,
            category=category,
            review_text=review_text,
            rating=rating,
        )
        logger.info("[%s] SHARED_MEMORY stored OK product=%r", agent_id[:8], product)
    except Exception:
        logger.exception("[%s] SHARED_MEMORY FAILED product=%r", agent_id[:8], product)
        raise
    return {"status": "review_stored", "product": product}
