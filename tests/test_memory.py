"""Tests for the ChromaDB memory layer."""
import pytest
import tempfile
import os
from backend.vouch.memory.agent_memory import AgentMemory
from backend.vouch.memory.shared_memory import SharedMemory
import backend.vouch.memory.store as store_module


@pytest.fixture(autouse=True)
def tmp_chroma(tmp_path, monkeypatch):
    """Use a fresh temp dir for ChromaDB in each test."""
    monkeypatch.setattr(store_module, "_client", None)
    from backend.vouch import config
    monkeypatch.setattr(config.settings, "chroma_path", str(tmp_path / "chroma"))
    yield


def test_store_and_retrieve_preference():
    mem = AgentMemory("test-agent-1")
    mem.store_preference("Loves matte lipsticks under $30")
    mem.store_preference("Avoids fragrance in skincare")
    results = mem.retrieve_preferences("matte lipstick budget")
    assert len(results) > 0
    assert any("matte" in r.lower() for r in results)


def test_build_preference_context_empty():
    mem = AgentMemory("test-agent-empty")
    ctx = mem.build_preference_context()
    assert "No preferences" in ctx


def test_store_and_retrieve_purchase_history():
    mem = AgentMemory("test-agent-2")
    mem.store_purchase("Fenty Foundation", 38.0, "foundation", satisfaction=5)
    history = mem.retrieve_relevant_history("foundation full coverage")
    assert len(history) > 0
    assert any("Fenty" in h["text"] for h in history)


def test_shared_memory_contribute_and_query():
    shared = SharedMemory()
    shared.contribute_review(
        agent_id="agent-a",
        product="Rare Beauty Blush",
        category="blush",
        review_text="Perfect for daily wear, very pigmented",
        rating=5,
    )
    results = shared.query_reviews(
        query="blush pigmented",
        category="blush",
        trusted_agent_ids=["agent-a"],
    )
    assert len(results) > 0
    assert results[0]["agent_id"] == "agent-a"


def test_shared_memory_filters_untrusted():
    shared = SharedMemory()
    shared.contribute_review(
        agent_id="untrusted-agent",
        product="Some Mascara",
        category="mascara",
        review_text="Great lengthening effect",
        rating=4,
    )
    results = shared.query_reviews(
        query="mascara lengthening",
        category="mascara",
        trusted_agent_ids=["trusted-agent-only"],
    )
    assert len(results) == 0
