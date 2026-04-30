"""
Autonomous agent tick — proactive behaviors that run without user prompting.

POST /agents/{agent_id}/tick        run one agent (manual or scheduler)
POST /agents/tick-all               run all is_autonomous=True agents sequentially (Cloud Scheduler target)
POST /agents/tick-all-parallel      run all is_autonomous=True agents concurrently (asyncio.gather)

Each tick:
  1. Wishlist refill: checks for products due for replacement, queries the trust
     network for better alternatives, creates actionable restock notifications.
  2. Peer discovery: embeds the agent's preference profile, finds other agents
     with similar tastes via pgvector similarity, sends connection requests and
     actionable add_friend notifications.
"""
import asyncio
import hashlib
import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db, AsyncSessionLocal
from ..models.agent import ShoppingAgent
from ..models.connection_request import ConnectionRequest
from ..models.notification import Notification
from ..models.trust import TrustRelationship
from ..models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agents", tags=["autonomous"])


# ── Shared notification helper ────────────────────────────────────────────────

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
    existing = await db.execute(
        select(Notification).where(Notification.source_hash == source_hash)
    )
    existing_notif = existing.scalar_one_or_none()
    if existing_notif:
        if existing_notif.action_type is None and action_type is not None:
            existing_notif.action_type = action_type
            existing_notif.action_payload = action_payload
        return
    db.add(Notification(
        agent_id=agent_id,
        type=type_,
        title=title,
        body=body,
        source_hash=source_hash,
        action_type=action_type,
        action_payload=action_payload,
    ))


# ── Wishlist refill + peer query ──────────────────────────────────────────────

async def _run_wishlist_refill(agent_id: str, db: AsyncSession) -> int:
    from ..mcp_server.handlers import check_and_refill_wishlist, query_trust_network

    added = await check_and_refill_wishlist(agent_id)
    for product_name in added:
        try:
            recs = await query_trust_network(agent_id=agent_id, category="general", query=product_name)
        except Exception:
            recs = []

        body = f"You're due to restock {product_name}."
        rec_product = product_name
        if recs:
            top = recs[0]
            rec_product = top.get("product", product_name)
            body += f" Your network recommends: {rec_product}."

        source_hash = hashlib.sha256(f"refill:{agent_id}:{product_name}".encode()).hexdigest()
        await _upsert_notification(
            agent_id=agent_id,
            type_="restock_due",
            title=f"Time to restock: {product_name}",
            body=body,
            source_hash=source_hash,
            db=db,
            action_type="add_to_wishlist",
            action_payload={
                "product_name": rec_product,
                "description": body,
                "is_recurring": True,
            },
        )

    if added:
        await db.commit()
    return len(added)


# ── Peer discovery ────────────────────────────────────────────────────────────

async def _run_peer_discovery(agent_id: str, db: AsyncSession) -> int:
    from ..memory.store import find_similar_agents

    # find_similar_agents is sync (psycopg2). Run in a thread-pool executor so it
    # does not block the asyncio event loop — this is the key fix that enables
    # genuine parallelism in tick-all-parallel via asyncio.gather.
    candidates = await asyncio.get_event_loop().run_in_executor(
        None, find_similar_agents, agent_id, 5, 0.65
    )
    if not candidates:
        return 0

    # Agents already connected
    trust_result = await db.execute(
        select(TrustRelationship.to_agent_id).where(TrustRelationship.from_agent_id == agent_id)
    )
    connected = {row[0] for row in trust_result.all()}

    # Agents with a pending outgoing request
    req_result = await db.execute(
        select(ConnectionRequest.to_agent_id).where(
            ConnectionRequest.from_agent_id == agent_id,
            ConnectionRequest.status == "pending",
        )
    )
    pending = {row[0] for row in req_result.all()}
    exclude = connected | pending | {agent_id}

    sender_row = await db.execute(
        select(User).join(ShoppingAgent, ShoppingAgent.user_id == User.id)
        .where(ShoppingAgent.id == agent_id)
    )
    sender_user = sender_row.scalar_one_or_none()
    sender_name = sender_user.name if sender_user else "A shopper"

    sent = 0
    for candidate_id, score in candidates:
        if candidate_id in exclude:
            continue

        req = ConnectionRequest(
            from_agent_id=agent_id,
            to_agent_id=candidate_id,
            message=f"{sender_name}'s agent found you have similar taste ({score:.0%} match).",
            similarity_score=score,
        )
        db.add(req)
        await db.flush()

        source_hash = hashlib.sha256(f"conn_req:{agent_id}:{candidate_id}".encode()).hexdigest()
        await _upsert_notification(
            agent_id=candidate_id,
            type_="connection_request",
            title=f"{sender_name} wants to connect",
            body=f"You share {score:.0%} taste overlap. Accept to share reviews and get tailored recommendations.",
            source_hash=source_hash,
            db=db,
            action_type="add_friend",
            action_payload={"connection_request_id": req.id, "from_agent_id": agent_id},
        )
        exclude.add(candidate_id)
        sent += 1

    if sent:
        await db.commit()
    return sent


