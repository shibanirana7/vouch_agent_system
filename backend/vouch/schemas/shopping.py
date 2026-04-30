from pydantic import BaseModel
from datetime import datetime


class WishlistItemOut(BaseModel):
    id: str
    product_name: str
    description: str
    url: str | None
    priority: int
    target_price: float | None
    is_recurring: bool
    recurrence_interval_days: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class WishlistItemCreate(BaseModel):
    product_name: str
    description: str = ""
    url: str | None = None
    priority: int = 1
    target_price: float | None = None
    is_recurring: bool = False
    recurrence_interval_days: int | None = None


class PurchaseRecordOut(BaseModel):
    id: str
    product_name: str
    url: str
    price: float
    was_recommended: bool
    recommending_agent_id: str | None
    satisfaction_score: int | None
    opinion_text: str | None
    purchased_at: datetime

    model_config = {"from_attributes": True}


class PurchaseCreate(BaseModel):
    agent_id: str
    product_name: str
    price: float
    category: str = "general"
    url: str = ""
    was_recommended: bool = False
    recommending_agent_id: str | None = None


class ConfirmWishlistPurchase(BaseModel):
    wishlist_item_id: str
    actual_price: float | None = None


class RatePurchase(BaseModel):
    opinion: str  # free-form opinion; agent extracts sentiment, review, and preferences


class DecideRequest(BaseModel):
    agent_id: str
    query: str
