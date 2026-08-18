"""Provider error classification.

The Gemini free tier caps gemini-3.6-flash at 20 generate_content requests per
day (quotaId GenerateRequestsPerDayPerProjectPerModel-FreeTier). That is low
enough that anyone demonstrating this app will hit it, so a 429 has to be a
designed-for outcome rather than an unhandled 500. Classification is by message
content because each provider raises its own exception type -- and the point of
the provider seam is that nothing above it should have to know which vendor is
behind it.

Note on retry_after: Gemini returns a short RetryInfo delay even when the daily
quota is the exhausted one, so the value parsed below is a lower bound rather
than a promise. Callers should word it as a hint.
"""

from __future__ import annotations

import re

_RATE_LIMIT_MARKERS = (
    "429",
    "resource_exhausted",
    "rate limit",
    "ratelimit",
    "quota exceeded",
    "too many requests",
)

# Gemini reports "Please retry in 59.856841684s"; the RetryInfo block carries
# "retryDelay": "59s".
_RETRY_AFTER = re.compile(r"retry in (\d+(?:\.\d+)?)s|retryDelay['\"]?:\s*['\"](\d+)s")


class RateLimited(Exception):
    """The provider refused the request because of a quota or rate limit."""

    def __init__(self, retry_after: int = 60, provider_message: str = ""):
        self.retry_after = retry_after
        self.provider_message = provider_message
        super().__init__(f"Rate limited; retry after {retry_after}s")


class ProviderUnavailable(Exception):
    """The provider could not be reached, or refused for a non-quota reason."""


def classify(exc: Exception) -> Exception:
    """Map a provider exception onto our own vocabulary.

    Returns the exception to raise. Anything unrecognised is returned unchanged so
    genuine bugs are not silently reclassified as infrastructure problems.
    """
    text = str(exc)
    lowered = text.lower()

    if any(marker in lowered for marker in _RATE_LIMIT_MARKERS):
        match = _RETRY_AFTER.search(text)
        seconds = 60
        if match:
            raw = match.group(1) or match.group(2)
            # Round up: retrying at exactly the boundary tends to 429 again.
            seconds = max(1, int(float(raw)) + 1)
        return RateLimited(retry_after=seconds, provider_message=text[:400])

    if any(
        marker in lowered
        for marker in ("unavailable", "deadline", "timeout", "connection", "503", "500")
    ):
        return ProviderUnavailable(text[:400])

    return exc
