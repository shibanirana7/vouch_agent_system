"""
MCP tool server for Vouch shopping agents.
Mounted into the FastAPI app at /mcp.
"""
from fastmcp import FastMCP
from . import handlers

mcp = FastMCP(name="vouch-tools")


@mcp.tool()
async def search_products(query: str, max_price: float = 9999.0, category: str = "general") -> list[dict]:
    """Search for products matching the query. Returns a list of product candidates."""
    return await handlers.search_products(query=query, max_price=max_price, category=category)


@mcp.tool()
async def query_trust_network(agent_id: str, category: str, query: str) -> list[dict]:
    """Fetch weighted product recommendations from the agent's trusted connections."""
    return await handlers.query_trust_network(agent_id=agent_id, category=category, query=query)


@mcp.tool()
async def add_to_wishlist(
    agent_id: str,
    product_name: str,
    description: str = "",
    target_price: float | None = None,
    is_recurring: bool = False,
    recurrence_interval_days: int | None = None,
    priority: int = 1,
) -> dict:
    """Add a product to the agent's wishlist."""
    return await handlers.add_to_wishlist(
        agent_id=agent_id,
        product_name=product_name,
        description=description,
        target_price=target_price,
        is_recurring=is_recurring,
        recurrence_interval_days=recurrence_interval_days,
        priority=priority,
    )


@mcp.tool()
async def get_wishlist(agent_id: str) -> list[dict]:
    """Return the agent's current wishlist."""
    return await handlers.get_wishlist(agent_id=agent_id)


@mcp.tool()
async def record_purchase(
    agent_id: str,
    product_name: str,
    price: float,
    category: str = "general",
    url: str = "",
    was_recommended: bool = False,
    recommending_agent_id: str | None = None,
) -> dict:
    """Record a purchase and embed it into the agent's purchase history."""
    return await handlers.record_purchase(
        agent_id=agent_id,
        product_name=product_name,
        price=price,
        category=category,
        url=url,
        was_recommended=was_recommended,
        recommending_agent_id=recommending_agent_id,
    )


@mcp.tool()
async def update_preference(agent_id: str, preference_text: str) -> dict:
    """Store a new preference statement for the agent."""
    return await handlers.update_preference(agent_id=agent_id, preference_text=preference_text)


@mcp.tool()
async def rate_recommendation(purchase_id: str, satisfaction_score: int) -> dict:
    """Rate a purchase 1-5. Updates the purchase record."""
    return await handlers.rate_recommendation(purchase_id=purchase_id, satisfaction_score=satisfaction_score)


@mcp.tool()
async def confirm_wishlist_purchase(wishlist_item_id: str, actual_price: float | None = None) -> dict:
    """Confirm a wishlist item was purchased. Removes it from wishlist and adds to purchase history."""
    return await handlers.confirm_wishlist_purchase(
        wishlist_item_id=wishlist_item_id, actual_price=actual_price
    )


@mcp.tool()
async def contribute_review(
    agent_id: str,
    product: str,
    category: str,
    review_text: str,
    rating: int,
) -> dict:
    """Write a product review that trusted agents can see."""
    return await handlers.contribute_review(
        agent_id=agent_id,
        product=product,
        category=category,
        review_text=review_text,
        rating=rating,
    )
