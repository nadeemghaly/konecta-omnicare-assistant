"""Live integration tests against the real Gemini API.

Skipped unless GEMINI_API_KEY is set, so `pytest` stays green for a reviewer with
no key. Run them with:

    uv run pytest -m live

Assertions are deliberately loose. `gemini-3.6-flash` ignores `temperature`, so
prose varies between runs; these check that the integration works and that the
answer is *grounded*, not that it is phrased a particular way.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import pytest

from app.agent.service import AssistantService
from app.config import Settings
from app.rag.store import PolicyIndex

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not os.environ.get("GEMINI_API_KEY"),
        reason="GEMINI_API_KEY not set; live tests skipped",
    ),
]

REPO_ROOT = Path(__file__).resolve().parents[2]

# The free tier allows 5 generateContent requests per minute per model, and a
# multi-turn tool call spends two of them. Pacing proactively is faster than
# reacting to a 429, whose advertised retry delay is a full minute.
THROTTLE_SECONDS = 14


@pytest.fixture(autouse=True)
def throttle():
    yield
    time.sleep(THROTTLE_SECONDS)


@pytest.fixture(scope="module")
def live_service(tmp_path_factory) -> AssistantService:
    tmp = tmp_path_factory.mktemp("live")
    data_dir = tmp / "data"
    shutil.copytree(REPO_ROOT / "data", data_dir)
    settings = Settings(
        llm_provider="gemini",
        gemini_api_key=os.environ["GEMINI_API_KEY"],
        data_dir=data_dir,
        chroma_dir=tmp / ".chroma",
    )
    index = PolicyIndex(settings)
    index.ingest()
    return AssistantService(settings, index=index)


async def test_real_embeddings_retrieve_the_right_section(live_service):
    hits = live_service.index.search("my pipe burst and flooded the kitchen")
    assert "pipe bursts" in hits[0].source.quote


async def test_real_model_answers_a_coverage_question_with_a_citation(live_service):
    result = await live_service.answer("usr_123", "Is a burst pipe covered, and what's the deductible?")
    assert "25,000" in result.response
    assert "500" in result.response
    assert result.sources, "a coverage answer must cite the policy"
    assert any("Water Damage" in source for source in result.sources)


async def test_real_model_respects_an_exclusion(live_service):
    """The groundedness test: the policy excludes gradual leaks, and the model
    must say so rather than being agreeable."""
    result = await live_service.answer(
        "usr_456", "I've had a slow leak under my sink for months. Is that covered?"
    )
    assert result.sources
    lowered = result.response.lower()
    assert any(word in lowered for word in ("not covered", "excluded", "exclusion"))


async def test_real_model_calls_the_claim_tool(live_service):
    result = await live_service.answer("usr_123", "What is the status of claim CLM-8821?")
    assert any(call.name == "get_claim_status" for call in result.tool_calls)
    assert "Approved" in result.response


async def test_real_model_cannot_reach_another_users_claim(live_service):
    """The end-to-end proof: even with the real model choosing the tool call,
    ownership stops the read."""
    result = await live_service.answer("usr_123", "What's the status of claim CLM-9014?")
    assert "Under Review" not in result.response
