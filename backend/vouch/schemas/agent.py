from pydantic import BaseModel
from datetime import datetime


class AgentOut(BaseModel):
    id: str
    user_id: str
    preference_summary: dict
    is_autonomous: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatMessage(BaseModel):
    role: str   # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []  # sliding window of prior turns (last 10)


class ChatResponse(BaseModel):
    response: str
    agent_id: str
    reflection_retries: int = 0
