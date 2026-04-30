import asyncio
import hashlib
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_db
from ..models.agent import ShoppingAgent
from ..models.purchase import PurchaseRecord
from ..schemas.shopping import (
    PurchaseCreate, PurchaseRecordOut,
    ConfirmWishlistPurchase, RatePurchase, DecideRequest,
)
from ..agents.shopping_agent import chat
from ..mcp_server.handlers import (
    record_purchase, confirm_wishlist_purchase, rate_recommendation, contribute_review
)

router = APIRouter(prefix="/shopping", tags=["shopping"])


async def _extract_from_opinion(product_name: str, opinion: str) -> dict:
    """LLM extracts structured insights from a free-form product opinion.

    Returns dict with: sentiment_score (1-5), category, review_text, useful_for, preference_signals.
    Falls back gracefully if the LLM response can't be parsed.
    """
    from ..agents.llm import get_llm
    llm = get_llm()
    response = await llm.ainvoke([
        SystemMessage(content=(
            "A user shared their opinion about a product. Extract structured information.\n"
            "Reply in this EXACT format (no extra text, no markdown):\n"
            "SENTIMENT: <integer 1-5, where 1=very negative, 3=neutral, 5=very positive>\n"
            "CATEGORY: <one word from: foundation concealer moisturizer cleanser serum mascara lipstick eyeshadow blush bronzer highlighter primer toner sunscreen brush general>\n"
            "REVIEW: <concise 1-2 sentence review written in third person for friends to read>\n"
            "USEFUL_FOR: <brief phrase describing who benefits most from this product>\n"
            "PREFERENCES: <pipe-separated list of 1-3 preference signals gleaned about the user; include brand preferences if evident, e.g. 'prefers Charlotte Tilbury | avoids heavy coverage | values cruelty-free brands'>"
        )),
        HumanMessage(content=f"Product: {product_name}\nOpinion: {opinion}"),
    ])
    content = response.content if hasattr(response, "content") else str(response)
    parsed: dict = {}
    for line in content.strip().splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            parsed[key.strip().upper()] = val.strip()

    return {
        "sentiment_score": _safe_int(parsed.get("SENTIMENT", "3"), default=3, min_val=1, max_val=5),
        "category": parsed.get("CATEGORY", "general").lower().split()[0],
        "review_text": parsed.get("REVIEW", opinion[:200]),
        "useful_for": parsed.get("USEFUL_FOR", ""),
        "preference_signals": [
            p.strip() for p in parsed.get("PREFERENCES", "").split("|") if p.strip()
        ],
    }


def _safe_int(val: str, default: int, min_val: int, max_val: int) -> int:
    try:
        return max(min_val, min(max_val, int(val)))
    except (ValueError, TypeError):
        return default