# ── Single-agent tick (shared by all endpoints) ───────────────────────────────

async def _tick_one(agent_id: str) -> dict:
    """Run both behaviors for one agent. Used by tick-all and tick-all-parallel."""
    try:
        async with AsyncSessionLocal() as db:
            refills = await _run_wishlist_refill(agent_id, db)
            discovered = await _run_peer_discovery(agent_id, db)
        return {"agent_id": agent_id, "refills": refills, "discovered": discovered}
    except Exception:
        logger.exception("[%s] tick error", agent_id[:8])
        return {"agent_id": agent_id, "error": "tick failed"}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/{agent_id}/tick")
async def agent_tick(agent_id: str, db: AsyncSession = Depends(get_db)):
    """Run all autonomous behaviors for a single agent."""
    result = await db.execute(select(ShoppingAgent).where(ShoppingAgent.id == agent_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Agent not found")

    refills = await _run_wishlist_refill(agent_id, db)
    discovered = await _run_peer_discovery(agent_id, db)

    logger.info("[%s] TICK refills=%d discovered=%d", agent_id[:8], refills, discovered)
    return {"agent_id": agent_id, "refills_added": refills, "peers_discovered": discovered}


@router.post("/tick-all")
async def tick_all_agents():
    """Cloud Scheduler target: run tick for every is_autonomous agent concurrently.

    Uses asyncio.gather so all agents run in parallel — wall time is bounded by
    the slowest single agent rather than growing linearly with agent count.
    find_similar_agents (sync psycopg2) is wrapped in run_in_executor so it
    does not block the event loop during gather.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ShoppingAgent).where(ShoppingAgent.is_autonomous == True)  # noqa: E712
        )
        agents = result.scalars().all()

    t0 = time.monotonic()
    raw_results = await asyncio.gather(*[_tick_one(a.id) for a in agents], return_exceptions=True)
    elapsed = time.monotonic() - t0

    results = []
    for r in raw_results:
        if isinstance(r, Exception):
            results.append({"error": str(r)})
        else:
            results.append(r)

    logger.info("TICK-ALL n=%d elapsed=%.2fs", len(results), elapsed)
    return {"ticked": len(results), "elapsed_s": round(elapsed, 2), "results": results}


@router.post("/tick-all-parallel")
async def tick_all_agents_parallel():
    """Parallel tick: all agents run concurrently via asyncio.gather.

    find_similar_agents (sync psycopg2) is wrapped in run_in_executor so it
    runs in a thread pool rather than blocking the event loop. Wall time is
    bounded by the slowest single agent instead of growing linearly — O(1) vs O(n).

    Tradeoff: concurrent DB writes require NullPool (already configured) and
    may increase DB connection count momentarily to n × 2 (read + write per agent).
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ShoppingAgent).where(ShoppingAgent.is_autonomous == True)  # noqa: E712
        )
        agents = result.scalars().all()

    t0 = time.monotonic()
    raw_results = await asyncio.gather(*[_tick_one(a.id) for a in agents], return_exceptions=True)
    elapsed = time.monotonic() - t0

    results = []
    for r in raw_results:
        if isinstance(r, Exception):
            results.append({"error": str(r)})
        else:
            results.append(r)

    logger.info("TICK-ALL-PARALLEL n=%d elapsed=%.2fs", len(results), elapsed)
    return {"ticked": len(results), "elapsed_s": round(elapsed, 2), "results": results}
