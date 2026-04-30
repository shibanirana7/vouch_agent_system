"""Tests for MCP handlers and synthetic data generation."""
import pytest
import tempfile
from unittest.mock import AsyncMock, patch
import backend.vouch.memory.store as store_module


@pytest.fixture(autouse=True)
def tmp_chroma(tmp_path, monkeypatch):
    monkeypatch.setattr(store_module, "_client", None)
    from backend.vouch import config
    monkeypatch.setattr(config.settings, "chroma_path", str(tmp_path / "chroma"))
    yield


@pytest.mark.asyncio
async def test_search_products_returns_results():
    from backend.vouch.mcp_server.handlers import search_products
    results = await search_products(query="matte lipstick", max_price=50.0, category="lipstick")
    assert len(results) > 0
    assert all(p["price"] <= 50.0 for p in results)


@pytest.mark.asyncio
async def test_search_products_budget_filter():
    from backend.vouch.mcp_server.handlers import search_products
    results = await search_products(query="foundation", max_price=20.0, category="general")
    assert all(p["price"] <= 20.0 for p in results)


@pytest.mark.asyncio
async def test_search_products_brand_match():
    from backend.vouch.mcp_server.handlers import search_products
    results = await search_products(query="nars", max_price=999.0, category="general")
    assert any("NARS" in p["brand"] for p in results)


def test_synthetic_history_generation(tmp_path, monkeypatch):
    monkeypatch.setattr(store_module, "_client", None)
    from backend.vouch import config
    monkeypatch.setattr(config.settings, "chroma_path", str(tmp_path / "chroma2"))
    from backend.vouch.mcp_server.handlers import generate_synthetic_history
    from backend.vouch.memory.agent_memory import AgentMemory

    generate_synthetic_history("new-agent-123", n=3)
    mem = AgentMemory("new-agent-123")
    history = mem.retrieve_relevant_history("makeup beauty product")
    assert len(history) >= 1


@pytest.mark.asyncio
async def test_update_preference():
    from backend.vouch.mcp_server.handlers import update_preference
    result = await update_preference("agent-pref-test", "Loves dewy finish skincare under $50")
    assert result["status"] == "stored"
    assert "dewy" in result["preference"]


@pytest.mark.asyncio
async def test_contribute_review():
    from backend.vouch.mcp_server.handlers import contribute_review
    result = await contribute_review(
        agent_id="agent-reviewer",
        product="Charlotte Tilbury Lip",
        category="lipstick",
        review_text="Long-lasting and hydrating",
        rating=5,
    )
    assert result["status"] == "review_stored"
