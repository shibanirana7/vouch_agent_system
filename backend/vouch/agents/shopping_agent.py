"""
Main shopping agent graph.
Hydrates state from DB + ChromaDB, classifies intent, routes to subagraphs,
then composes a final user-facing response.
"""
import logging
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, END
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger(__name__)

from .state import AgentState
from .llm import get_llm
from ._utils import _text
from .subagents.preference_agent import preference_graph
from .subagents.trust_query_agent import trust_query_graph
from .subagents.product_search_agent import product_search_graph
from .subagents.decision_agent import decision_graph
from .subagents.review_agent import review_graph
from ..memory.agent_memory import AgentMemory
from ..trust.graph import TrustNetwork
from ..database import AsyncSessionLocal
from ..mcp_server.handlers import add_to_wishlist, check_and_refill_wishlist


# ── Intent classification ─────────────────────────────────────────────────────

INTENTS = ["preference_update", "trust_query", "product_search", "decision", "review", "general"]


def _aid(state: AgentState) -> str:
    """Short agent ID prefix for log lines."""
    return state["agent_id"][:8]


async def _hydrate_state(state: AgentState) -> AgentState:
    """Load preferences and trust context, and auto-refill wishlist for overdue items."""
    agent_id = state["agent_id"]
    logger.info("[%s] HYDRATE start", _aid(state))
    mem = AgentMemory(agent_id)
    prefs_ctx = mem.build_preference_context()

    async with AsyncSessionLocal() as db:
        network = TrustNetwork(agent_id=agent_id, db=db)
        trust_ctx = await network.get_trust_summary()

    # Auto-add products due for replacement (non-critical — never fail the chat)
    try:
        replacements = await check_and_refill_wishlist(agent_id)
    except Exception:
        replacements = []

    logger.info("[%s] HYDRATE done — prefs=%d chars trust=%d chars replacements=%s",
                _aid(state), len(prefs_ctx), len(trust_ctx), replacements or "none")
    return {
        **state,
        "preferences_context": prefs_ctx,
        "trust_context": trust_ctx,
        "auto_wishlist_additions": replacements,
    }


async def _classify_intent(state: AgentState) -> AgentState:
    llm = get_llm()
    last_message = state["messages"][-1].content if state["messages"] else ""
    response = await llm.ainvoke([
        SystemMessage(content=(
            "Classify the user's intent into exactly one of these categories:\n"
            "- preference_update: user is expressing what they like or dislike about products or beauty in general\n"
            "- trust_query: user explicitly asks what their trusted friends or network recommend\n"
            "- product_search: user is looking for, asking about, or wants to find a specific type of product (e.g. 'recommend a foundation', 'what mascara should I get', 'find me a red lipstick')\n"
            "- decision: user wants a full buying recommendation with comparison across options\n"
            "- review: user is sharing their experience or opinion about a product they already bought\n"
            "- general: greetings, questions about their wishlist or account, or anything that doesn't fit the above\n\n"
            "When in doubt between product_search and general, prefer product_search if any beauty product is mentioned.\n"
            "Reply with ONLY the category name, nothing else."
        )),
        HumanMessage(content=last_message),
    ])
    intent = _text(response.content).strip().lower()
    if intent not in INTENTS:
        intent = "general"
    logger.info("[%s] INTENT: %s | msg=%r", _aid(state),
                intent, (state["messages"][-1].content if state["messages"] else "")[:80])
    return {**state, "current_task": intent}


def _route_intent(state: AgentState) -> str:
    return state.get("current_task", "general")


async def _run_preference_subgraph(state: AgentState) -> AgentState:
    result = await preference_graph.ainvoke(state)
    return {**state, "subagent_outputs": result.get("subagent_outputs", {})}


async def _run_trust_subgraph(state: AgentState) -> AgentState:
    result = await trust_query_graph.ainvoke(state)
    return {**state, "subagent_outputs": result.get("subagent_outputs", {})}


