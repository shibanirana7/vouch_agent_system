import uuid
from datetime import datetime
from sqlalchemy import String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base


class AgentConsultation(Base):
    __tablename__ = "agent_consultations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    from_agent_id: Mapped[str] = mapped_column(String, ForeignKey("shopping_agents.id"), nullable=False)
    to_agent_id: Mapped[str] = mapped_column(String, ForeignKey("shopping_agents.id"), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    trust_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    a2a_request: Mapped[str | None] = mapped_column(Text, nullable=True)
    a2a_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
