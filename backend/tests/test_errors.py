"""Provider error classification.

Discovered the hard way: the Gemini free tier caps at 5 requests per minute, so
this path runs during any real demo and cannot be left as an unhandled 500.
"""

import pytest

from app.llm.errors import ProviderUnavailable, RateLimited, classify

GEMINI_429 = (
    "Error calling model 'gemini-3.6-flash' (RESOURCE_EXHAUSTED): 429 RESOURCE_EXHAUSTED. "
    "{'error': {'code': 429, 'message': 'You exceeded your current quota. "
    "Quota exceeded for metric: generativelanguage.googleapis.com/"
    "generate_content_free_tier_requests, limit: 5, model: gemini-3.6-flash "
    "Please retry in 59.856841684s.'}}"
)


def test_a_gemini_quota_error_is_a_rate_limit():
    assert isinstance(classify(RuntimeError(GEMINI_429)), RateLimited)


def test_the_providers_retry_delay_is_extracted_and_rounded_up():
    """Retrying at exactly the boundary tends to 429 again."""
    assert classify(RuntimeError(GEMINI_429)).retry_after == 60


def test_retry_delay_falls_back_to_a_sane_default():
    assert classify(RuntimeError("429 too many requests")).retry_after == 60


@pytest.mark.parametrize(
    "message",
    ["Rate limit reached for gpt-4", "RESOURCE_EXHAUSTED", "quota exceeded"],
)
def test_other_providers_rate_limits_are_recognised(message):
    """The seam exists so nothing above it knows which vendor is behind it."""
    assert isinstance(classify(RuntimeError(message)), RateLimited)


@pytest.mark.parametrize("message", ["503 Service Unavailable", "connection refused"])
def test_transport_failures_are_provider_unavailable(message):
    assert isinstance(classify(RuntimeError(message)), ProviderUnavailable)


def test_unrecognised_errors_pass_through_unchanged():
    """Genuine bugs must not be relabelled as infrastructure problems."""
    original = ValueError("something is actually broken in our code")
    assert classify(original) is original
