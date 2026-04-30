import uuid
from .store import get_or_create_collection


class AgentMemory:
    """Per-agent vector memory for preferences and purchase history."""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self._prefs = get_or_create_collection(f"agent_{agent_id}_preferences")
        self._history = get_or_create_collection(f"agent_{agent_id}_history")

    # ── Preferences ──────────────────────────────────────────────────────────

    def store_preference(self, text: str) -> None:
        self._prefs.add(
            documents=[text],
            ids=[str(uuid.uuid4())],
        )

    def retrieve_preferences(self, query: str, n: int = 5) -> list[str]:
        count = self._prefs.count()
        if count == 0:
            return []
        results = self._prefs.query(query_texts=[query], n_results=min(n, count))
        return results["documents"][0] if results["documents"] else []

    def build_preference_context(self, n: int = 5) -> str:
        count = self._prefs.count()
        if count == 0:
            return "No preferences recorded yet."
        results = self._prefs.query(
            query_texts=["user shopping preferences taste style budget"],
            n_results=min(n, count),
        )
        prefs = results["documents"][0] if results["documents"] else []
        return "\n".join(f"- {p}" for p in prefs)

    # ── Purchase history ─────────────────────────────────────────────────────

    def store_purchase(self, product: str, price: float, category: str, satisfaction: int | None = None) -> None:
        text = f"Purchased: {product} (${price:.2f}, category: {category}"
        if satisfaction is not None:
            text += f", satisfaction: {satisfaction}/5"
        text += ")"
        self._history.add(
            documents=[text],
            ids=[str(uuid.uuid4())],
            metadatas=[{"product": product, "price": price, "category": category, "satisfaction": satisfaction or 0}],
        )

    def retrieve_relevant_history(self, query: str, n: int = 5) -> list[dict]:
        count = self._history.count()
        if count == 0:
            return []
        results = self._history.query(query_texts=[query], n_results=min(n, count))
        docs = results["documents"][0] if results["documents"] else []
        metas = results["metadatas"][0] if results["metadatas"] else []
        return [{"text": d, **m} for d, m in zip(docs, metas)]
