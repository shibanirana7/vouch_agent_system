"""
Trust query subagent: identifies the product category, fetches weighted reviews
from shared memory, then consults up to 2 trusted peers via the A2A protocol.
"""
import json
import uuid
import logging
from datetime import datetime, timezone
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from ..state import AgentState
from ..llm import get_llm
from .._utils import _text
from ...mcp_server.handlers import query_trust_network
from ...database import AsyncSessionLocal
from ...trust.graph import TrustNetwork

logger = logging.getLogger(__name__)

# Multi-word phrases must come before their component words so they match first.
_CATEGORIES = [
    "setting powder", "setting spray", "lip gloss", "lip liner", "lip treatment",
    "eye cream", "face mask", "makeup remover",
    "foundation", "concealer", "primer", "contour", "blush", "bronzer",
    "highlighter", "mascara", "eyeliner", "eyeshadow", "eyebrow",
    "lipstick", "moisturizer", "cleanser", "serum", "toner", "sunscreen",
    "brush", "tool",
]


def _extract_category(text: str) -> str:
    """Return the first catalog category found in text, or 'general'."""
    lower = text.lower()
    for cat in _CATEGORIES:
        if cat in lower:
            return cat
    return "general"


def _build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("identify_category", _identify_category_node)
    graph.add_node("fetch", _fetch_node)
    graph.add_node("consult_peers", _consult_peers_node)
    graph.set_entry_point("identify_category")
    graph.add_edge("identify_category", "fetch")
    graph.add_edge("fetch", "consult_peers")
    graph.add_edge("consult_peers", END)
    return graph.compile()


def _identify_category_node(state: AgentState) -> AgentState:
    last_message = state["messages"][-1].content if state["messages"] else ""
    category = _extract_category(last_message)
    logger.info("[%s] TRUST category=%s", state["agent_id"][:8], category)
    outputs = dict(state.get("subagent_outputs", {}))
    outputs["trust_category"] = category
    return {**state, "subagent_outputs": outputs}


async def _fetch_node(state: AgentState) -> AgentState:
    category = state["subagent_outputs"].get("trust_category", "general")
    last_message = state["messages"][-1].content if state["messages"] else ""
    recs = await query_trust_network(
        agent_id=state["agent_id"],
        category=category,
        query=last_message,
    )
    logger.info("[%s] TRUST vector fetch — %d SharedMemory recs for category=%s",
                state["agent_id"][:8], len(recs), category)
    outputs = dict(state.get("subagent_outputs", {}))
    outputs["trust_recommendations"] = recs
    return {**state, "subagent_outputs": outputs}


