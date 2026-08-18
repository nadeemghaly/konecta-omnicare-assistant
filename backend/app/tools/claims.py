"""The two operational tools, bound to one Policyholder.

Identity is captured in a closure rather than exposed as a tool parameter. This
is the load-bearing security decision: if `user_id` were an argument the model
filled in, a prompt injection could simply ask for someone else's claims. The
model can only ever act as the caller, because it has no way to name anyone else.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import ValidationError

from ..schemas import SubmitClaimInput
from .repository import ClaimNotFound, ClaimsRepository, UserRepository

logger = logging.getLogger(__name__)

# One message for "no such claim" and for "not your claim". Identical text in both
# cases, so probing claim ids reveals nothing about which ones exist.
CLAIM_NOT_FOUND = "I couldn't find a claim with that ID under your policies."


def build_claim_tools(
    user_id: str,
    claims: ClaimsRepository,
    users: UserRepository,
) -> list[BaseTool]:
    """Construct the toolset for a single Policyholder."""
    policy_numbers = users.policies_for(user_id)

    def get_claim_status(claim_id: str) -> str:
        """Look up the current status of one of the caller's insurance claims.

        Args:
            claim_id: The claim identifier, formatted like CLM-8821.
        """
        try:
            claim = claims.get_owned(claim_id, policy_numbers)
        except ClaimNotFound:
            logger.info("claim lookup denied or missing: user=%s claim=%s", user_id, claim_id)
            return CLAIM_NOT_FOUND
        return (
            f"Claim {claim.claim_id} on policy {claim.policy_number}: "
            f"status={claim.status}, type={claim.claim_type}, amount=${claim.amount:,.2f}"
        )

    async def submit_claim(
        policy_number: str, claim_type: str, amount: float, description: str
    ) -> str:
        """File a new insurance claim on one of the caller's policies.

        Args:
            policy_number: The policy to claim against, formatted like POL-1092.
            claim_type: Short category, e.g. "Water Damage".
            amount: Claim amount in dollars, greater than zero.
            description: What happened.
        """
        try:
            payload = SubmitClaimInput(
                policy_number=policy_number,
                claim_type=claim_type,
                amount=Decimal(str(amount)),
                description=description,
            )
        except (ValidationError, ArithmeticError) as exc:
            # Surfaced back to the model as text so it can ask the user to
            # correct the input, rather than raising and killing the turn.
            return f"I couldn't submit that claim because the details are invalid: {exc}"

        if payload.policy_number not in policy_numbers:
            logger.info(
                "claim submission denied: user=%s policy=%s", user_id, payload.policy_number
            )
            # Same non-confirmatory posture as claim lookup: do not reveal
            # whether the policy exists, only that it isn't available here.
            return (
                f"I can't file a claim against {payload.policy_number} — "
                "it isn't one of the policies on your account."
            )

        claim = await claims.append(
            policy_number=payload.policy_number,
            claim_type=payload.claim_type,
            amount=float(payload.amount),
        )
        logger.info("claim submitted: user=%s claim=%s", user_id, claim.claim_id)
        return (
            f"Claim filed. Confirmation ID {claim.claim_id}, status {claim.status}, "
            f"policy {claim.policy_number}, amount ${claim.amount:,.2f}. "
            f"Description on file: {payload.description}"
        )

    return [
        StructuredTool.from_function(
            func=get_claim_status,
            name="get_claim_status",
            description=(
                "Look up the status of one of the current user's insurance claims by "
                "claim ID (format CLM-8821). Use this whenever the user asks about an "
                "existing claim."
            ),
        ),
        StructuredTool.from_function(
            coroutine=submit_claim,
            name="submit_claim",
            description=(
                "File a new insurance claim for the current user. Requires the policy "
                "number (format POL-1092), a claim type, an amount in dollars, and a "
                "description. Only call this once the user has supplied all four."
            ),
        ),
    ]