async def _run_product_search_subgraph(state: AgentState) -> AgentState:
    # Run the full trust graph (vector fetch + A2A peer consultation) on first pass.
    # The caching check prevents re-running on reflection retries.
    existing_outputs = state.get("subagent_outputs", {})
    if existing_outputs.get("trust_recommendations") is None:
        logger.info("[%s] PRODUCT_SEARCH: running trust graph (first pass)", _aid(state))
        trust_result = await trust_query_graph.ainvoke(state)
        trust_outputs = trust_result.get("subagent_outputs", {})
        n_recs = len(trust_outputs.get("trust_recommendations", []))
        logger.info("[%s] PRODUCT_SEARCH: trust graph done — %d recommendations", _aid(state), n_recs)
    else:
        trust_outputs = existing_outputs
        logger.info("[%s] PRODUCT_SEARCH: using cached trust results (reflection retry)", _aid(state))

    state_with_trust = {**state, "subagent_outputs": trust_outputs}
    search_result = await product_search_graph.ainvoke(state_with_trust)
    search_outputs = search_result.get("subagent_outputs", {})
    merged = {**trust_outputs, **search_outputs}
    n_products = len(merged.get("ranked_products", []))
    logger.info("[%s] PRODUCT_SEARCH: catalog search done — %d ranked products", _aid(state), n_products)
    return {**state, "subagent_outputs": merged}


async def _run_decision_subgraph(state: AgentState) -> AgentState:
    # product_search already runs trust internally — don't call trust separately
    state = await _run_product_search_subgraph(state)
    result = await decision_graph.ainvoke(state)
    return {**state, "subagent_outputs": result.get("subagent_outputs", {})}


async def _reflect(state: AgentState) -> AgentState:
    """Self-critique node: checks if ranked products match the user's preferences.

    If they don't match and we haven't retried yet, routes back to product_search
    with a note to try different results. Otherwise passes through.
    """
    outputs = state.get("subagent_outputs", {})
    products = outputs.get("ranked_products", [])
    prefs = state.get("preferences_context", "")
    retries = state.get("reflection_retries", 0)

    # Skip reflection if we have nothing to evaluate or already retried
    if not products or not prefs or "No preferences" in prefs or retries >= 1:
        return {**state, "reflection_ok": True}

    llm = get_llm()
    product_summary = "\n".join(
        f"- {p['name']} by {p['brand']} (${p['price']}): {', '.join(p.get('qualities', []))}"
        for p in products[:3]
    )
    try:
        response = await llm.ainvoke([
            SystemMessage(content=(
                "You are a quality-checking agent for a beauty shopping assistant.\n"
                "Given the user's recorded preferences and the proposed product recommendations, "
                "decide whether the recommendations are a good fit.\n"
                "Reply with ONLY one word: 'good' if they match well, or 'refine' if they do not."
            )),
            HumanMessage(content=(
                f"User preferences:\n{prefs}\n\n"
                f"Proposed products:\n{product_summary}"
            )),
        ])
        verdict = _text(response.content).strip().lower()
        ok = "good" in verdict
        if not ok:
            logger.info("[%s] REFLECT verdict=%r", _aid(state), verdict[:200])
    except Exception:
        logger.exception("Reflection LLM call failed — passing through")
        ok = True

    new_retries = retries if ok else retries + 1
    if not ok:
        logger.info("[%s] REFLECT: FAIL — triggering retry #%d", _aid(state), new_retries)
    else:
        logger.info("[%s] REFLECT: PASS (retries so far=%d)", _aid(state), retries)
    return {**state, "reflection_ok": ok, "reflection_retries": new_retries}


def _route_reflect(state: AgentState) -> str:
    if state.get("reflection_ok", True):
        return "respond"
    return "product_search"


async def _run_review_subgraph(state: AgentState) -> AgentState:
    result = await review_graph.ainvoke(state)
    return {**state, "subagent_outputs": result.get("subagent_outputs", {})}


