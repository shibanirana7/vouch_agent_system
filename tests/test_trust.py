"""Tests for the trust network layer."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.vouch.trust.graph import TrustNetwork, _weight_to_level
from backend.vouch.models.trust import TrustRelationship, TRUST_WEIGHTS


def test_trust_weights():
    assert TRUST_WEIGHTS["close_friend"] == 0.9
    assert TRUST_WEIGHTS["friend"] == 0.6
    assert TRUST_WEIGHTS["acquaintance"] == 0.3


def test_weight_to_level():
    assert _weight_to_level(0.9) == "close friend"
    assert _weight_to_level(0.6) == "friend"
    assert _weight_to_level(0.3) == "acquaintance"


@pytest.mark.asyncio
async def test_get_trusted_agents():
    mock_db = AsyncMock()
    rel1 = MagicMock(to_agent_id="agent-b", trust_weight=0.9)
    rel2 = MagicMock(to_agent_id="agent-c", trust_weight=0.6)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [rel1, rel2]
    mock_db.execute = AsyncMock(return_value=mock_result)

    network = TrustNetwork("agent-a", mock_db)
    trusted = await network.get_trusted_agents()

    assert len(trusted) == 2
    assert trusted[0] == ("agent-b", 0.9)
    assert trusted[1] == ("agent-c", 0.6)


@pytest.mark.asyncio
async def test_get_trust_summary_empty():
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=mock_result)

    network = TrustNetwork("agent-a", mock_db)
    summary = await network.get_trust_summary()
    assert "No trusted" in summary
