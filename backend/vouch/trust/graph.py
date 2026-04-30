import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models.trust import TrustRelationship
from ..memory.shared_memory import SharedMemory

logger = logging.getLogger(__name__)


class TrustNetwork:
    """Query and manage an agent's trust network."""

    def __init__(self, agent_id: str, db: AsyncSession) -> None:
        self.agent_id = agent_id
        self.db = db
        self._shared_memory = SharedMemory()

    async def get_trusted_agents(self) -> list[tuple[str, float]]:
        """Return [(agent_id, trust_weight), ...] sorted by weight DESC."""
        result = await self.db.execute(
            select(TrustRelationship)
            .where(TrustRelationship.from_agent_id == self.agent_id)
            .order_by(TrustRelationship.trust_weight.desc())
        )
        rels = result.scalars().all()
        return [(r.to_agent_id, r.trust_weight) for r in rels]

    async def get_recommendations(self, category: str, query: str) -> list[dict]:
        """
        Query reviews from trusted agents, weighted by trust level.
        Returns a list of review dicts sorted by effective_score DESC.
        """
        trusted = await self.get_trusted_agents()
        if not trusted:
            return []

        trusted_ids = [agent_id for agent_id, _ in trusted]
        weight_map = {agent_id: weight for agent_id, weight in trusted}

        reviews = self._shared_memory.query_reviews(query=query, category=category, trusted_agent_ids=trusted_ids)

        for review in reviews:
            agent_id = review.get("agent_id", "")
            review["trust_weight"] = weight_map.get(agent_id, 0.0)
            review["effective_score"] = review.get("rating", 0) * review["trust_weight"]

        reviews.sort(key=lambda r: r["effective_score"], reverse=True)
        return reviews

    async def update_taste_weight(
        self, product_name: str, my_rating: int
    ) -> list[dict]:
        """Adjust trust weights based on rating agreement with trusted peers.

        Agreement  (|diff| <= 1): weight += 0.05, capped at 1.0
        Neutral    (|diff| == 2): no change
        Disagreement (|diff| >= 3): weight -= 0.05, floor at 0.1

        Returns list of dicts describing each change:
        [{"agent_id": str, "old_weight": float, "new_weight": float, "direction": "up"|"down"|"none"}]
        """
        trusted = await self.get_trusted_agents()
        if not trusted:
            return []

        trusted_ids = [aid for aid, _ in trusted]
        reviews = self._shared_memory.get_reviews_by_agents(trusted_ids)

        peer_ratings: dict[str, int] = {}
        for review in reviews:
            if review.get("product", "").lower() == product_name.lower():
                peer_id = review.get("agent_id")
                if peer_id:
                    peer_ratings[peer_id] = review.get("rating", 0)

        if not peer_ratings:
            return []

        changes = []
        for peer_id, peer_rating in peer_ratings.items():
            diff = abs(my_rating - peer_rating)
            result = await self.db.execute(
                select(TrustRelationship).where(
                    TrustRelationship.from_agent_id == self.agent_id,
                    TrustRelationship.to_agent_id == peer_id,
                )
            )
            rel = result.scalar_one_or_none()
            if not rel:
                continue

            old_weight = rel.trust_weight
            if diff <= 1:
                rel.trust_weight = min(rel.trust_weight + 0.05, 1.0)
                direction = "up"
            elif diff >= 3:
                rel.trust_weight = max(rel.trust_weight - 0.05, 0.1)
                direction = "down"
            else:
                direction = "none"

            rel.interaction_count += 1
            changes.append({
                "agent_id": peer_id,
                "old_weight": round(old_weight, 2),
                "new_weight": round(rel.trust_weight, 2),
                "direction": direction,
            })
            logger.info(
                "Taste update: %s → %s on '%s': diff=%d weight %.2f → %.2f",
                self.agent_id[:8], peer_id[:8], product_name, diff, old_weight, rel.trust_weight,
            )

        await self.db.commit()
        return changes

    async def auto_connect(self, candidates: list[tuple[str, float]]) -> list[str]:
        """Send connection requests to similar agents not yet connected or already requested.

        candidates: [(agent_id, similarity_score), ...]
        Returns list of agent IDs for which requests were sent.
        """
        from ..models.connection_request import ConnectionRequest

        existing_trust = await self.db.execute(
            select(TrustRelationship.to_agent_id).where(
                TrustRelationship.from_agent_id == self.agent_id
            )
        )
        already_connected = {row[0] for row in existing_trust.fetchall()}

        existing_reqs = await self.db.execute(
            select(ConnectionRequest.to_agent_id).where(
                ConnectionRequest.from_agent_id == self.agent_id,
                ConnectionRequest.status == "pending",
            )
        )
        already_requested = {row[0] for row in existing_reqs.fetchall()}

        sent = []
        for other_id, sim in candidates:
            if other_id in already_connected or other_id in already_requested or other_id == self.agent_id:
                continue
            req = ConnectionRequest(
                from_agent_id=self.agent_id,
                to_agent_id=other_id,
                message="I think we have similar taste — I'd love to connect!",
                similarity_score=round(sim, 3),
                status="pending",
            )
            self.db.add(req)
            sent.append(other_id)
            logger.info(
                "Connection request: %s → %s (sim=%.2f)",
                self.agent_id[:8], other_id[:8], sim,
            )

        if sent:
            await self.db.commit()
        return sent

    async def get_trust_summary(self) -> str:
        """Human-readable summary for agent system prompt."""
        trusted = await self.get_trusted_agents()
        if not trusted:
            return "No trusted connections yet."
        lines = []
        for agent_id, weight in trusted[:5]:
            level = _weight_to_level(weight)
            lines.append(f"- Agent {agent_id[:8]}... ({level}, weight {weight})")
        return "\n".join(lines)


def _weight_to_level(weight: float) -> str:
    if weight >= 0.85:
        return "close friend"
    if weight >= 0.5:
        return "friend"
    return "acquaintance"