async def _respond(state: AgentState) -> AgentState:
    """Compose the final user-facing message from subagent outputs."""
    llm = get_llm()
    task = state.get("current_task", "general")
    outputs = state.get("subagent_outputs", {})
    agent_id = state["agent_id"]
    last_message = state["messages"][-1].content if state["messages"] else ""

    wishlist_note = ""

    if task == "decision" and outputs.get("decision"):
        final_text = outputs["decision"]
        # Auto-add top product from decision pipeline
        top = (outputs.get("ranked_products") or [None])[0]
        if top:
            try:
                result = await add_to_wishlist(
                    agent_id=agent_id,
                    product_name=top["name"],
                    description=", ".join(top.get("qualities", [])[:2]),
                    target_price=top["price"],
                    is_recurring=False,
                    recurrence_interval_days=None,
                    priority=2,
                )
                if result.get("status") == "added":
                    wishlist_note = f"\n\nI've added **{top['name']}** to your wishlist."
                elif result.get("status") == "already_in_wishlist":
                    wishlist_note = f"\n\n**{top['name']}** is already in your wishlist."
            except Exception:
                logger.exception("Failed to add decision result to wishlist")

    elif task == "product_search" and outputs.get("ranked_products"):
        products = outputs["ranked_products"][:3]
        prefs = state.get("preferences_context", "")
        product_summary = "\n".join(
            "- {name} by {brand} (${price}): {quals}{friend}".format(
                name=p["name"],
                brand=p["brand"],
                price=p["price"],
                quals=", ".join(p.get("qualities", [])),
                friend=f" [friend recommended]" if p.get("friend_recommended") else "",
            )
            for p in products
        )
        trust_recs = outputs.get("trust_recommendations", [])
        catalog_names_lower = {p["name"].lower() for p in products}

        # A2A peer opinions — what consulted agents said about the query
        peer_opinions = [r for r in trust_recs if r.get("source") == "a2a_consultation"]
        peer_note = ""
        if peer_opinions:
            peer_note = "\n\nOpinions from trusted friends I consulted:\n" + "\n".join(
                f"- Friend said: {r['text']}" for r in peer_opinions[:3]
            )

        # SharedMemory friend reviews not already in ranked products
        extra_friend_recs = [
            r for r in trust_recs
            if r.get("source") != "a2a_consultation"
            and r.get("product", "").lower() not in catalog_names_lower
            and r.get("product")
        ]
        friend_note = ""
        if extra_friend_recs:
            friend_note = "\n\nFriends also mentioned these specific products:\n" + "\n".join(
                f"- {r['product']}" for r in extra_friend_recs[:3]
            )

        explanation = await llm.ainvoke([
            SystemMessage(content=(
                "You are a personal beauty shopping assistant. Present product options and explain "
                "why each fits this user's specific preferences. Be concise, personal, and direct.\n"
                "Format: short bulleted list — bold product name, price, one sentence why it fits them.\n"
                "If a product is friend-recommended, say so.\n"
                "If you have opinions from consulted friends, weave them in naturally — "
                "e.g. 'I checked in with your friend and they said...' — don't just list them separately."
            )),
            HumanMessage(content=(
                f"User's recorded preferences:\n{prefs or 'None recorded yet.'}\n\n"
                f"Products to present:\n{product_summary}"
                f"{peer_note}"
                f"{friend_note}\n\n"
                f"User's query: {last_message}"
            )),
        ])
        final_text = _text(explanation.content).strip()

        # Auto-add the top result (friend-recommended or not) to wishlist
        top = products[0]
        try:
            result = await add_to_wishlist(
                agent_id=agent_id,
                product_name=top["name"],
                description=", ".join(top.get("qualities", [])[:2]),
                target_price=top["price"],
                is_recurring=False,
                recurrence_interval_days=None,
                priority=2,
            )
            if result.get("status") == "added":
                wishlist_note = f"\n\nI've added **{top['name']}** to your wishlist."
            elif result.get("status") == "already_in_wishlist":
                wishlist_note = f"\n\n**{top['name']}** is already in your wishlist."
        except Exception:
            logger.exception("Failed to add product search result to wishlist")

    elif task == "trust_query" and outputs.get("trust_recommendations"):
        recs = outputs["trust_recommendations"][:3]
        n_recs = len(recs)
        prefs = state.get("preferences_context", "")
        # Include the targeted question used for each peer consultation so the
        # synthesis can explain exactly what was asked and why
        rec_summary = "\n".join(
            "- [asked: '{q}'] response (trust {w:.1f}): {t}".format(
                q=r.get("targeted_question", last_message),
                w=r.get("trust_weight", 0),
                t=r.get("text", ""),
            )
            for r in recs
        )
        synthesis = await llm.ainvoke([
            SystemMessage(content=(
                "You are a personal beauty shopping assistant summarizing what your user's trusted connections said.\n"
                "Rewrite the following responses in YOUR voice as the user's own agent. "
                "For each peer consultation: mention WHAT you asked them (from the [asked: ...] field) and WHY that question was relevant to the user's preferences. "
                "Then share what they said. Use phrasing like 'I asked your friend specifically about X because you prefer Y — they said...'.\n"
                "Do NOT quote verbatim. Do NOT say 'my user'. Speak directly to the user.\n"
                f"IMPORTANT: There {'is exactly 1 response' if n_recs == 1 else f'are exactly {n_recs} responses'}. "
                "Use singular they/them pronouns. Keep it concise and natural."
            )),
            HumanMessage(content=(
                f"User asked: {last_message}\n\n"
                f"User's preferences:\n{prefs or 'None recorded.'}\n\n"
                f"Friend responses ({n_recs} total):\n{rec_summary}"
            )),
        ])
        final_text = _text(synthesis.content).strip()

    elif task == "preference_update":
        prefs = outputs.get("preference_agent", [])
        if prefs:
            final_text = f"Got it! I've noted {len(prefs)} new preference(s) for you:\n" + "\n".join(f"- {p}" for p in prefs)
        else:
            final_text = "I didn't catch any specific preferences there. Try sharing what you love or avoid in beauty products!"

        # Autonomously discover and connect similar agents after any preference update
        try:
            new_connections = await _discover_and_connect(agent_id)
            if new_connections:
                final_text += f"\n\nI also found {len(new_connections)} agent{'s' if len(new_connections) > 1 else ''} with similar taste and sent {'them' if len(new_connections) > 1 else 'them'} a connection request — they'll need to accept it in their network."
        except Exception:
            logger.exception("Auto-discovery failed — skipping")

    elif task == "review":
        data = outputs.get("review_data", {})
        if data:
            final_text = f"Thanks for sharing! I've stored your review for **{data.get('product', 'that product')}** and updated your preference profile. Your trusted connections will see it when they shop."
            # Reviews also update taste profile — try discovery
            try:
                new_connections = await _discover_and_connect(agent_id)
                if new_connections:
                    final_text += f"\n\nBased on your review, I found {len(new_connections)} agent{'s' if len(new_connections) > 1 else ''} with similar taste and sent {'them' if len(new_connections) > 1 else 'them'} a connection request — they'll need to accept it in their network."
            except Exception:
                logger.exception("Auto-discovery after review failed — skipping")
        else:
            final_text = "Thanks for the feedback! I wasn't able to extract a review — could you tell me more about the product and what you thought?"

    else:
        response = await llm.ainvoke([
            SystemMessage(content=(
                f"You are a personal beauty shopping assistant.\n\n"
                f"Based on this user's purchase history and past interactions, here is what you know about their tastes:\n{state.get('preferences_context', 'Nothing recorded yet — this is a fresh start.')}\n\n"
                f"Their trusted connections:\n{state.get('trust_context', 'None yet.')}\n\n"
                "Important: only reference things the user has explicitly told you in this conversation, or clearly attribute information to their purchase history (e.g. 'Based on your past purchases...'). Never present inferred data as something the user said. "
                "Use singular they/them pronouns when referring to any person."
            )),
            HumanMessage(content=last_message),
        ])
        final_text = _text(response.content).strip()

    # Surface replacement reminders added during hydration
    replacements = state.get("auto_wishlist_additions", [])
    if replacements:
        names = ", ".join(f"**{n}**" for n in replacements)
        final_text += f"\n\nHeads up: I've added {names} to your wishlist — {'it looks' if len(replacements) == 1 else 'they look'} due for replacement based on your purchase history."

    if wishlist_note:
        final_text += wishlist_note

    new_messages = list(state["messages"]) + [AIMessage(content=final_text)]
    return {**state, "messages": new_messages}


