import uuid
from datetime import datetime
from sqlalchemy import String, Float, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base


class PurchaseRecord(Base):
    __tablename__ = "purchase_records"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id: Mapped[str] = mapped_column(String, ForeignKey("shopping_agents.id"), nullable=False)
    product_name: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, default="")
    price: Mapped[float] = mapped_column(Float, nullable=False)
    was_recommended: Mapped[bool] = mapped_column(Boolean, default=False)
    recommending_agent_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("shopping_agents.id"), nullable=True
    )
    satisfaction_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    opinion_text: Mapped[str | None] = mapped_column(String, nullable=True)
    purchased_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    agent: Mapped["ShoppingAgent"] = relationship(
        "ShoppingAgent", foreign_keys=[agent_id], back_populates="purchases"
    )
    recommending_agent: Mapped["ShoppingAgent | None"] = relationship(
        "ShoppingAgent", foreign_keys=[recommending_agent_id]
    )
