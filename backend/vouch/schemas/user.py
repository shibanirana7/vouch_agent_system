from pydantic import BaseModel, EmailStr
from datetime import datetime


class UserCreate(BaseModel):
    name: str
    email: str
    password: str | None = None
    is_agent_user: bool = False


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: str
    name: str
    email: str
    is_agent_user: bool
    created_at: datetime
    agent_id: str | None = None

    model_config = {"from_attributes": True}