# ── Build the main graph ──────────────────────────────────────────────────────

def build_shopping_agent() -> object:
    graph = StateGraph(AgentState)

    graph.add_node("hydrate_state", _hydrate_state)
    graph.add_node("classify_intent", _classify_intent)
    graph.add_node("preference_update", _run_preference_subgraph)
    graph.add_node("trust_query", _run_trust_subgraph)
    graph.add_node("product_search", _run_product_search_subgraph)
    graph.add_node("reflect", _reflect)
    graph.add_node("decision", _run_decision_subgraph)
    graph.add_node("review", _run_review_subgraph)
    graph.add_node("general", lambda s: s)
    graph.add_node("respond", _respond)

    graph.set_entry_point("hydrate_state")
    graph.add_edge("hydrate_state", "classify_intent")
    graph.add_conditional_edges(
        "classify_intent",
        _route_intent,
        {
            "preference_update": "preference_update",
            "trust_query": "trust_query",
            "product_search": "product_search",
            "decision": "decision",
            "review": "review",
            "general": "general",
        },
    )
    graph.add_edge("product_search", "respond")
    graph.add_edge("decision", "reflect")
    graph.add_conditional_edges("reflect", _route_reflect, {"respond": "respond", "product_search": "product_search"})
    for node in ["preference_update", "trust_query", "review", "general"]:
        graph.add_edge(node, "respond")
    graph.add_edge("respond", END)

    return graph.compile()


