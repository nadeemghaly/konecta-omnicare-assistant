"""Claim access is scoped to the caller.

The assessment brief passes `user_id` into /chat and never says what to do with
it, while claims are keyed by policy number. Left unused, `get_claim_status`
becomes an IDOR: any user can read any claim by guessing its ID. These tests are
the proof that it does not.
"""

import json

import pytest

from app.config import Settings
from app.tools.claims import CLAIM_NOT_FOUND, build_claim_tools
from app.tools.repository import ClaimNotFound, ClaimsRepository, UserRepository


def tools_for(user_id: str, settings: Settings):
    return {
        tool.name: tool
        for tool in build_claim_tools(
            user_id, ClaimsRepository(settings), UserRepository(settings)
        )
    }


async def test_a_user_cannot_read_another_users_claim(settings: Settings):
    """usr_123 holds POL-1092; CLM-9014 belongs to POL-3341."""
    dana = tools_for("usr_123", settings)
    assert await dana["get_claim_status"].ainvoke({"claim_id": "CLM-9014"}) == CLAIM_NOT_FOUND


async def test_the_owner_can_read_the_same_claim(settings: Settings):
    """The refusal above must be about ownership, not a broken lookup."""
    marcus = tools_for("usr_456", settings)
    assert "Under Review" in await marcus["get_claim_status"].ainvoke({"claim_id": "CLM-9014"})


async def test_denied_and_missing_are_indistinguishable(settings: Settings):
    """If "not yours" read differently from "does not exist", the ownership check
    would double as an existence oracle for enumerating real claim IDs."""
    dana = tools_for("usr_123", settings)
    denied = await dana["get_claim_status"].ainvoke({"claim_id": "CLM-9014"})
    missing = await dana["get_claim_status"].ainvoke({"claim_id": "CLM-0002"})
    assert denied == missing


async def test_a_user_cannot_file_a_claim_on_a_policy_they_do_not_hold(
    settings: Settings,
):
    dana = tools_for("usr_123", settings)
    before = len(json.loads(settings.claims_path.read_text()))
    result = await dana["submit_claim"].ainvoke(
        {
            "policy_number": "POL-3341",
            "claim_type": "Personal Property",
            "amount": 500.0,
            "description": "Not my policy",
        }
    )
    assert "isn't one of the policies" in result
    # And nothing was written.
    assert len(json.loads(settings.claims_path.read_text())) == before


async def test_a_multi_policy_holder_reaches_all_their_claims(settings: Settings):
    """usr_789 holds both policies, so both claims are legitimately visible."""
    priya = tools_for("usr_789", settings)
    assert "Approved" in await priya["get_claim_status"].ainvoke({"claim_id": "CLM-8821"})
    assert "Under Review" in await priya["get_claim_status"].ainvoke({"claim_id": "CLM-9014"})


async def test_an_unknown_user_can_read_nothing(settings: Settings):
    nobody = tools_for("usr_999", settings)
    assert await nobody["get_claim_status"].ainvoke({"claim_id": "CLM-8821"}) == CLAIM_NOT_FOUND


def test_the_repository_refuses_unowned_reads_directly(settings: Settings):
    """Ownership lives in the repository, not in the tool wrapper, so no future
    caller can bypass it by going one layer down."""
    with pytest.raises(ClaimNotFound):
        ClaimsRepository(settings).get_owned("CLM-9014", {"POL-1092"})


def test_identity_is_not_a_tool_parameter(settings: Settings):
    """The decisive control: if the model could pass user_id, a prompt injection
    could simply ask for someone else's claims. It cannot name anyone."""
    for tool in build_claim_tools(
        "usr_123", ClaimsRepository(settings), UserRepository(settings)
    ):
        schema = tool.args_schema.model_json_schema()
        assert "user_id" not in schema.get("properties", {})


def test_listing_claims_never_widens_the_policy_set(settings: Settings):
    """The repository filters on the caller's policies and nothing else.

    Asserted as an invariant over whatever the fixture holds, rather than against a
    fixed claim list: the guarantee is "never widens", and that must survive the
    mock data growing.
    """
    repo = ClaimsRepository(settings)
    every_policy = {c.policy_number for c in repo.all()}

    for held in ({"POL-1092"}, {"POL-1092", "POL-3341"}, every_policy):
        returned = repo.for_policies(held)
        assert returned, f"fixture should hold claims on {held}"
        assert {c.policy_number for c in returned} <= held

    assert [c.claim_id for c in repo.for_policies(set())] == []

    # Claims outside the requested set are genuinely withheld, not merely reordered.
    one_policy = {c.claim_id for c in repo.for_policies({"POL-1092"})}
    assert one_policy < {c.claim_id for c in repo.all()}
