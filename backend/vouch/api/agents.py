import hashlib
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_db
from ..models.agent import ShoppingAgent
from ..models.wishlist import WishlistItem
from ..models.purchase import PurchaseRecord
from ..models.notification import Notification
from ..models.trust import TrustRelationship
from ..models.user import User
from ..schemas.agent import AgentOut, ChatRequest, ChatResponse
from ..schemas.shopping import WishlistItemOut, WishlistItemCreate, PurchaseRecordOut
from ..agents.shopping_agent import chat
from ..mcp_server.handlers import generate_synthetic_history

router = APIRouter(prefix="/agents", tags=["agents"])


async def _get_agent_or_404(agent_id: str, db: AsyncSession) -> ShoppingAgent:
    result = await db.execute(select(ShoppingAgent).where(ShoppingAgent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.get("/{agent_id}", response_model=AgentOut)
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    return await _get_agent_or_404(agent_id, db)


@router.post("/{agent_id}/chat", response_model=ChatResponse)
async def agent_chat(agent_id: str, payload: ChatRequest, db: AsyncSession = Depends(get_db)):
    await _get_agent_or_404(agent_id, db)
    history = [{"role": m.role, "content": m.content} for m in payload.history]
    result = await chat(agent_id=agent_id, message=payload.message, history=history)
    return ChatResponse(agent_id=agent_id, **result)


@router.get("/{agent_id}/wishlist", response_model=list[WishlistItemOut])
async def get_wishlist(agent_id: str, db: AsyncSession = Depends(get_db)):
    await _get_agent_or_404(agent_id, db)
    result = await db.execute(select(WishlistItem).where(WishlistItem.agent_id == agent_id))
    return result.scalars().all()


@router.delete("/{agent_id}/wishlist/{item_id}", status_code=204)
async def remove_wishlist_item(agent_id: str, item_id: str, db: AsyncSession = Depends(get_db)):
    await _get_agent_or_404(agent_id, db)
    result = await db.execute(
        select(WishlistItem).where(WishlistItem.id == item_id, WishlistItem.agent_id == agent_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Wishlist item not found")
    await db.delete(item)
    await db.commit()


@router.post("/{agent_id}/wishlist", response_model=WishlistItemOut, status_code=201)
async def add_wishlist_item(
    agent_id: str, payload: WishlistItemCreate, db: AsyncSession = Depends(get_db)
):
    await _get_agent_or_404(agent_id, db)
    item = WishlistItem(agent_id=agent_id, **payload.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/{agent_id}/preferences")
async def get_preferences(agent_id: str, db: AsyncSession = Depends(get_db)):
    await _get_agent_or_404(agent_id, db)
    from ..memory.agent_memory import AgentMemory
    mem = AgentMemory(agent_id)
    prefs = mem.retrieve_preferences("beauty makeup skincare style", n=20)
    history = mem.retrieve_relevant_history("purchase history", n=20)
    return {"preferences": prefs, "purchase_history_summary": history}


@router.get("/{agent_id}/purchases", response_model=list[PurchaseRecordOut])
async def get_purchases(agent_id: str, db: AsyncSession = Depends(get_db)):
    await _get_agent_or_404(agent_id, db)
    result = await db.execute(
        select(PurchaseRecord)
        .where(PurchaseRecord.agent_id == agent_id)
        .order_by(PurchaseRecord.purchased_at.desc())
    )
    return result.scalars().all()


@router.patch("/{agent_id}/autonomous", status_code=200)
async def set_autonomous(agent_id: str, enabled: bool, db: AsyncSession = Depends(get_db)):
    """Enable or disable autonomous background behavior for this agent."""
    agent = await _get_agent_or_404(agent_id, db)
    agent.is_autonomous = enabled
    await db.commit()
    return {"agent_id": agent_id, "is_autonomous": enabled}


@router.post("/{agent_id}/reseed", status_code=200)
async def reseed_history(agent_id: str, db: AsyncSession = Depends(get_db)):
    """Top up an existing agent's purchase history to 20 items."""
    await _get_agent_or_404(agent_id, db)
    await generate_synthetic_history(agent_id, n=20)
    return {"status": "ok"}


@router.get("/{agent_id}/reviews")
async def get_reviews(agent_id: str, db: AsyncSession = Depends(get_db)):
    """Return all reviews this agent has written, keyed by product name."""
    await _get_agent_or_404(agent_id, db)
    from ..memory.shared_memory import SharedMemory
    reviews = SharedMemory().get_own_reviews(agent_id)
    return {r["product"].lower(): {"text": r["text"], "rating": r["rating"]} for r in reviews}


# ── Notifications (event loop) ─────────────────────────────────────────────────

@router.get("/{agent_id}/notifications")
async def get_notifications(agent_id: str, db: AsyncSession = Depends(get_db)):
    """Return all undismissed notifications for this agent.

    Also runs a background check for new events (price drops, friend reviews)
    so agents feel like they're running in a persistent loop.
    """
    await _get_agent_or_404(agent_id, db)
    await _run_event_checks(agent_id, db)
    result = await db.execute(
        select(Notification)
        .where(Notification.agent_id == agent_id, Notification.dismissed == False)  # noqa: E712
        .order_by(Notification.created_at.desc())
    )
    notifs = result.scalars().all()
    return [
        {
            "id": n.id,
            "type": n.type,
            "title": n.title,
            "body": n.body,
            "action_type": n.action_type,
            "action_payload": n.action_payload,
            "created_at": n.created_at.isoformat(),
        }
        for n in notifs
    ]


@router.patch("/{agent_id}/notifications/{notification_id}/dismiss", status_code=204)
async def dismiss_notification(
    agent_id: str, notification_id: str, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.agent_id == agent_id,
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    notif.dismissed = True
    await db.commit()


async def _run_event_checks(agent_id: str, db: AsyncSession) -> None:
    """Check for price drops and new friend reviews; persist as notifications."""
    try:
        await _check_price_drops(agent_id, db)
        await _check_friend_reviews(agent_id, db)
    except Exception:
        pass  # event checks must never break the caller


async def _upsert_notification(
    agent_id: str,
    type_: str,
    title: str,
    body: str,
    source_hash: str,
    db: AsyncSession,
    action_type: str | None = None,
    action_payload: dict | None = None,
) -> None:
    """Create a notification only if one with this source_hash doesn't already exist."""
    existing = await db.execute(
        select(Notification).where(
            Notification.agent_id == agent_id,
            Notification.source_hash == source_hash,
        )
    )
    if existing.scalar_one_or_none():
        return
    notif = Notification(
        agent_id=agent_id,
        type=type_,
        title=title,
        body=body,
        source_hash=source_hash,
        action_type=action_type,
        action_payload=action_payload,
    )
    db.add(notif)


async def _check_price_drops(agent_id: str, db: AsyncSession) -> None:
    from ..mcp_server.handlers import search_products
    result = await db.execute(
        select(WishlistItem).where(
            WishlistItem.agent_id == agent_id,
            WishlistItem.target_price.isnot(None),
        )
    )
    items = result.scalars().all()
    for item in items:
        try:
            matches = await search_products(
                query=item.product_name,
                max_price=float(item.target_price),
                category="general",
            )
            if not matches:
                continue
            best = matches[0]
            savings = round(float(item.target_price) - best["price"], 2)
            source_hash = hashlib.sha256(f"price_drop:{item.id}".encode()).hexdigest()
            body = f"{best['name']} is available at ${best['price']}"
            if savings > 0:
                body += f" — ${savings} under your target price"
            await _upsert_notification(
                agent_id=agent_id,
                type_="price_drop",
                title=f"{item.product_name} is within budget",
                body=body,
                source_hash=source_hash,
                db=db,
            )
        except Exception:
            pass
    await db.commit()


async def _check_friend_reviews(agent_id: str, db: AsyncSession) -> None:
    from ..memory.shared_memory import SharedMemory
    friends_result = await db.execute(
        select(TrustRelationship, User)
        .join(ShoppingAgent, ShoppingAgent.id == TrustRelationship.to_agent_id)
        .join(User, User.id == ShoppingAgent.user_id)
        .where(TrustRelationship.from_agent_id == agent_id)
    )
    friend_rows = friends_result.all()
    if not friend_rows:
        return

    shared = SharedMemory()
    for rel, friend_user in friend_rows:
        friend_id = rel.to_agent_id
        reviews = shared.get_own_reviews(friend_id)
        for review in reviews:
            product = review.get("product", "a product")
            text = review.get("text", "")
            source_hash = hashlib.sha256(
                f"friend_review:{friend_id}:{product}".encode()
            ).hexdigest()
            # Strip the [category] prefix from the text for a clean notification body
            clean = text.split(": ", 1)[-1] if ": " in text else text
            await _upsert_notification(
                agent_id=agent_id,
                type_="friend_review",
                title=f"{friend_user.name} reviewed {product}",
                body=clean[:200],
                source_hash=source_hash,
                db=db,
                action_type="add_to_wishlist",
                action_payload={"product_name": product, "description": clean[:200], "is_recurring": False},
            )
    await db.commit()


# ── Legacy proactive-check (kept for backward compat) ─────────────────────────

@router.post("/{agent_id}/proactive-check")
async def proactive_wishlist_check(agent_id: str, db: AsyncSession = Depends(get_db)):
    """Delegates to /notifications which now runs checks and persists results."""
    await _get_agent_or_404(agent_id, db)
    await _run_event_checks(agent_id, db)
    result = await db.execute(
        select(Notification).where(
            Notification.agent_id == agent_id,
            Notification.type == "price_drop",
            Notification.dismissed == False,  # noqa: E712
        )
    )
    notifs = result.scalars().all()
    alerts = []
    for n in notifs:
        alerts.append({
            "wishlist_item_id": n.source_hash,
            "product_name": n.title.replace(" is within budget", ""),
            "target_price": 0,
            "found_at": 0,
            "found_product": n.body,
            "savings": 0,
        })
    return {"alerts": alerts}