shopping_agent = build_shopping_agent()


_WINDOW = 10  # number of prior turns to keep in context


async def _discover_and_connect(agent_id: str) -> list[str]:
    """Find agents with similar preferences and auto-add them to the trust network.

    Runs a pgvector similarity search across all agents' preference collections,
    then creates acquaintance/friend relationships for any new matches.
    Returns list of newly connected agent IDs.
    """
    from ..memory.store import find_similar_agents

    loop = __import__("asyncio").get_event_loop()
    candidates = await loop.run_in_executor(
        None, lambda: find_similar_agents(agent_id, n=5, min_similarity=0.75)
    )
    if not candidates:
        return []

    async with AsyncSessionLocal() as db:
        network = TrustNetwork(agent_id=agent_id, db=db)
        return await network.auto_connect(candidates)


async def _consult_response(agent_id: str, query: str) -> str:
    """Generate a consultation response: share this agent's user's own experience/preferences.

    The consulted agent speaks from its user's perspective — what they've bought, loved,
    and would personally recommend — rather than running a product search.
    """
    from ..memory.shared_memory import SharedMemory
    from ..models.purchase import PurchaseRecord
    from sqlalchemy import select as sa_select

    mem = AgentMemory(agent_id)
    prefs_ctx = mem.build_preference_context()

    # Include own reviews so the agent can reference specific products it's tried
    own_reviews = SharedMemory().get_own_reviews(agent_id)
    vector_products = {r.get("product", "").lower() for r in own_reviews}

    reviews_ctx = ""
    if own_reviews:
        lines = [f"- {r['product']}: {r['text'].split(': ', 1)[-1]}" for r in own_reviews]
        reviews_ctx = "\nProducts my user has tried:\n" + "\n".join(lines)

    # Also pull DB purchases with opinions — covers cases where SharedMemory embedding
    # failed or the review was never contributed (e.g. early-return on LLM failure)
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                sa_select(PurchaseRecord).where(
                    PurchaseRecord.agent_id == agent_id,
                    PurchaseRecord.opinion_text.isnot(None),
                )
            )
            db_purchases = result.scalars().all()
        extra_lines = []
        for p in db_purchases:
            if p.product_name.lower() not in vector_products and p.opinion_text:
                extra_lines.append(f"- {p.product_name}: {p.opinion_text[:200]}")
        if extra_lines:
            reviews_ctx += "\nAdditional products with comments:\n" + "\n".join(extra_lines)
    except Exception:
        logger.exception("Failed to load DB purchase opinions for consultation")

    llm = get_llm()
    response = await llm.ainvoke([
        SystemMessage(content=(
            "You are a personal shopping agent representing your user. "
            "Another agent is consulting you on behalf of their user who wants a recommendation.\n\n"
            "Your job: share what YOUR user has personally tried, loved, or recommends — "
            "based on their real purchase history, stated preferences, and product reviews. "
            "Speak naturally as if your user is a friend giving advice: "
            "'My user swears by...', 'They tried X and rated it 5/5 — highly recommend.'\n\n"
            "IMPORTANT: Use singular they/them pronouns for your user (not she/her or he/him).\n"
            "Do NOT run a product search. Do NOT recommend things your user hasn't tried. "
            "If your user has no relevant history, be honest about that.\n\n"
            f"Your user's taste profile:\n{prefs_ctx or 'No preferences recorded yet.'}"
            f"{reviews_ctx}"
        )),
        HumanMessage(content=query),
    ])
    return _text(response.content).strip()


