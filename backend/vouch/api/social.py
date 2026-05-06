from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_db
from ..models.trust import TrustRelationship, TRUST_WEIGHTS
from ..models.agent import ShoppingAgent
from ..models.user import User
from ..models.consultation import AgentConsultation
from ..models.connection_request import ConnectionRequest
from ..schemas.social import TrustCreate, TrustUpdate, TrustRelationshipOut
from ..trust.graph import TrustNetwork
from ..memory.shared_memory import SharedMemory

router = APIRouter(prefix="/social", tags=["social"])


@router.post("/trust", response_model=TrustRelationshipOut, status_code=201)
async def create_trust(payload: TrustCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(TrustRelationship).where(
            TrustRelationship.from_agent_id == payload.from_agent_id,
            TrustRelationship.to_agent_id == payload.to_agent_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Trust relationship already exists")

    rel = TrustRelationship(
        from_agent_id=payload.from_agent_id,
        to_agent_id=payload.to_agent_id,
        trust_level=payload.trust_level,
        trust_weight=TRUST_WEIGHTS[payload.trust_level],
    )
    db.add(rel)
    await db.commit()
    await db.refresh(rel)
    return rel


@router.patch("/trust/{from_agent_id}/{to_agent_id}", response_model=TrustRelationshipOut)
async def update_trust(
    from_agent_id: str, to_agent_id: str, payload: TrustUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(TrustRelationship).where(
            TrustRelationship.from_agent_id == from_agent_id,
            TrustRelationship.to_agent_id == to_agent_id,
        )
    )
    rel = result.scalar_one_or_none()
    if not rel:
        raise HTTPException(status_code=404, detail="Trust relationship not found")
    rel.trust_level = payload.trust_level
    rel.trust_weight = TRUST_WEIGHTS[payload.trust_level]
    await db.commit()
    await db.refresh(rel)
    return rel


@router.delete("/trust/{from_agent_id}/{to_agent_id}", status_code=204)
async def delete_trust(from_agent_id: str, to_agent_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TrustRelationship).where(
            TrustRelationship.from_agent_id == from_agent_id,
            TrustRelationship.to_agent_id == to_agent_id,
        )
    )
    rel = result.scalar_one_or_none()
    if not rel:
        raise HTTPException(status_code=404, detail="Trust relationship not found")
    await db.delete(rel)
    await db.commit()


@router.get("/trust/{agent_id}", response_model=list[TrustRelationshipOut])
async def get_trust_network(agent_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TrustRelationship)
        .where(TrustRelationship.from_agent_id == agent_id)
        .order_by(TrustRelationship.trust_weight.desc())
    )
    return result.scalars().all()


