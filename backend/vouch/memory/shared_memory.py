import uuid
from .store import get_or_create_collection


class SharedMemory:
    """Global product review store shared across all agents, filtered by trust."""

    def __init__(self) -> None:
        self._col = get_or_create_collection("shared_product_reviews")

    def contribute_review(
        self,
        agent_id: str,
        product: str,
        category: str,
        review_text: str,
        rating: int = 3,
    ) -> None:
        doc = f"[{category}] {product}: {review_text}"
        self._col.add(
            documents=[doc],
            ids=[str(uuid.uuid4())],
            metadatas=[{
                "agent_id": agent_id,
                "product": product,
                "category": category,
                "rating": rating,
            }],
        )

    def get_own_reviews(self, agent_id: str) -> list[dict]:
        """Return all reviews written by this agent."""
        if self._col.count() == 0:
            return []
        results = self._col.get(where={"agent_id": {"$eq": agent_id}})
        docs = results.get("documents") or []
        metas = results.get("metadatas") or []
        return [{"text": d, **m} for d, m in zip(docs, metas)]

    def get_reviews_by_agents(self, agent_ids: list[str]) -> list[dict]:
        """Return all reviews written by any of the given agents."""
        if not agent_ids or self._col.count() == 0:
            return []
        results = self._col.get(where={"agent_id": {"$in": agent_ids}})
        docs = results.get("documents") or []
        metas = results.get("metadatas") or []
        return [{"text": d, **m} for d, m in zip(docs, metas)]

    def query_reviews(
        self,
        query: str,
        category: str,
        trusted_agent_ids: list[str],
        n: int = 10,
    ) -> list[dict]:
        if not trusted_agent_ids:
            return []
        count = self._col.count()
        if count == 0:
            return []
        results = self._col.query(
            query_texts=[query],
            n_results=min(n, count),
            where={"agent_id": {"$in": trusted_agent_ids}},
        )
        docs = results["documents"][0] if results["documents"] else []
        metas = results["metadatas"][0] if results["metadatas"] else []
        return [{"text": d, **m} for d, m in zip(docs, metas)]
