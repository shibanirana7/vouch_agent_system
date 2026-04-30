from typing import TypedDict
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    messages: list[BaseMessage]
    agent_id: str
    preferences_context: str
    trust_context: str
    current_task: str              # "preference_update" | "trust_query" | "product_search" | "decision" | "review" | "general"
    subagent_outputs: dict         # keyed by subagent name, holds their output strings
    auto_wishlist_additions: list  # product names auto-added to wishlist this turn
    reflection_ok: bool            # True = proceed to respond; False = retry search
    reflection_retries: int        # number of search retries so far (max 1)
    is_consultation: bool          # True = being called by another agent; skip own trust queries