async def _consult_peer(
    agent_id: str,
    peer_id: str,
    trust_weight: float,
    query: str,
) -> dict | None:
    """Consult a single peer and return a consultation record, or None on failure."""
    import asyncio
    from ..shopping_agent import chat  # lazy import avoids circular dependency

    message_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    context_id = str(uuid.uuid4())
    a2a_request = {
        "message": {
            "role": "user",
            "parts": [{"kind": "text", "text": query}],
            "messageId": message_id,
        },
        "configuration": {"historyLength": 0},
        "metadata": {
            "caller_agent_id": agent_id,
            "trust_weight": trust_weight,
            "protocol": "a2a",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "taskId": task_id,
        "contextId": context_id,
    }

    try:
        result = await chat(agent_id=peer_id, message=query, is_consultation=True)
        response_text = result["response"] if isinstance(result, dict) else result

        a2a_response = {
            "id": task_id,
            "contextId": context_id,
            "status": {
                "state": "completed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": {
                    "role": "agent",
                    "parts": [{"kind": "text", "text": response_text}],
                    "messageId": str(uuid.uuid4()),
                },
            },
            "metadata": {"trust_weight": trust_weight},
        }

        try:
            from ...models.consultation import AgentConsultation
            async with AsyncSessionLocal() as db:
                record = AgentConsultation(
                    from_agent_id=agent_id,
                    to_agent_id=peer_id,
                    query=query,
                    response=response_text,
                    trust_weight=trust_weight,
                    a2a_request=json.dumps(a2a_request, indent=2),
                    a2a_response=json.dumps(a2a_response, indent=2),
                )
                db.add(record)
                await db.commit()
        except Exception:
            logger.exception("Failed to save A2A consultation record for peer %s", peer_id[:8])

        logger.info("[%s] A2A -> peer %s (weight=%.2f) | response=%d chars: %r",
                    agent_id[:8], peer_id[:8], trust_weight, len(response_text), response_text[:80])
        return {
            "agent_id": peer_id,
            "text": response_text,
            "targeted_question": query,
            "trust_weight": trust_weight,
            "source": "a2a_consultation",
        }
    except Exception:
        logger.exception("[%s] A2A -> peer %s FAILED", agent_id[:8], peer_id[:8])
        return None


async def _generate_peer_question(user_query: str, category: str) -> str:
    """Use LLM to craft a targeted follow-up question for peer consultation."""
    llm = get_llm()
    response = await llm.ainvoke([
        SystemMessage(content=(
            "You are a beauty shopping agent consulting a trusted peer agent. "
            "Generate a single focused follow-up question to ask the peer based on the user's request. "
            "The question should:\n"
            "- Ask for the peer's personal experience or opinion on a specific, relevant aspect "
            "(e.g. a formula concern, finish preference, value-for-money, skin type compatibility)\n"
            "- Be concise — one or two sentences\n"
            "- Sound natural, like one knowledgeable shopper asking another\n"
            "Output only the question, no preamble."
        )),
        HumanMessage(content=(
            f"User request: {user_query}\n"
            f"Product category: {category}"
        )),
    ])
    return _text(response.content).strip()


async def _consult_peers_node(state: AgentState) -> AgentState:
    """Consult up to 2 trusted peers in parallel. Skips if already being consulted."""
    if state.get("is_consultation"):
        logger.info("[%s] PEERS skip (is_consultation=True)", state["agent_id"][:8])
        return state

    import asyncio

    last_message = state["messages"][-1].content if state["messages"] else ""
    user_query = last_message.replace("[AGENT CONSULTATION] ", "")
    agent_id = state["agent_id"]
    outputs = dict(state.get("subagent_outputs", {}))
    existing_recs = list(outputs.get("trust_recommendations", []))
    category = outputs.get("trust_category", "general")

    try:
        async with AsyncSessionLocal() as db:
            network = TrustNetwork(agent_id=agent_id, db=db)
            trusted = await network.get_trusted_agents()
    except Exception:
        logger.exception("Failed to load trust network for peer consultation")
        return state

    peers_to_consult = trusted[:2]
    if not peers_to_consult:
        logger.info("[%s] PEERS no trusted peers found — skipping A2A", agent_id[:8])
        return state

    logger.info("[%s] PEERS consulting %d peer(s): %s",
                agent_id[:8], len(peers_to_consult),
                ", ".join(f"{pid[:8]}(w={w:.2f})" for pid, w in peers_to_consult))

    # Generate a focused question once, then consult all peers in parallel
    try:
        peer_question = await _generate_peer_question(user_query, category)
        logger.info("[%s] PEERS generated question: %r", agent_id[:8], peer_question)
    except Exception:
        logger.exception("Failed to generate peer question — falling back to raw query")
        peer_question = user_query

    tasks = [_consult_peer(agent_id, peer_id, weight, peer_question) for peer_id, weight in peers_to_consult]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    consultation_recs = [r for r in results if isinstance(r, dict)]

    logger.info("[%s] PEERS got %d/%d responses", agent_id[:8], len(consultation_recs), len(peers_to_consult))
    outputs["trust_recommendations"] = existing_recs + consultation_recs
    return {**state, "subagent_outputs": outputs}


trust_query_graph = _build_graph()


async def fetch_trust_context_fast(state: AgentState) -> dict:
    """Run only category identification + vector fetch — no A2A peer consultation.

    Used by product_search to get SharedMemory recommendations without the latency
    of live peer consultation (which is reserved for explicit trust_query intent).
    """
    state = _identify_category_node(state)
    state = await _fetch_node(state)
    return state.get("subagent_outputs", {})
