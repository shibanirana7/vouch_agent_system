import uuid
from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base

TRUST_WEIGHTS = {
    "close_friend": 0.9,
    "friend": 0.6,
    "acquaintance": 0.3,
}


class TrustRelationship(Base):
    __tablename__ = "trust_relationships"
    __table_args__ = (UniqueConstraint("from_agent_id", "to_agent_id", name="uq_trust_pair"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    from_agent_id: Mapped[str] = mapped_column(String, ForeignKey("shopping_agents.id"), nullable=False)
    to_agent_id: Mapped[str] = mapped_column(String, ForeignKey("shopping_agents.id"), nullable=False)
    trust_level: Mapped[str] = mapped_column(String, nullable=False, default="acquaintance")
    trust_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.3)
    interaction_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    from_agent: Mapped["ShoppingAgent"] = relationship(
        "ShoppingAgent", foreign_keys=[from_agent_id], back_populates="outgoing_trust"
    )
    to_agent: Mapped["ShoppingAgent"] = relationship(
        "ShoppingAgent", foreign_keys=[to_agent_id], back_populates="incoming_trust"
    )
