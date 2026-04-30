import uuid
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..api.oauth import get_agent_from_token
from ..agents.shopping_agent import chat

router = APIRouter(tags=["a2a"])

VOUCH_URL = "https://vouch-backend-392847826435.us-central1.run.app"

AGENT_CARD = {
    "name": "Vouch Shopping Agent",
    "description": "A personal beauty shopping agent with taste memory and a trust network of peers.",
    "provider": {"organization": "Vouch", "url": VOUCH_URL},
    "version": "1.0.0",
    "url": VOUCH_URL,
    "capabilities": {"streaming": False, "pushNotifications": False},
    "securitySchemes": {
        "oauth2": {
            "type": "oauth2",
            "flows": {
                "authorizationCode": {
                    "authorizationUrl": f"{VOUCH_URL}/oauth/authorize",
                    "tokenUrl": f"{VOUCH_URL}/api/oauth/token",
                    "scopes": {
                        "chat": "Send messages to your Vouch shopping agent",
                        "read": "Read recommendations and reviews from the trust network",
                    },
                }
            },
        }
    },
    "security": [{"oauth2": ["chat"]}],
    "skills": [
        {
            "id": "shopping-recommendation",
            "name": "Shopping Recommendation",
            "description": "Get personalized product recommendations based on your taste profile and trusted network.",
            "tags": ["shopping", "beauty", "recommendations"],
            "inputModes": ["text"],
            "outputModes": ["text"],
            "examples": ["Find me a good foundation for dry skin", "What moisturiser would you recommend?"],
        },
        {
            "id": "product-review",
            "name": "Product Review",
            "description": "Share a product review that updates your trust network's recommendations.",
            "tags": ["reviews", "beauty"],
            "inputModes": ["text"],
            "outputModes": ["text"],
            "examples": ["I loved the Rare Beauty blush, 5 stars", "The CeraVe cleanser was too drying for me"],
        },
        {
            "id": "trust-network-query",
            "name": "Trust Network Query",
            "description": "Ask what your trusted connections think about a product or category.",
            "tags": ["trust", "social", "recommendations"],
            "inputModes": ["text"],
            "outputModes": ["text"],
            "examples": ["What do my friends think about micellar water?"],
        },
    ],
}


# ── A2A message schema ─────────────────────────────────────────────────────────

class MessagePart(BaseModel):
    kind: str
    text: str | None = None


class A2AMessage(BaseModel):
    role: str
    parts: list[MessagePart]
    messageId: str


class SendMessageRequest(BaseModel):
    message: A2AMessage
    configuration: dict[str, Any] = {}
    metadata: dict[str, Any] = {}
    contextId: str | None = None
    taskId: str | None = None


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/.well-known/a2a-agent-card.json")
async def well_known_agent_card():
    return AGENT_CARD


@router.get("/api/a2a/agent-card")
async def agent_card():
    return AGENT_CARD


@router.post("/api/a2a/agents/{agent_id}/message/send")
async def send_message(
    agent_id: str,
    body: SendMessageRequest,
    token_agent_id: str = Depends(get_agent_from_token),
):
    if token_agent_id != agent_id:
        raise HTTPException(status_code=403, detail="Token does not grant access to this agent")

    text = next((p.text for p in body.message.parts if p.kind == "text" and p.text), None)
    if not text:
        raise HTTPException(status_code=400, detail="Message must contain at least one text part")

    result = await chat(agent_id, text)
    response_text = result["response"] if isinstance(result, dict) else result

    return {
        "id": body.taskId or str(uuid.uuid4()),
        "contextId": body.contextId or str(uuid.uuid4()),
        "status": {
            "state": "completed",
            "message": {
                "role": "agent",
                "parts": [{"kind": "text", "text": response_text}],
                "messageId": str(uuid.uuid4()),
            },
        },
    }
