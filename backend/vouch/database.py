from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from .config import settings


engine = create_async_engine(
    settings.database_url,
    echo=False,
    poolclass=NullPool,  # open/close per request — no persistent pool; safe for many concurrent instances
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    from . import models  # noqa: F401 — ensure all models are registered
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # pgvector extension + embeddings table (no-op on SQLite for local dev)
        dialect = conn.dialect.name
        if dialect == "postgresql":
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR"))
            await conn.execute(text("ALTER TABLE agent_consultations ADD COLUMN IF NOT EXISTS a2a_request TEXT"))
            await conn.execute(text("ALTER TABLE agent_consultations ADD COLUMN IF NOT EXISTS a2a_response TEXT"))
            await conn.execute(text("ALTER TABLE purchase_records ADD COLUMN IF NOT EXISTS opinion_text TEXT"))
            await conn.execute(text("ALTER TABLE shopping_agents ADD COLUMN IF NOT EXISTS is_autonomous BOOLEAN NOT NULL DEFAULT FALSE"))
            await conn.execute(text("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS action_type VARCHAR"))
            await conn.execute(text("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS action_payload JSONB"))
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS vector_embeddings (
                    id TEXT PRIMARY KEY,
                    collection_name TEXT NOT NULL,
                    document TEXT NOT NULL,
                    embedding vector(768) NOT NULL,
                    metadata JSONB NOT NULL DEFAULT '{}'
                )
            """))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS vec_collection_idx "
                "ON vector_embeddings (collection_name)"
            ))
