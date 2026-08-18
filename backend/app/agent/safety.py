"""Prompt-injection posture.

The defence is *structural*, and the heuristic below is the least important part
of it. What actually holds the boundary:

1. Identity is a closure, not a tool argument (tools/claims.py) -- the model
   cannot name another Policyholder, so it cannot act as one.
2. Ownership is enforced inside the repository on every read and write
   (tools/repository.py) -- not by asking the prompt nicely.
3. Tool arguments are Pydantic-validated (schemas.py) -- a successful jailbreak
   still cannot file a malformed or absurdly-valued claim.
4. Retrieved document text is delimited and labelled as untrusted data, so
   instructions embedded in a policy document are content, not commands.

Consequence: injection cannot escalate privilege, because the prompt was never
what was holding the boundary. The pattern list adds cheap, visible detection of
blatant attempts -- and would be security theatre if it were relied upon alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

INJECTION_REFUSAL = (
    "I can't help with that. I can answer questions about your OmniCare policy "
    "coverage, check the status of your claims, or file a new claim."
)

# Deliberately narrow: these match explicit attempts to override instructions or
# exfiltrate the system prompt. Broad keyword matching would reject legitimate
# questions ("my instructions from the adjuster were to ignore the first letter"),
# and a false refusal is a worse product than a caught-later injection.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "override-instructions",
        re.compile(
            r"\b(ignore|disregard|forget|override)\b[^.?!]{0,40}?"
            r"\b(previous|prior|earlier|above|all|your|the)\b[^.?!]{0,20}?"
            r"\b(instruction|instructions|prompt|prompts|rule|rules|direction|directions)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "reveal-system-prompt",
        re.compile(
            r"\b(reveal|show|print|repeat|output|dump|tell me)\b[^.?!]{0,30}?"
            r"\b(system|initial|original|hidden)\b[^.?!]{0,15}?"
            r"\b(prompt|instruction|instructions|message)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "role-override",
        re.compile(
            r"\b(you are now|from now on you are|act as|pretend to be|"
            r"developer mode|jailbreak)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "cross-user-access",
        re.compile(
            r"\b(all|every|other|another|everyone'?s|someone else'?s)\b[^.?!]{0,25}?"
            r"\b(policyholder|policyholders|customer|customers|user|users|"
            r"claims of|claim records)\b",
            re.IGNORECASE,
        ),
    ),
)


@dataclass(frozen=True)
class Verdict:
    blocked: bool
    pattern: str | None = None


def screen(message: str) -> Verdict:
    """Check a user message for blatant injection attempts."""
    for name, pattern in _PATTERNS:
        if pattern.search(message):
            return Verdict(blocked=True, pattern=name)
    return Verdict(blocked=False)


def wrap_untrusted(text: str) -> str:
    """Delimit retrieved document text as data.

    Any instruction-looking text inside a policy document arrives here as
    quoted content. The system prompt tells the model that everything in this
    envelope is reference material and never a command.
    """
    fence = "<<<POLICY_EXCERPT>>>"
    # Strip any attempt by document content to close the envelope early.
    return f"{fence}\n{text.replace(fence, '')}\n{fence}"
