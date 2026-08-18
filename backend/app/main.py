"""FastAPI application.

Two entry points reach the same domain logic:

- `POST /api/v1/chat` -- the agent, which formats results as prose for a human.
- `GET/POST /api/v1/claims` -- thin REST handlers returning JSON.

Both go through `ClaimsRepository` and the same ownership check, so the security
boundary is shared rather than reimplemented per surface. The tools' only unique
responsibility is turning a result into a sentence.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from .agent.service import AssistantService, UnknownPolicyholder
from .config import get_settings
from .llm.errors import ProviderUnavailable, RateLimited
from .schemas import (
    ChatRequest,
    ChatResponse,
    Claim,
    HealthResponse,
    SubmitClaimInput,
    SubmitClaimResponse,
    UserId,
)
from .tools.claims import CLAIM_NOT_FOUND
from .tools.repository import ClaimNotFound

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    service = AssistantService(settings)
    # Idempotent: re-running against a populated volume skips the embedding work,
    # so a restart is instant. /health stays "degraded" until this completes,
    # which is what compose waits on.
    count = service.index.ingest()
    logger.info("policy index ready: %d chunks", count)
    app.state.service = service
    yield


app = FastAPI(
    title="OmniCare Financial Customer Assistant",
    version="1.0.0",
    description="Policy coverage RAG with citations, claim lookup, and claim submission.",
    lifespan=lifespan,
)


def get_service(request: Request) -> AssistantService:
    return request.app.state.service


@app.exception_handler(UnknownPolicyholder)
async def unknown_policyholder_handler(request: Request, exc: UnknownPolicyholder):
    return JSONResponse(status_code=404, content={"detail": "Unknown policyholder."})


@app.exception_handler(RateLimited)
async def rate_limited_handler(request: Request, exc: RateLimited):
    """The Gemini free tier caps gemini-3.6-flash at 20 generate_content requests
    per day, which a live demo will reach. 503 with Retry-After is the honest
    signal -- the request was valid -- and it keeps a quota problem out of the
    500s, where genuine faults live.

    Caveat worth knowing: the provider sends a short Retry-After even when the
    *daily* quota is the exhausted one, so the hint can be far too optimistic.
    """
    return JSONResponse(
        status_code=503,
        headers={"Retry-After": str(exc.retry_after)},
        content={
            "detail": (
                f"The model provider is rate limited. Try again in about "
                f"{exc.retry_after} seconds."
            ),
            "retry_after": exc.retry_after,
        },
    )


@app.exception_handler(ProviderUnavailable)
async def provider_unavailable_handler(request: Request, exc: ProviderUnavailable):
    return JSONResponse(
        status_code=502,
        content={"detail": "The model provider is unreachable. Please try again."},
    )


# exclude_none so a healthy response is exactly {"status": "healthy"} as the
# spec states, rather than carrying a null detail field.
@app.get("/api/v1/health", response_model=HealthResponse, response_model_exclude_none=True)
async def health(service: AssistantService = Depends(get_service)) -> HealthResponse:
    """Readiness, gated on the policy index.

    Reporting "healthy" before the index exists would let compose declare the
    stack up while every coverage question was still failing.
    """
    size = service.index.size
    if size == 0:
        return HealthResponse(status="degraded", detail="policy index is empty")
    return HealthResponse(status="healthy")


@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest, service: AssistantService = Depends(get_service)
) -> ChatResponse:
    return await service.answer(payload.user_id, payload.message)


@app.get("/api/v1/claims", response_model=list[Claim])
async def list_claims(
    x_user_id: UserId = Header(..., alias="X-User-Id"),
    service: AssistantService = Depends(get_service),
) -> list[Claim]:
    """Every claim on the caller's policies.

    Scoped by the same ownership rule as the single-claim read, so this cannot be
    used to enumerate the whole table. An unknown policyholder holds no policies
    and therefore sees an empty list rather than an error -- there is nothing to
    disclose either way.
    """
    return service.claims.for_policies(service.users.policies_for(x_user_id))


@app.get("/api/v1/claims/{claim_id}", response_model=Claim)
async def get_claim(
    claim_id: str,
    x_user_id: UserId = Header(..., alias="X-User-Id"),
    service: AssistantService = Depends(get_service),
) -> Claim:
    """Read one of the caller's claims.

    Returns 404 identically for "no such claim" and "not your claim", so the
    endpoint cannot be used to enumerate which claim IDs exist.
    """
    policies = service.users.policies_for(x_user_id)
    try:
        return service.claims.get_owned(claim_id, policies)
    except ClaimNotFound:
        raise HTTPException(status_code=404, detail=CLAIM_NOT_FOUND) from None


@app.post("/api/v1/claims", response_model=SubmitClaimResponse, status_code=201)
async def create_claim(
    payload: SubmitClaimInput,
    x_user_id: UserId = Header(..., alias="X-User-Id"),
    service: AssistantService = Depends(get_service),
) -> SubmitClaimResponse:
    """File a claim on one of the caller's policies."""
    policies = service.users.policies_for(x_user_id)
    if payload.policy_number not in policies:
        raise HTTPException(
            status_code=403, detail="That policy is not on your account."
        )
    claim = await service.claims.append(
        policy_number=payload.policy_number,
        claim_type=payload.claim_type,
        amount=float(payload.amount),
    )
    return SubmitClaimResponse(confirmation_id=claim.claim_id, status=claim.status)
