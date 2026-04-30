"""
Decision subagent: synthesizes trust recommendations + product search results
+ user preferences into a final purchase recommendation.
"""
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from ..state import AgentState
from ..llm import get_llm
from .._utils import _text
import json


def _build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("synthesize", _synthesize_node)
    graph.set_entry_point("synthesize")
    graph.add_edge("synthesize", END)
    return graph.compile()


async def _synthesize_node(state: AgentState) -> AgentState:
    llm = get_llm()
    preferences = state.get("preferences_context", "No preferences recorded.")
    trust_recs = state["subagent_outputs"].get("trust_recommendations", [])
    products = state["subagent_outputs"].get("ranked_products", [])
    last_message = state["messages"][-1].content if state["messages"] else ""

    trust_block = (
        "\n".join(f"- {r.get('text', '')} (trust weight: {r.get('trust_weight', 0):.1f})" for r in trust_recs[:5])
        if trust_recs else "No trusted recommendations available."
    )
    product_block = (
        "\n".join(
            f"- {p['name']} by {p['brand']}, ${p['price']} — {', '.join(p.get('qualities', []))}"
            for p in products[:5]
        )
        if products else "No products found."
    )

    response = await llm.ainvoke([
        SystemMessage(content=(
            "You are a personal beauty shopping assistant. Based on the user's preferences, "
            "trusted friend recommendations, and available products, give a clear, specific purchase recommendation. "
            "Explain WHY this product fits the user. Be concise and helpful."
        )),
        HumanMessage(content=(
            f"User request: {last_message}\n\n"
            f"User preferences:\n{preferences}\n\n"
            f"Trusted friend recommendations:\n{trust_block}\n\n"
            f"Available products:\n{product_block}"
        )),
    ])

    outputs = dict(state.get("subagent_outputs", {}))
    outputs["decision"] = _text(response.content).strip()
    return {**state, "subagent_outputs": outputs}


decision_graph = _build_graph()
