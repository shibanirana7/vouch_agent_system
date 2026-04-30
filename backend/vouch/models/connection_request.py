import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Text, Float
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base


class ConnectionRequest(Base):
    __tablename__ = "connection_requests"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    from_agent_id: Mapped[str] = mapped_column(String, nullable=False)
    to_agent_id: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")  # pending, accepted, denied
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
