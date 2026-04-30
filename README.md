# Vouch — Trust-First Beauty Shopping Agent

Vouch is a multi-agent shopping system where each user gets a personal AI agent that learns their preferences, consults trusted peers, and acts autonomously in the background. Built with FastAPI, LangGraph, Gemini, and pgvector on Google Cloud.

## Architecture

```
Frontend (React + Vite)
    └── FastAPI backend (Cloud Run)
            ├── LangGraph agent loop  ← Gemini LLM + MCP tools
            ├── pgvector (Cloud SQL)  ← preference embeddings + similarity search
            ├── PostgreSQL (Cloud SQL) ← users, agents, trust graph, wishlists
            └── Cloud Scheduler       ← autonomous tick (POST /agents/tick-all)
```

**Agent loop (per chat request):**
1. Retrieve preferences + peer reviews from memory
2. Gemini reasons and selects MCP tools (product search, wishlist, trust network)
3. Execute tools, reflect on response quality, retry if needed

**Autonomous tick (background, no user action required):**
- Wishlist refill: detects products due for replacement, adds them, notifies user
- Peer discovery: finds agents with similar taste via cosine similarity (≥ 0.65), sends connection requests

## Stack

| Layer | Technology |
|---|---|
| LLM | Gemini 2.5 Pro via Google AI Studio |
| Agent framework | LangGraph |
| Tool protocol | MCP (Model Context Protocol) |
| Backend | FastAPI + asyncpg |
| Vector memory | pgvector on Cloud SQL PostgreSQL |
| Hosting | Cloud Run (backend + frontend served together) |
| Scheduler | Cloud Scheduler → POST /agents/tick-all |

## Prerequisites

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Node.js 20+
- A Google Cloud project with billing enabled
- A [Google AI Studio](https://aistudio.google.com/apikey) API key (free tier works)

## Local Development

### 1. Clone and install

```bash
git clone <repo-url>
cd vouch_agent_system
uv sync                        # install Python deps
cd frontend && npm install     # install JS deps
```

### 2. Configure environment

```bash
cp .env.example .env
# Fill in GEMINI_API_KEY and DATABASE_URL
```

For local development you can point `DATABASE_URL` and `VECTOR_DB_URL` at a local PostgreSQL instance with the pgvector extension enabled:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### 3. Run

```bash
# Terminal 1 — backend
uv run uvicorn vouch.main:app --reload --app-dir backend

# Terminal 2 — frontend
cd frontend && npm run dev
```

Open http://localhost:5173

## Production Deployment (Google Cloud)

### 1. Cloud SQL (PostgreSQL + pgvector)

```bash
# Create instance
gcloud sql instances create vouch-db \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=us-central1

# Create DB and user
gcloud sql databases create vouch --instance=vouch-db
gcloud sql users create vouch --instance=vouch-db --password=<password>

# Enable pgvector (connect and run)
gcloud sql connect vouch-db --user=vouch --database=vouch
# Inside psql:
# CREATE EXTENSION IF NOT EXISTS vector;
```

Note the public IP from `gcloud sql instances describe vouch-db --format="value(ipAddresses[0].ipAddress)"`.

Authorize your Cloud Run service account under **Cloud SQL > Connections > Authorized networks**, or use the Cloud SQL Auth Proxy.

### 2. Build and deploy to Cloud Run

```bash
gcloud builds submit --tag gcr.io/<PROJECT_ID>/vouch-backend

gcloud run deploy vouch-backend \
  --image gcr.io/<PROJECT_ID>/vouch-backend \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars "\
LLM_BACKEND=gemini,\
GEMINI_API_KEY=<key>,\
GEMINI_MODEL=gemini-2.5-pro,\
DATABASE_URL=postgresql+asyncpg://vouch:<password>@<cloud-sql-ip>/vouch,\
VECTOR_DB_URL=postgresql://vouch:<password>@<cloud-sql-ip>/vouch"
```

The Dockerfile is a multistage build — it compiles the React frontend and serves it from the same Cloud Run container as the FastAPI backend.

### 3. Autonomous scheduler (optional)

To enable background agent ticks, create a Cloud Scheduler job targeting the deployed service:

```bash
gcloud scheduler jobs create http vouch-tick-all \
  --schedule="*/30 * * * *" \
  --uri="https://<cloud-run-url>/api/agents/tick-all" \
  --http-method=POST \
  --location=us-central1
```

Users opt in via the **Profile → Autonomous agent** toggle in the UI.

## Environment Variables

See `.env.example` for all variables. Required for production:

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Google AI Studio API key |
| `GEMINI_MODEL` | Model name (default: `gemini-2.5-pro`) |
| `DATABASE_URL` | asyncpg connection string for FastAPI |
| `VECTOR_DB_URL` | psycopg2 connection string for vector memory layer |

## Project Structure

```
backend/vouch/
├── agents/          # LangGraph agent graph + LLM loader
├── api/             # FastAPI routers (agents, social, autonomous, a2a)
├── mcp_server/      # MCP tool definitions and handlers
├── memory/          # pgvector store, agent memory, shared memory
├── models/          # SQLAlchemy models
├── trust/           # Trust graph + weight adjustment
└── data/            # Product catalog

frontend/src/
├── pages/           # Dashboard, Profile, Wishlist, SocialGraph, Purchases
├── api/             # Typed API client
└── store/           # Zustand auth + chat state

experiments/         # Multi-agent scale experiment scripts (HW7 + HW8)
```

## Key API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/agents/{id}/chat` | Chat with agent |
| POST | `/api/agents/tick-all` | Run autonomous tick for all opted-in agents |
| PATCH | `/api/agents/{id}/autonomous` | Enable/disable autonomous mode |
| GET | `/api/agents/{id}/notifications` | Get agent notifications |
| POST | `/api/social/trust` | Create trust relationship |
| GET | `/api/social/consultations/{id}` | View peer consultation log |