async def chat(
    agent_id: str,
    message: str,
    history: list[dict] | None = None,
    is_consultation: bool = False,
) -> dict:
    """Public interface: send a message to an agent, get a response string.

    history: list of {"role": "user"|"assistant", "content": str} — last N turns
             from the frontend Zustand store. Capped to _WINDOW entries.
    is_consultation: True when called by another agent — shares the agent's user's
                     personal experience instead of running a product search.
    """
    logger.info("[%s] CHAT %s | msg=%r", agent_id[:8],
                "consultation" if is_consultation else "user", message[:100])
    if is_consultation:
        text = await _consult_response(agent_id, message)
        logger.info("[%s] CONSULT response=%d chars", agent_id[:8], len(text))
        return {"response": text, "reflection_retries": 0}

    prior: list = []
    for turn in (history or [])[-_WINDOW:]:
        if turn["role"] == "user":
            prior.append(HumanMessage(content=turn["content"]))
        else:
            prior.append(AIMessage(content=turn["content"]))

    state: AgentState = {
        "messages": prior + [HumanMessage(content=message)],
        "agent_id": agent_id,
        "preferences_context": "",
        "trust_context": "",
        "current_task": "general",
        "subagent_outputs": {},
        "auto_wishlist_additions": [],
        "reflection_ok": True,
        "reflection_retries": 0,
        "is_consultation": False,
    }
    result = await shopping_agent.ainvoke(state)
    ai_messages = [m for m in result["messages"] if isinstance(m, AIMessage)]
    text = ai_messages[-1].content if ai_messages else "I couldn't process that. Please try again."
    retries = result.get("reflection_retries", 0)
    logger.info("[%s] DONE intent=%s retries=%d response=%d chars",
                agent_id[:8], result.get("current_task", "?"), retries, len(text))
    return {"response": text, "reflection_retries": retries}
