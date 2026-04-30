"""
Vector store backed by pgvector (PostgreSQL) in production,
with a ChromaDB fallback for local SQLite dev.

Embeddings use Google's text-embedding-004 model (768-dim) when VECTOR_DB_URL is set,
falling back to ChromaDB's built-in embeddings for local dev.
"""
from __future__ import annotations
from ..config import settings

EMBEDDING_DIM = 768  # Google text-embedding-004


def get_or_create_collection(name: str):
    """Return a collection object matching the ChromaDB interface."""
    if settings.vector_db_url:
        return PgVectorCollection(name)
    return _chroma_collection(name)


# ── ChromaDB fallback (local dev without PostgreSQL) ──────────────────────────

def _chroma_collection(name: str):
    from pathlib import Path
    import chromadb
    chroma_path = "./data/chroma"
    Path(chroma_path).mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=chroma_path)
    return client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})


# ── Google embedding (direct REST, v1beta generativelanguage API) ─────────────

_EMBED_MODEL = "models/gemini-embedding-001"
_EMBED_BASE = "https://generativelanguage.googleapis.com/v1beta"


def _embed_one_rest(text: str) -> list[float]:
    import time, requests
    url = f"{_EMBED_BASE}/{_EMBED_MODEL}:embedContent"
    body = {
        "content": {"parts": [{"text": text}]},
        "outputDimensionality": 768,
    }
    for attempt in range(5):
        r = requests.post(url, json=body, params={"key": settings.gemini_api_key}, timeout=30)
        if r.status_code == 429:
            wait = 2 ** attempt  # 1s, 2s, 4s, 8s, 16s
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()["embedding"]["values"]
    r.raise_for_status()  # raise after exhausting retries


def _embed(texts: list[str]) -> list[list[float]]:
    return [_embed_one_rest(t) for t in texts]


def _embed_one(text: str) -> list[float]:
    return _embed_one_rest(text)


def _vec_str(emb: list[float]) -> str:
    """Format a float list as a pgvector literal: [0.1,0.2,...]"""
    return "[" + ",".join(f"{x:.8f}" for x in emb) + "]"


# ── pgvector collection ───────────────────────────────────────────────────────

def _conn():
    import psycopg2
    return psycopg2.connect(settings.vector_db_url)


class PgVectorCollection:
    def __init__(self, name: str) -> None:
        self.name = name

    def count(self) -> int:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM vector_embeddings WHERE collection_name = %s",
                (self.name,),
            )
            return cur.fetchone()[0]

    def add(
        self,
        documents: list[str],
        ids: list[str],
        metadatas: list[dict] | None = None,
    ) -> None:
        import json
        embeddings = _embed(documents)
        metas = metadatas or [{} for _ in documents]
        with _conn() as conn, conn.cursor() as cur:
            for doc, eid, emb, meta in zip(documents, ids, embeddings, metas):
                cur.execute(
                    """
                    INSERT INTO vector_embeddings
                        (id, collection_name, document, embedding, metadata)
                    VALUES (%s, %s, %s, %s::vector, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (eid, self.name, doc, _vec_str(emb), json.dumps(meta)),
                )

    def query(
        self,
        query_texts: list[str],
        n_results: int = 5,
        where: dict | None = None,
    ) -> dict:
        emb = _embed_one(query_texts[0])
        filter_sql, filter_params = _build_where(self.name, where)
        sql = f"""
            SELECT document, metadata
            FROM vector_embeddings
            WHERE {filter_sql}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(sql, (*filter_params, _vec_str(emb), n_results))
            rows = cur.fetchall()
        docs = [r[0] for r in rows]
        metas = [r[1] for r in rows]
        return {"documents": [docs], "metadatas": [metas]}

    def get(self, where: dict | None = None) -> dict:
        filter_sql, filter_params = _build_where(self.name, where)
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT document, metadata FROM vector_embeddings WHERE {filter_sql}",
                filter_params,
            )
            rows = cur.fetchall()
        return {
            "documents": [r[0] for r in rows],
            "metadatas": [r[1] for r in rows],
        }


def _build_where(collection_name: str, where: dict | None) -> tuple[str, list]:
    """Translate ChromaDB-style filter dicts to SQL WHERE clauses."""
    clauses = ["collection_name = %s"]
    params: list = [collection_name]
    if where:
        for field, condition in where.items():
            if "$eq" in condition:
                clauses.append(f"metadata->>'{field}' = %s")
                params.append(str(condition["$eq"]))
            elif "$in" in condition:
                placeholders = ",".join(["%s"] * len(condition["$in"]))
                clauses.append(f"metadata->>'{field}' IN ({placeholders})")
                params.extend(str(v) for v in condition["$in"])
    return " AND ".join(clauses), params


def find_similar_agents(
    agent_id: str,
    n: int = 5,
    min_similarity: float = 0.75,
) -> list[tuple[str, float]]:
    """Find other agents whose preference vectors are similar to this agent's.

    Compares this agent's preference documents against all other agents'
    preference collections using pgvector cosine similarity.

    Returns [(other_agent_id, avg_similarity), ...] sorted by similarity DESC,
    excluding agent_id itself and agents with avg_similarity < min_similarity.
    Only runs when vector_db_url is configured (no-op on ChromaDB).
    """
    if not settings.vector_db_url:
        return []

    import psycopg2
    collection_prefix = f"agent_{agent_id}_preferences"

    try:
        with psycopg2.connect(settings.vector_db_url) as conn, conn.cursor() as cur:
            # Fetch this agent's preference embeddings (up to 10)
            cur.execute(
                "SELECT embedding FROM vector_embeddings WHERE collection_name = %s LIMIT 10",
                (collection_prefix,),
            )
            my_embeddings = [row[0] for row in cur.fetchall()]

        if not my_embeddings:
            return []

        # For each of our embeddings, find the top similar documents from OTHER agents' preference collections
        # collection_name pattern: agent_<uuid>_preferences
        similarity_sums: dict[str, float] = {}
        hit_counts: dict[str, int] = {}

        with psycopg2.connect(settings.vector_db_url) as conn, conn.cursor() as cur:
            for emb in my_embeddings[:5]:  # cap to avoid too many queries
                cur.execute(
                    """
                    SELECT
                        substring(collection_name FROM 7 FOR 36) AS other_id,
                        AVG(1 - (embedding <=> %s::vector)) AS avg_sim
                    FROM vector_embeddings
                    WHERE collection_name LIKE 'agent_%%_preferences'
                      AND collection_name != %s
                    GROUP BY collection_name
                    HAVING AVG(1 - (embedding <=> %s::vector)) >= %s
                    ORDER BY avg_sim DESC
                    LIMIT %s
                    """,
                    (emb, collection_prefix, emb, min_similarity, n * 2),
                )
                for other_id, sim in cur.fetchall():
                    similarity_sums[other_id] = similarity_sums.get(other_id, 0.0) + float(sim)
                    hit_counts[other_id] = hit_counts.get(other_id, 0) + 1

        if not similarity_sums:
            return []

        # Average across our embedding probes and sort
        averaged = [
            (oid, similarity_sums[oid] / hit_counts[oid])
            for oid in similarity_sums
        ]
        averaged.sort(key=lambda x: x[1], reverse=True)
        return averaged[:n]

    except Exception:
        import logging
        logging.getLogger(__name__).exception("find_similar_agents failed")
        return []
