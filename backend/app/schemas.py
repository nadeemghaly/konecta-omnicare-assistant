"""Wire contracts and domain types.

Vocabulary here follows CONTEXT.md: Policyholder, Policy Number, Claim,
Claim Status, Source.
"""

from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints

# A Policyholder is identified by `usr_###`, a policy by `POL-####`, a claim by
# `CLM-####`. Constraining these at the edge means a malformed id is rejected
# before it can reach a tool -- part of the Q8 "structural, not prompt-based"
# defence: even a successful jailbreak cannot smuggle a bad identifier through.
UserId = Annotated[str, StringConstraints(pattern=r"^usr_\d+$")]
PolicyNumber = Annotated[str, StringConstraints(pattern=r"^POL-\d{4}$")]
ClaimId = Annotated[str, StringConstraints(pattern=r"^CLM-\d{4}$")]

ClaimStatus = Literal["Submitted", "Under Review", "Approved"]


class Claim(BaseModel):
    """A Claim as persisted in mock_claims.json."""

    claim_id: ClaimId
    policy_number: PolicyNumber
    claim_type: str
    status: ClaimStatus
    amount: float


class SubmitClaimInput(BaseModel):
    """Validated arguments for the submit_claim tool.

    `status` is deliberately absent: the caller does not get to assert an
    adjudication outcome. New claims are always Submitted.
    """

    policy_number: PolicyNumber
    claim_type: Annotated[str, StringConstraints(min_length=3, max_length=80)]
    # gt=0 with a ceiling: an unbounded float here is how a jailbreak turns into
    # a $10^12 claim. Decimal keeps currency parsing exact at the boundary.
    amount: Annotated[Decimal, Field(gt=0, le=Decimal("10000000"))]
    description: Annotated[str, StringConstraints(min_length=3, max_length=2000)]


class Source(BaseModel):
    """Provenance for a coverage assertion: a section heading plus the exact
    sentence relied upon. Falls out of retrieval rather than being self-reported
    by the model, so a reader can verify any answer by eye."""

    section: str
    quote: str

    def render(self) -> str:
        return f"{self.section} — “{self.quote}”"


class ToolCallRecord(BaseModel):
    """What the agent actually did, surfaced through the API so the caller can
    audit the run rather than trusting the prose."""

    name: str
    args: dict[str, Any]
    ok: bool
    result: str


class ChatRequest(BaseModel):
    # Note: `user_id` is client-asserted, because the assessment's contract puts
    # it in the request body. In production this would come from a verified
    # token -- see docs/adr/0002-ownership-based-authorization.md.
    user_id: UserId
    message: Annotated[str, StringConstraints(min_length=1, max_length=4000)]


class ChatResponse(BaseModel):
    response: str
    sources: list[str] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded"]
    detail: str | None = None


class SubmitClaimResponse(BaseModel):
    confirmation_id: ClaimId
    status: ClaimStatus
