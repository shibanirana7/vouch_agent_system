from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import bcrypt

from ..database import get_db
from ..models.user import User
from ..models.agent import ShoppingAgent
from ..schemas.user import UserCreate, UserOut, LoginRequest
from ..mcp_server.handlers import generate_synthetic_history


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserOut, status_code=201)
async def create_user(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        name=payload.name,
        email=payload.email,
        password_hash=_hash_password(payload.password) if payload.password else None,
        is_agent_user=payload.is_agent_user,
    )
    db.add(user)
    await db.flush()

    agent = ShoppingAgent(
        user_id=user.id,
        chroma_collection_id=f"agent_{user.id}",
    )
    db.add(agent)
    await db.commit()
    await db.refresh(user)
    await db.refresh(agent)

    # Seed synthetic purchase history for new agents
    await generate_synthetic_history(agent.id)

    out = UserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        is_agent_user=user.is_agent_user,
        created_at=user.created_at,
        agent_id=agent.id,
    )
    return out


@router.post("/login", response_model=UserOut)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if not user or not user.password_hash or not _verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    agent_result = await db.execute(select(ShoppingAgent).where(ShoppingAgent.user_id == user.id))
    agent = agent_result.scalar_one_or_none()

    return UserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        is_agent_user=user.is_agent_user,
        created_at=user.created_at,
        agent_id=agent.id if agent else None,
    )


@router.get("/search")
async def search_users(q: str = "", db: AsyncSession = Depends(get_db)):
    """Search users by name. Returns name + agent_id for each match."""
    if not q:
        return []
    result = await db.execute(
        select(User, ShoppingAgent)
        .join(ShoppingAgent, ShoppingAgent.user_id == User.id)
        .where(User.name.ilike(f"%{q}%"))
        .limit(10)
    )
    return [{"name": user.name, "agent_id": agent.id} for user, agent in result.all()]


@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    agent_result = await db.execute(select(ShoppingAgent).where(ShoppingAgent.user_id == user_id))
    agent = agent_result.scalar_one_or_none()

    return UserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        is_agent_user=user.is_agent_user,
        created_at=user.created_at,
        agent_id=agent.id if agent else None,
    )
