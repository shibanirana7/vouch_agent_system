"""
Product search subagent: refines the user query using preferences context,
searches the catalog, and filters results with LLM ranking.
"""
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from ..state import AgentState
from ..llm import get_llm
from .._utils import _text
from ...mcp_server.handlers import search_products
from ...data.catalog import PRODUCT_CATALOG
import json


def _build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("refine_query", _refine_node)
    graph.add_node("search", _search_node)
    graph.add_node("rank", _rank_node)
    graph.set_entry_point("refine_query")
    graph.add_edge("refine_query", "search")
    graph.add_edge("search", "rank")
    graph.add_edge("rank", END)
    return graph.compile()


async def _refine_node(state: AgentState) -> AgentState:
    llm = get_llm()
    last_message = state["messages"][-1].content if state["messages"] else ""
    preferences = state.get("preferences_context", "")
    response = await llm.ainvoke([
        SystemMessage(content=(
            "You are helping refine a beauty product search query. "
            "Given the user's message and their known preferences, produce a short, specific search query (under 15 words). "
            "Also extract a max price (as a number, or 9999 if not mentioned). "
            "Reply in this exact format:\nQUERY: <the refined query>\nMAX_PRICE: <number>"
        )),
        HumanMessage(content=f"User message: {last_message}\n\nUser preferences:\n{preferences}"),
    ])
    lines = {line.split(":")[0].strip(): line.split(":", 1)[1].strip()
             for line in _text(response.content).strip().splitlines() if ":" in line}
    refined_query = lines.get("QUERY", last_message)
    try:
        max_price = float(lines.get("MAX_PRICE", "9999"))
    except ValueError:
        max_price = 9999.0

    outputs = dict(state.get("subagent_outputs", {}))
    outputs["refined_query"] = refined_query
    outputs["max_price"] = max_price
    return {**state, "subagent_outputs": outputs}


async def _search_node(state: AgentState) -> AgentState:
    outputs = dict(state.get("subagent_outputs", {}))
    results = await search_products(
        query=outputs.get("refined_query", ""),
        max_price=outputs.get("max_price", 9999.0),
        category=outputs.get("trust_category", "general"),
    )
    outputs["product_results"] = results
    return {**state, "subagent_outputs": outputs}


_CATALOG_BY_NAME = {p["name"].lower(): p for p in PRODUCT_CATALOG}


async def _rank_node(state: AgentState) -> AgentState:
    llm = get_llm()
    outputs = dict(state.get("subagent_outputs", {}))
    catalog_results = outputs.get("product_results", [])
    preferences = state.get("preferences_context", "")
    trust_recs = outputs.get("trust_recommendations", [])

    # Build a lookup of friend-reviewed products by name
    search_category = outputs.get("trust_category", "general")
    friend_rec_map: dict[str, dict] = {}
    for rec in trust_recs:
        name = rec.get("product", "").lower()
        if name and name not in friend_rec_map:
            friend_rec_map[name] = rec

    # Mark catalog results that are also friend-reviewed (this is the common case —
    # the catalog search and trust network both return the same popular product).
    catalog_results = [dict(p) for p in catalog_results]  # shallow copy so we can mutate
    for p in catalog_results:
        rec = friend_rec_map.get(p["name"].lower())
        if rec:
            p["friend_recommended"] = True
            p["friend_trust_weight"] = rec.get("trust_weight", 0)
            p["friend_rating"] = rec.get("rating", 0)

    # Add friend-reviewed products that the catalog search didn't return,
    # filtered to the requested category.
    seen_names = {p["name"].lower() for p in catalog_results}
    friend_products = []
    for rec in trust_recs:
        name = rec.get("product", "")
        if name.lower() not in seen_names:
            catalog_entry = _CATALOG_BY_NAME.get(name.lower())
            if catalog_entry:
                if search_category != "general" and catalog_entry.get("category") != search_category:
                    continue
                friend_products.append({
                    **catalog_entry,
                    "friend_recommended": True,
                    "friend_trust_weight": rec.get("trust_weight", 0),
                    "friend_rating": rec.get("rating", 0),
                })
                seen_names.add(name.lower())

    all_products = catalog_results + friend_products
    if not all_products:
        return state

    # Build product list for LLM, marking friend-recommended items
    product_lines = []
    for i, p in enumerate(all_products):
        tag = ""
        if p.get("friend_recommended"):
            tag = f" [friend recommended — trust {p['friend_trust_weight']}, rated {p['friend_rating']}/5]"
        product_lines.append(
            f"{i+1}. {p['name']} (${p['price']}) — {', '.join(p.get('qualities', []))}{tag}"
        )

    # Build trust context for the ranking prompt
    trust_context = ""
    if trust_recs:
        trust_lines = [
            f"- {r.get('product', r.get('product_name', 'unknown'))} (friend rating: {r.get('rating', '?')}/5, trust weight: {r.get('trust_weight', 0):.2f})"
            for r in trust_recs[:5]
        ]
        trust_context = "\nFriend recommendations:\n" + "\n".join(trust_lines)

    response = await llm.ainvoke([
        SystemMessage(content=(
            "Rank these beauty products for this user. "
            "Factor in both their personal preferences AND friend recommendations — "
            "products marked [friend recommended] with high trust weight and high rating should rank higher. "
            "Return ONLY the numbers in ranked order, comma-separated (e.g. '2,1,3')."
        )),
        HumanMessage(content=(
            f"User preferences:\n{preferences}"
            f"{trust_context}\n\n"
            f"Products:\n" + "\n".join(product_lines)
        )),
    ])
    try:
        order = [int(x.strip()) - 1 for x in _text(response.content).strip().split(",")]
        ranked = [all_products[i] for i in order if 0 <= i < len(all_products)]
        # Append anything the LLM dropped
        ranked_names = {p["name"] for p in ranked}
        ranked += [p for p in all_products if p["name"] not in ranked_names]
    except Exception:
        ranked = all_products

    outputs["ranked_products"] = ranked
    return {**state, "subagent_outputs": outputs}


product_search_graph = _build_graph()
