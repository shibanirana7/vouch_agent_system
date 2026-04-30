"""
Preference subagent: extracts preference statements from user messages
and persists them via the MCP update_preference tool.
"""
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from ..state import AgentState
from ..llm import get_llm
from .._utils import _text
from ...mcp_server.handlers import update_preference


def _build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("extract", _extract_node)
    graph.add_node("store", _store_node)
    graph.set_entry_point("extract")
    graph.add_edge("extract", "store")
    graph.add_edge("store", END)
    return graph.compile()


async def _extract_node(state: AgentState) -> AgentState:
    llm = get_llm()
    last_message = state["messages"][-1].content if state["messages"] else ""
    response = await llm.ainvoke([
        SystemMessage(content=(
            "Extract explicit or implicit user preferences about beauty and makeup products "
            "from the message below. Output one preference per line, starting each with a dash. "
            "Focus on: price range, brands, ingredients, finish (matte/dewy/glossy), coverage, "
            "values (cruelty-free, vegan, clean beauty), and product categories. "
            "If no preferences are present, output: NONE"
        )),
        HumanMessage(content=last_message),
    ])
    raw = _text(response.content).strip()
    prefs = [line.lstrip("- ").strip() for line in raw.splitlines() if line.strip() and line.strip() != "NONE"]
    outputs = dict(state.get("subagent_outputs", {}))
    outputs["preference_agent"] = prefs
    return {**state, "subagent_outputs": outputs}


async def _store_node(state: AgentState) -> AgentState:
    prefs: list[str] = state["subagent_outputs"].get("preference_agent", [])
    for pref in prefs:
        await update_preference(agent_id=state["agent_id"], preference_text=pref)
    return state


preference_graph = _build_graph()
