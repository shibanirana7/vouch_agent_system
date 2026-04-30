from pydantic import BaseModel
from datetime import datetime
from typing import Literal


TrustLevel = Literal["close_friend", "friend", "acquaintance"]


class TrustCreate(BaseModel):
    from_agent_id: str
    to_agent_id: str
    trust_level: TrustLevel = "acquaintance"


class TrustUpdate(BaseModel):
    trust_level: TrustLevel


class TrustRelationshipOut(BaseModel):
    id: str
    from_agent_id: str
    to_agent_id: str
    trust_level: str
    trust_weight: float
    interaction_count: int
    created_at: datetime

    model_config = {"from_attributes": True}
