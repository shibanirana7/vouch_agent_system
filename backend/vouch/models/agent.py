import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base


class ShoppingAgent(Base):
    __tablename__ = "shopping_agents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    chroma_collection_id: Mapped[str] = mapped_column(String, nullable=False)
    preference_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    is_autonomous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="agent")
    outgoing_trust: Mapped[list["TrustRelationship"]] = relationship(
        "TrustRelationship", foreign_keys="TrustRelationship.from_agent_id", back_populates="from_agent"
    )
    incoming_trust: Mapped[list["TrustRelationship"]] = relationship(
        "TrustRelationship", foreign_keys="TrustRelationship.to_agent_id", back_populates="to_agent"
    )
    wishlist_items: Mapped[list["WishlistItem"]] = relationship("WishlistItem", back_populates="agent")
    purchases: Mapped[list["PurchaseRecord"]] = relationship(
        "PurchaseRecord", foreign_keys="PurchaseRecord.agent_id", back_populates="agent"
    )
