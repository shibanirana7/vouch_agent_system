"""
Review subagent: after a purchase, prompts the user for their experience
and writes a structured review to shared memory.
"""
import re
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from ..state import AgentState
from ..llm import get_llm
from .._utils import _text
from ...mcp_server.handlers import contribute_review


def _build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("write_review", _write_review_node)
    graph.add_node("store_review", _store_review_node)
    graph.set_entry_point("write_review")
    graph.add_edge("write_review", "store_review")
    graph.add_edge("store_review", END)
    return graph.compile()


async def _write_review_node(state: AgentState) -> AgentState:
    llm = get_llm()
    last_message = state["messages"][-1].content if state["messages"] else ""

    # Extract exact product name and rating from structured prefix when available.
    # Format: "PRODUCT:<name>|RATING:<n>\n<user message>"
    prefix_match = re.match(r"PRODUCT:(.+?)\|RATING:(\d)\n", last_message)
    if prefix_match:
        exact_product = prefix_match.group(1)
        exact_rating = int(prefix_match.group(2))
        clean_message = last_message[prefix_match.end():]
    else:
        exact_product = None
        exact_rating = None
        clean_message = last_message

    # Use LLM only to write the review text (and category/product fallback)
    response = await llm.ainvoke([
        SystemMessage(content=(
            "Based on the user's feedback about a recent beauty purchase, write a concise product review "
            "(2-3 sentences). Extract: product name, category, and review text. "
            "Reply in this exact format:\n"
            "PRODUCT: <product name>\n"
            "CATEGORY: <category>\n"
            "REVIEW: <review text>"
        )),
        HumanMessage(content=clean_message),
    ])
    lines = {}
    for line in _text(response.content).strip().splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            lines[key.strip().upper()] = val.strip()

    outputs = dict(state.get("subagent_outputs", {}))
    outputs["review_data"] = {
        "product": exact_product or lines.get("PRODUCT", "Unknown product"),
        "category": lines.get("CATEGORY", "general"),
        "rating": exact_rating if exact_rating is not None else 3,
        "review_text": lines.get("REVIEW", clean_message),
    }
    return {**state, "subagent_outputs": outputs}


async def _store_review_node(state: AgentState) -> AgentState:
    data = state["subagent_outputs"].get("review_data", {})
    if data:
        await contribute_review(
            agent_id=state["agent_id"],
            product=data["product"],
            category=data["category"],
            review_text=data["review_text"],
            rating=data["rating"],
        )
    return state


review_graph = _build_graph()