@router.post("/decide")
async def decide_purchase(payload: DecideRequest, db: AsyncSession = Depends(get_db)):
    """Ask the agent to make a purchase recommendation via the full LangGraph pipeline."""
    result = await db.execute(select(ShoppingAgent).where(ShoppingAgent.id == payload.agent_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Agent not found")
    response = await chat(agent_id=payload.agent_id, message=payload.query)
    return {"agent_id": payload.agent_id, "recommendation": response}


@router.post("/purchase", response_model=dict)
async def record_direct_purchase(payload: PurchaseCreate, db: AsyncSession = Depends(get_db)):
    """Record a purchase made directly (not from wishlist)."""
    result = await db.execute(select(ShoppingAgent).where(ShoppingAgent.id == payload.agent_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Agent not found")
    return await record_purchase(
        agent_id=payload.agent_id,
        product_name=payload.product_name,
        price=payload.price,
        category=payload.category,
        url=payload.url,
        was_recommended=payload.was_recommended,
        recommending_agent_id=payload.recommending_agent_id,
    )


@router.post("/confirm-wishlist-purchase", response_model=dict)
async def confirm_wishlist(payload: ConfirmWishlistPurchase):
    """Confirm a wishlist item was purchased."""
    return await confirm_wishlist_purchase(
        wishlist_item_id=payload.wishlist_item_id,
        actual_price=payload.actual_price,
    )


@router.post("/rate/{purchase_id}", response_model=dict)
async def rate_purchase(
    purchase_id: str,
    payload: RatePurchase,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Accept a free-form opinion about a purchase.
    The agent extracts: sentiment score, a review for friends, and preference signals.
    Preferences are saved to the agent's profile; the review is shared with the trust network.
    """
    if not payload.opinion.strip():
        raise HTTPException(status_code=422, detail="opinion must not be empty")

    purchase_result = await db.execute(
        select(PurchaseRecord).where(PurchaseRecord.id == purchase_id)
    )
    purchase = purchase_result.scalar_one_or_none()
    if not purchase:
        raise HTTPException(status_code=404, detail="Purchase not found")

    # Save the raw opinion immediately so it's never lost, even if LLM extraction fails
    await rate_recommendation(
        purchase_id=purchase_id,
        satisfaction_score=3,  # neutral default; overwritten below if extraction succeeds
        opinion_text=payload.opinion,
    )

    # LLM extraction — best-effort; opinion is already persisted above
    try:
        insights = await _extract_from_opinion(purchase.product_name, payload.opinion)
    except Exception:
        # Store raw opinion in shared memory and agent's own preferences
        await contribute_review(
            agent_id=purchase.agent_id,
            product=purchase.product_name,
            category="general",
            review_text=payload.opinion[:300],
            rating=3,
        )
        from ..memory.agent_memory import AgentMemory
        AgentMemory(purchase.agent_id).store_preference(
            f"My experience with {purchase.product_name}: {payload.opinion[:300]}"
        )
        return {"status": "opinion_saved", "sentiment_score": 3, "preferences_added": 0}

    # Update with extracted sentiment score
    await rate_recommendation(
        purchase_id=purchase_id,
        satisfaction_score=insights["sentiment_score"],
        opinion_text=payload.opinion,
    )

    # Store cleaned review in shared memory for friends
    await contribute_review(
        agent_id=purchase.agent_id,
        product=purchase.product_name,
        category=insights["category"],
        review_text=insights["review_text"]
        + (f" Particularly useful for: {insights['useful_for']}." if insights["useful_for"] else ""),
        rating=insights["sentiment_score"],
    )

    # Store gleaned preferences + the review itself in agent memory
    from ..memory.agent_memory import AgentMemory
    mem = AgentMemory(purchase.agent_id)
    for pref in insights["preference_signals"]:
        mem.store_preference(pref)
    review_note = insights["review_text"]
    if insights["useful_for"]:
        review_note += f" Particularly useful for: {insights['useful_for']}."
    mem.store_preference(f"My experience with {purchase.product_name}: {review_note}")

    # Background: update trust weights + push unsolicited rec to close friends if loved
    background_tasks.add_task(
        _update_taste_weights,
        purchase.agent_id,
        purchase.product_name,
        insights["sentiment_score"],
    )
    if insights["sentiment_score"] >= 4:
        background_tasks.add_task(
            _push_friend_recommendations,
            purchase.agent_id,
            purchase.product_name,
            insights["review_text"],
        )

    return {
        "status": "opinion_saved",
        "sentiment_score": insights["sentiment_score"],
        "preferences_added": len(insights["preference_signals"]),
    }


async def _update_taste_weights(agent_id: str, product_name: str, rating: int) -> None:
    try:
        from ..database import AsyncSessionLocal
        from ..trust.graph import TrustNetwork
        async with AsyncSessionLocal() as db:
            network = TrustNetwork(agent_id=agent_id, db=db)
            await network.update_taste_weight(product_name, rating)
    except Exception:
        pass


async def _push_friend_recommendations(
    agent_id: str, product_name: str, review_text: str
) -> None:
    """Notify close friends (trust_weight >= 0.7) when an agent loves a product."""
    try:
        from ..database import AsyncSessionLocal
        from ..models.trust import TrustRelationship
        from ..models.notification import Notification
        from ..models.user import User
        from ..models.agent import ShoppingAgent

        async with AsyncSessionLocal() as db:
            # Get sender's name
            sender_row = await db.execute(
                select(User).join(ShoppingAgent, ShoppingAgent.user_id == User.id)
                .where(ShoppingAgent.id == agent_id)
            )
            sender_user = sender_row.scalar_one_or_none()
            sender_name = sender_user.name if sender_user else agent_id[:8]

            # Get close friends
            friends_result = await db.execute(
                select(TrustRelationship).where(
                    TrustRelationship.from_agent_id == agent_id,
                    TrustRelationship.trust_weight >= 0.7,
                )
            )
            friends = friends_result.scalars().all()

            for friend_rel in friends:
                target_id = friend_rel.to_agent_id
                source_hash = hashlib.sha256(
                    f"friend_rec:{agent_id}:{product_name}:{target_id}".encode()
                ).hexdigest()

                existing = await db.execute(
                    select(Notification).where(
                        Notification.agent_id == target_id,
                        Notification.source_hash == source_hash,
                    )
                )
                if existing.scalar_one_or_none():
                    continue

                notif = Notification(
                    agent_id=target_id,
                    type="friend_recommendation",
                    title=f"{sender_name} loves {product_name}",
                    body=review_text,
                    source_hash=source_hash,
                )
                db.add(notif)

            await db.commit()
    except Exception:
        pass
