import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional
from ..database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)  # price_drop | friend_review | friend_recommendation | restock_due | connection_request
    title: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(String, nullable=False)
    source_hash: Mapped[str] = mapped_column(String, nullable=False)  # deduplication key
    dismissed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Actionable notifications: action_type drives the CTA button in the UI
    # add_to_wishlist: payload = {product_name, description, is_recurring}
    # add_friend:      payload = {connection_request_id, from_agent_id}
    action_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    action_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
