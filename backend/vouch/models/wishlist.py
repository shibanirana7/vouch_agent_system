import uuid
from datetime import datetime
from sqlalchemy import String, Float, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base


class WishlistItem(Base):
    __tablename__ = "wishlist_items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id: Mapped[str] = mapped_column(String, ForeignKey("shopping_agents.id"), nullable=False)
    product_name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, default="")
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=1)
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    recurrence_interval_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    agent: Mapped["ShoppingAgent"] = relationship("ShoppingAgent", back_populates="wishlist_items")
