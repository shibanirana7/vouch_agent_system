import secrets
from datetime import datetime
from sqlalchemy import String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base


class OAuthClient(Base):
    __tablename__ = "oauth_clients"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    secret: Mapped[str] = mapped_column(String, nullable=False)
    redirect_uri: Mapped[str] = mapped_column(String, nullable=False)


class OAuthAuthCode(Base):
    __tablename__ = "oauth_auth_codes"

    code: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: secrets.token_urlsafe(32))
    client_id: Mapped[str] = mapped_column(String, ForeignKey("oauth_clients.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    token: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: secrets.token_urlsafe(40))
    client_id: Mapped[str] = mapped_column(String, ForeignKey("oauth_clients.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
