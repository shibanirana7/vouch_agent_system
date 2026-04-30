import secrets
import bcrypt
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_db
from ..models.user import User
from ..models.agent import ShoppingAgent
from ..models.oauth import OAuthClient, OAuthAuthCode, OAuthToken

router = APIRouter(prefix="/oauth", tags=["oauth"])

VOUCH_URL = "https://vouch-backend-392847826435.us-central1.run.app"


# ── Token dependency ───────────────────────────────────────────────────────────

async def get_agent_from_token(
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    token_str = authorization.removeprefix("Bearer ")
    result = await db.execute(select(OAuthToken).where(OAuthToken.token == token_str))
    token = result.scalar_one_or_none()
    if not token:
        raise HTTPException(status_code=401, detail="Invalid token")
    if token.expires_at and token.expires_at < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Token expired")
    return token.agent_id


# ── Schemas ────────────────────────────────────────────────────────────────────

class AuthorizeRequest(BaseModel):
    client_id: str
    redirect_uri: str
    state: str = ""
    email: str
    password: str
    action: str  # "allow" | "deny"


class TokenRequest(BaseModel):
    grant_type: str
    code: str
    client_id: str
    client_secret: str
    redirect_uri: str


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/client-info")
async def client_info(client_id: str, redirect_uri: str, db: AsyncSession = Depends(get_db)):
    """React consent page calls this to get client name before showing the form."""
    result = await db.execute(select(OAuthClient).where(OAuthClient.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=400, detail="Unknown client_id")
    if client.redirect_uri != redirect_uri:
        raise HTTPException(status_code=400, detail="redirect_uri mismatch")
    return {"client_id": client.id, "client_name": client.name, "redirect_uri": redirect_uri}


@router.post("/authorize")
async def authorize(payload: AuthorizeRequest, db: AsyncSession = Depends(get_db)):
    """Validate credentials and issue an auth code (or deny). Returns redirect_url."""
    result = await db.execute(select(OAuthClient).where(OAuthClient.id == payload.client_id))
    client = result.scalar_one_or_none()
    if not client or client.redirect_uri != payload.redirect_uri:
        raise HTTPException(status_code=400, detail="Invalid client or redirect_uri")

    if payload.action == "deny":
        return {"redirect_url": f"{payload.redirect_uri}?error=access_denied&state={payload.state}"}

    # Verify user credentials
    user_result = await db.execute(select(User).where(User.email == payload.email))
    user = user_result.scalar_one_or_none()
    if not user or not user.password_hash or not bcrypt.checkpw(payload.password.encode(), user.password_hash.encode()):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    agent_result = await db.execute(select(ShoppingAgent).where(ShoppingAgent.user_id == user.id))
    agent = agent_result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="No agent found for this user")

    code = OAuthAuthCode(
        code=secrets.token_urlsafe(32),
        client_id=payload.client_id,
        user_id=user.id,
        agent_id=agent.id,
        expires_at=datetime.utcnow() + timedelta(minutes=10),
    )
    db.add(code)
    await db.commit()

    return {"redirect_url": f"{payload.redirect_uri}?code={code.code}&state={payload.state}"}


@router.post("/token")
async def token(payload: TokenRequest, db: AsyncSession = Depends(get_db)):
    """Exchange auth code for an access token."""
    client_result = await db.execute(select(OAuthClient).where(OAuthClient.id == payload.client_id))
    client = client_result.scalar_one_or_none()
    if not client or client.secret != payload.client_secret:
        raise HTTPException(status_code=401, detail="Invalid client credentials")

    code_result = await db.execute(select(OAuthAuthCode).where(OAuthAuthCode.code == payload.code))
    auth_code = code_result.scalar_one_or_none()
    if not auth_code or auth_code.used or auth_code.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired code")
    if auth_code.client_id != payload.client_id:
        raise HTTPException(status_code=400, detail="Code was not issued for this client")
    if auth_code.client_id != payload.client_id or client.redirect_uri != payload.redirect_uri:
        raise HTTPException(status_code=400, detail="redirect_uri mismatch")

    auth_code.used = True
    access_token = OAuthToken(
        token=secrets.token_urlsafe(40),
        client_id=payload.client_id,
        user_id=auth_code.user_id,
        agent_id=auth_code.agent_id,
    )
    db.add(access_token)
    await db.commit()

    return {
        "access_token": access_token.token,
        "token_type": "bearer",
        "agent_id": access_token.agent_id,
    }


class SelfTokenRequest(BaseModel):
    agent_id: str


@router.post("/self-token")
async def self_token(payload: SelfTokenRequest, db: AsyncSession = Depends(get_db)):
    """Issue a Bearer token for the UI's own agent — no OAuth dance needed.
    Used exclusively by the A2A protocol view in the Vouch web app.
    """
    from ..models.agent import ShoppingAgent
    result = await db.execute(select(ShoppingAgent).where(ShoppingAgent.id == payload.agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Reuse an existing vouch-ui self-token if one exists for this agent
    existing = await db.execute(
        select(OAuthToken)
        .where(OAuthToken.client_id == "vouch-ui", OAuthToken.agent_id == payload.agent_id)
    )
    token = existing.scalar_one_or_none()
    if token:
        return {"access_token": token.token, "token_type": "bearer", "agent_id": token.agent_id}

    new_token = OAuthToken(
        token=secrets.token_urlsafe(40),
        client_id="vouch-ui",
        user_id=agent.user_id,
        agent_id=payload.agent_id,
    )
    db.add(new_token)
    await db.commit()
    return {"access_token": new_token.token, "token_type": "bearer", "agent_id": new_token.agent_id}


@router.get("/me")
async def me(agent_id: str = Depends(get_agent_from_token), db: AsyncSession = Depends(get_db)):
    """Return agent identity for a valid Bearer token."""
    result = await db.execute(
        select(User, ShoppingAgent)
        .join(ShoppingAgent, ShoppingAgent.user_id == User.id)
        .where(ShoppingAgent.id == agent_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Agent not found")
    user, agent = row
    return {"agent_id": agent.id, "user_id": user.id, "name": user.name}
