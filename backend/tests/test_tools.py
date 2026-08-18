"""Tool behaviour: lookup, submission, validation, and persistence."""

import asyncio
import json

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.schemas import SubmitClaimInput
from app.tools.claims import CLAIM_NOT_FOUND, build_claim_tools
from app.tools.repository import ClaimsRepository, UserRepository


@pytest.fixture
def tools(settings: Settings):
    return {
        tool.name: tool
        for tool in build_claim_tools(
            "usr_123", ClaimsRepository(settings), UserRepository(settings)
        )
    }


async def test_get_claim_status_returns_an_owned_claim(tools):
    result = await tools["get_claim_status"].ainvoke({"claim_id": "CLM-8821"})
    assert "Approved" in result
    assert "POL-1092" in result
    assert "$3,500.00" in result


async def test_submit_claim_persists_and_returns_a_confirmation_id(
    tools, settings: Settings
):
    result = await tools["submit_claim"].ainvoke(
        {
            "policy_number": "POL-1092",
            "claim_type": "Water Damage",
            "amount": 4200.0,
            "description": "Burst pipe under the kitchen sink",
        }
    )
    assert "CLM-9015" in result
    assert "Submitted" in result

    stored = json.loads(settings.claims_path.read_text())[-1]
    assert stored["claim_id"] == "CLM-9015"
    assert stored["status"] == "Submitted"
    assert stored["amount"] == 4200.0


async def test_a_submitted_claim_is_immediately_retrievable(tools):
    """The confirmation ID must be usable straight away, or the two tools disagree
    about what exists."""
    await tools["submit_claim"].ainvoke(
        {
            "policy_number": "POL-1092",
            "claim_type": "Water Damage",
            "amount": 900.0,
            "description": "Leak",
        }
    )
    assert "Submitted" in await tools["get_claim_status"].ainvoke({"claim_id": "CLM-9015"})


async def test_new_claims_are_never_created_pre_adjudicated(tools, settings: Settings):
    """Status is not a caller-supplied field: the assistant records arrival, it
    does not assert an outcome no adjudicator reached."""
    await tools["submit_claim"].ainvoke(
        {
            "policy_number": "POL-1092",
            "claim_type": "Water Damage",
            "amount": 100.0,
            "description": "Minor",
        }
    )
    assert json.loads(settings.claims_path.read_text())[-1]["status"] == "Submitted"


@pytest.mark.parametrize(
    "amount",
    [0, -1, -0.01, 10_000_001],
    ids=["zero", "negative", "tiny-negative", "over-ceiling"],
)
def test_amount_is_bounded(amount):
    """An unbounded float is how a jailbreak becomes a trillion-dollar claim."""
    with pytest.raises(ValidationError):
        SubmitClaimInput(
            policy_number="POL-1092",
            claim_type="Water Damage",
            amount=amount,
            description="test",
        )


@pytest.mark.parametrize("policy", ["POL-92", "1092", "pol-1092", "POL-10920", ""])
def test_malformed_policy_numbers_are_rejected(policy):
    with pytest.raises(ValidationError):
        SubmitClaimInput(
            policy_number=policy,
            claim_type="Water Damage",
            amount=100,
            description="test",
        )


async def test_invalid_input_is_reported_back_rather_than_raising(tools):
    """The model must be able to recover by asking the user, so a validation
    failure returns text instead of killing the turn."""
    result = await tools["submit_claim"].ainvoke(
        {
            "policy_number": "POL-1092",
            "claim_type": "Water Damage",
            "amount": -5.0,
            "description": "Negative",
        }
    )
    assert "invalid" in result.lower()


async def test_unknown_claim_returns_the_uniform_message(tools):
    assert await tools["get_claim_status"].ainvoke({"claim_id": "CLM-0001"}) == CLAIM_NOT_FOUND


def test_claim_ids_increment_from_the_highest_existing(settings: Settings):
    repo = ClaimsRepository(settings)
    assert repo.next_claim_id() == "CLM-9015"


async def test_concurrent_submissions_do_not_lose_claims(settings: Settings):
    """Two writers exist (the agent tool and POST /api/v1/claims). A naive
    read-modify-write on a JSON array drops records when they interleave."""
    repo = ClaimsRepository(settings)
    await asyncio.gather(
        *(
            repo.append(policy_number="POL-1092", claim_type="Water Damage", amount=100.0 + i)
            for i in range(8)
        )
    )
    stored = json.loads(settings.claims_path.read_text())
    assert len(stored) == 10  # 2 seeded + 8 appended
    assert len({row["claim_id"] for row in stored}) == 10
