import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .config import settings
from .database import init_db, AsyncSessionLocal
from .api import users, agents, shopping, social, autonomous
from .api import oauth as oauth_api
from .api import a2a as a2a_api
from .mcp_server.server import mcp


async def _seed_oauth_clients() -> None:
    """Ensure built-in OAuth clients exist (idempotent)."""
    from sqlalchemy import select
    from .models.oauth import OAuthClient
    clients = [
        OAuthClient(
            id="openclaw",
            name="OpenClaw",
            secret="openclaw-secret",
            redirect_uri="https://app.openclaw.ai/oauth/callback",
        ),
        OAuthClient(
            id="vouch-ui",
            name="Vouch Web App",
            secret="vouch-ui-internal",
            redirect_uri="https://vouch-backend-392847826435.us-central1.run.app",
        ),
    ]
    async with AsyncSessionLocal() as db:
        for client in clients:
            existing = await db.execute(select(OAuthClient).where(OAuthClient.id == client.id))
            if not existing.scalar_one_or_none():
                db.add(client)
        await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await _seed_oauth_clients()
    # Pre-initialize ChromaDB embedding model so the first request doesn't block
    # (downloads ~79 MB on first run, cached afterwards)
    from .memory.store import get_or_create_collection
    import asyncio
    await asyncio.get_event_loop().run_in_executor(
        None, lambda: get_or_create_collection("warmup")
    )
    yield


app = FastAPI(
    title="Vouch API",
    description="Trust-first agentic shopping platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router, prefix="/api")
app.include_router(agents.router, prefix="/api")
app.include_router(autonomous.router, prefix="/api")
app.include_router(shopping.router, prefix="/api")
app.include_router(social.router, prefix="/api")
app.include_router(oauth_api.router, prefix="/api")
app.include_router(a2a_api.router)  # serves /.well-known/... and /api/a2a/...

# Mount the MCP server
app.mount("/mcp", mcp.http_app(path="/"))


@app.get("/health")
async def health():
    return {"status": "ok", "llm_backend": settings.llm_backend}


# Serve the React frontend — must come last
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    # Mount assets (JS/CSS/images) at /assets so they resolve correctly
    app.mount("/assets", StaticFiles(directory=_static_dir / "assets"), name="assets")

    # Catch-all: serve index.html for any path React Router handles (SPA fallback)
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(request: Request, full_path: str):
        index = _static_dir / "index.html"
        if index.exists():
            return FileResponse(index)
        return {"detail": "Frontend not built"}