@router.get("/profile/{agent_id}")
async def get_agent_profile(agent_id: str, db: AsyncSession = Depends(get_db)):
    """Return a friend's public profile: name and all their reviews."""
    result = await db.execute(
        select(ShoppingAgent, User)
        .join(User, User.id == ShoppingAgent.user_id)
        .where(ShoppingAgent.id == agent_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Agent not found")
    _, user = row
    reviews = SharedMemory().get_own_reviews(agent_id)
    return {"agent_id": agent_id, "name": user.name, "reviews": reviews}


@router.get("/friend-reviews/{agent_id}")
async def get_friend_reviews(agent_id: str, db: AsyncSession = Depends(get_db)):
    """Return all reviews written by agents in this agent's trust network."""
    network = TrustNetwork(agent_id=agent_id, db=db)
    trusted = await network.get_trusted_agents()
    if not trusted:
        return []
    trusted_ids = [aid for aid, _ in trusted]
    weight_map = {aid: weight for aid, weight in trusted}
    reviews = SharedMemory().get_reviews_by_agents(trusted_ids)
    for r in reviews:
        r["trust_weight"] = weight_map.get(r.get("agent_id", ""), 0.0)
    reviews.sort(key=lambda r: r.get("trust_weight", 0), reverse=True)
    return reviews


class ConsultRequest(BaseModel):
    from_agent_id: str
    query: str


@router.post("/consult/{to_agent_id}")
async def consult_agent(to_agent_id: str, payload: ConsultRequest, db: AsyncSession = Depends(get_db)):
    """Agent-to-agent consultation: ask another agent's AI for a recommendation.

    The target agent responds based on its own preferences and purchase history only
    (no recursive trust queries). The calling agent weights the response by trust level.
    """
    # Verify the target agent exists
    result = await db.execute(select(ShoppingAgent).where(ShoppingAgent.id == to_agent_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Agent not found")

    # Verify a trust relationship exists (only trusted agents can consult each other)
    trust_result = await db.execute(
        select(TrustRelationship).where(
            TrustRelationship.from_agent_id == payload.from_agent_id,
            TrustRelationship.to_agent_id == to_agent_id,
        )
    )
    rel = trust_result.scalar_one_or_none()
    if not rel:
        raise HTTPException(status_code=403, detail="No trust relationship with this agent")

    from ..agents.shopping_agent import chat
    from ..models.consultation import AgentConsultation

    response = await chat(agent_id=to_agent_id, message=payload.query, is_consultation=True)

    record = AgentConsultation(
        from_agent_id=payload.from_agent_id,
        to_agent_id=to_agent_id,
        query=payload.query,
        response=response,
        trust_weight=rel.trust_weight,
    )
    db.add(record)
    await db.commit()

    return {
        "from_agent_id": payload.from_agent_id,
        "to_agent_id": to_agent_id,
        "trust_weight": rel.trust_weight,
        "response": response,
    }


@router.get("/consultations/{agent_id}")
async def get_consultations(agent_id: str, db: AsyncSession = Depends(get_db)):
    """Return all agent-to-agent consultation messages involving this agent (sent or received)."""
    from sqlalchemy import or_
    result = await db.execute(
        select(AgentConsultation)
        .where(
            or_(
                AgentConsultation.from_agent_id == agent_id,
                AgentConsultation.to_agent_id == agent_id,
            )
        )
        .order_by(AgentConsultation.created_at.desc())
    )
    consultations = result.scalars().all()
    return [
        {
            "id": c.id,
            "from_agent_id": c.from_agent_id,
            "to_agent_id": c.to_agent_id,
            "query": c.query,
            "response": c.response,
            "trust_weight": c.trust_weight,
            "created_at": c.created_at.isoformat(),
            "direction": "sent" if c.from_agent_id == agent_id else "received",
            "a2a_request": c.a2a_request,
            "a2a_response": c.a2a_response,
        }
        for c in consultations
    ]


@router.get("/connection-requests/{agent_id}")
async def get_connection_requests(agent_id: str, db: AsyncSession = Depends(get_db)):
    """Return pending connection requests sent to this agent by other agents."""
    result = await db.execute(
        select(ConnectionRequest, User)
        .join(ShoppingAgent, ShoppingAgent.id == ConnectionRequest.from_agent_id)
        .join(User, User.id == ShoppingAgent.user_id)
        .where(
            ConnectionRequest.to_agent_id == agent_id,
            ConnectionRequest.status == "pending",
        )
        .order_by(ConnectionRequest.created_at.desc())
    )
    rows = result.all()
    return [
        {
            "id": req.id,
            "from_agent_id": req.from_agent_id,
            "from_name": user.name,
            "message": req.message,
            "similarity_score": req.similarity_score,
            "created_at": req.created_at.isoformat(),
        }
        for req, user in rows
    ]


@router.get("/sent-requests/{agent_id}")
async def get_sent_requests(agent_id: str, db: AsyncSession = Depends(get_db)):
    """Return pending connection requests this agent has sent to others."""
    result = await db.execute(
        select(ConnectionRequest, User)
        .join(ShoppingAgent, ShoppingAgent.id == ConnectionRequest.to_agent_id)
        .join(User, User.id == ShoppingAgent.user_id)
        .where(
            ConnectionRequest.from_agent_id == agent_id,
            ConnectionRequest.status == "pending",
        )
        .order_by(ConnectionRequest.created_at.desc())
    )
    rows = result.all()
    return [
        {
            "id": req.id,
            "to_agent_id": req.to_agent_id,
            "to_name": user.name,
            "message": req.message,
            "similarity_score": req.similarity_score,
            "created_at": req.created_at.isoformat(),
        }
        for req, user in rows
    ]


class RespondToRequest(BaseModel):
    action: Literal["accept", "deny"]
    trust_level: str = "acquaintance"


@router.patch("/connection-requests/{request_id}/respond")
async def respond_to_connection_request(
    request_id: str, payload: RespondToRequest, db: AsyncSession = Depends(get_db)
):
    """Accept or deny a pending connection request.

    Accepting creates a trust relationship from this agent to the requester
    at the chosen trust level.
    """
    result = await db.execute(
        select(ConnectionRequest).where(ConnectionRequest.id == request_id)
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "pending":
        raise HTTPException(status_code=409, detail="Request already resolved")

    if payload.trust_level not in TRUST_WEIGHTS:
        raise HTTPException(status_code=422, detail="Invalid trust level")

    req.status = payload.action

    if payload.action == "accept":
        # Create B → A (accepter trusts requester)
        existing = await db.execute(
            select(TrustRelationship).where(
                TrustRelationship.from_agent_id == req.to_agent_id,
                TrustRelationship.to_agent_id == req.from_agent_id,
            )
        )
        if not existing.scalar_one_or_none():
            db.add(TrustRelationship(
                from_agent_id=req.to_agent_id,
                to_agent_id=req.from_agent_id,
                trust_level=payload.trust_level,
                trust_weight=TRUST_WEIGHTS[payload.trust_level],
            ))

        # Create A → B (requester trusts accepter) — makes the connection mutual
        reverse = await db.execute(
            select(TrustRelationship).where(
                TrustRelationship.from_agent_id == req.from_agent_id,
                TrustRelationship.to_agent_id == req.to_agent_id,
            )
        )
        if not reverse.scalar_one_or_none():
            db.add(TrustRelationship(
                from_agent_id=req.from_agent_id,
                to_agent_id=req.to_agent_id,
                trust_level=payload.trust_level,
                trust_weight=TRUST_WEIGHTS[payload.trust_level],
            ))

    await db.commit()
    return {"status": req.status}


@router.get("/recommendations/{agent_id}/{category}")
async def get_trusted_recommendations(
    agent_id: str, category: str, query: str = "", db: AsyncSession = Depends(get_db)
):
    network = TrustNetwork(agent_id=agent_id, db=db)
    recs = await network.get_recommendations(category=category, query=query or category)
    return {"agent_id": agent_id, "category": category, "recommendations": recs}
