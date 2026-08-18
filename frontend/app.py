"""Streamlit chat UI for the OmniCare assistant.

Deliberately thin: it renders a conversation and calls the backend. All agent
logic, retrieval, and authorization live behind /api/v1/chat, so this file has no
opinions about insurance.

Two choices worth knowing about:

- Citations render inline and expanded, not tucked inside a collapsed expander.
  Provenance is the product's whole argument; hiding it behind a click buries the
  one thing that distinguishes this from a chatbot that guesses.
- The policyholder switcher is not decoration. Switching users is how you show
  claim access is scoped -- Dana cannot see Marcus's claim even by asking for it
  by ID.

Visual direction lives in theme.py.
"""

from __future__ import annotations

import html
import os

import requests
import streamlit as st

from theme import CSS

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
REQUEST_TIMEOUT = 120  # Thinking models plus tool rounds can be slow.

# Mirrors wrap_untrusted() in backend/app/agent/safety.py. The backend fences
# retrieved policy text so the model treats it as data rather than instructions.
# That envelope is a real control, but it is plumbing -- shown here as a labelled
# block rather than as raw sentinel strings.
EXCERPT_FENCE = "<<<POLICY_EXCERPT>>>"

# Mirrors data/mock_users.json. Kept here rather than fetched so the UI still
# renders when the backend is down.
POLICYHOLDERS = {
    "usr_123": ("Dana Whitfield", ["POL-1092"]),
    "usr_456": ("Marcus Adeyemi", ["POL-3341"]),
    "usr_789": ("Priya Raghunathan", ["POL-1092", "POL-3341"]),
}

# Grouped by the three things the assistant can actually do -- a real taxonomy,
# not decorative numbering.
STARTERS = {
    "Coverage": [
        "Is a burst pipe covered, and what is the deductible?",
        "I've had a slow leak under my sink for months. Is that covered?",
        "Is a $3,000 laptop covered, and do I need an appraisal?",
    ],
    "Claims": [
        "What is the status of claim CLM-8821?",
        "A pipe burst under my kitchen sink. Please file a water damage claim "
        "on POL-1092 for $4,200.",
    ],
}

# Claim Status -> palette tone. Mirrors CONTEXT.md: Submitted is distinct from
# Under Review on purpose, so it gets its own colour rather than sharing "pending".
STATUS_TONE = {"Approved": "ok", "Under Review": "pending", "Submitted": "new"}

st.set_page_config(
    page_title="OmniCare Assistant",
    page_icon="◍",
    layout="centered",
    initial_sidebar_state="expanded",
)
st.markdown(CSS, unsafe_allow_html=True)


def md(text: str) -> str:
    """Escape dollar signs before rendering as markdown.

    Streamlit reads paired `$` as LaTeX math delimiters, so "$25,000 with a $500
    deductible" renders as a maths block instead of two currency amounts. Every
    coverage answer in this app contains dollar figures, so this is not cosmetic.
    """
    return str(text).replace("$", r"\$")


def block(text: str) -> str:
    """Escape text for injection into a custom HTML block, newlines included.

    A blank line inside inline HTML *terminates the HTML block* in markdown, so
    any text after it escapes the wrapping <div> and Streamlit wraps it in its own
    <p> instead -- which our CSS cannot reach, and which renders at the body size
    mid-block. Converting newlines to <br> keeps the whole thing one block.
    """
    return html.escape(str(text)).replace("\n", "<br>")


def backend_health() -> tuple[bool, str]:
    try:
        response = requests.get(f"{BACKEND_URL}/api/v1/health", timeout=5)
        payload = response.json()
        return payload.get("status") == "healthy", payload.get("detail") or "healthy"
    except requests.RequestException:
        return False, "unreachable"


def fetch_claims(user_id: str) -> list[dict]:
    """The caller's claims, for the sidebar. Empty on any failure -- the sidebar
    must still render when the backend is down."""
    try:
        response = requests.get(
            f"{BACKEND_URL}/api/v1/claims",
            headers={"X-User-Id": user_id},
            timeout=8,
        )
        return response.json() if response.status_code == 200 else []
    except requests.RequestException:
        return []


def money(amount: float) -> str:
    return f"${amount:,.2f}"


def detail_rows(pairs: list[tuple[str, str]]) -> str:
    return "".join(
        f'<span class="tip-row"><span class="tip-key">{html.escape(k)}</span>'
        f'<span class="tip-val">{html.escape(v)}</span></span>'
        for k, v in pairs
    )


def info(details: str) -> str:
    """An `i` affordance whose detail appears on hover or keyboard focus.

    tabindex makes it reachable without a mouse; hover alone would hide the
    detail from anyone navigating by keyboard.
    """
    return (
        f'<span class="info" tabindex="0" aria-label="Details">i'
        f'<span class="tip">{details}</span></span>'
    )


def split_source(source: str) -> tuple[str, str]:
    """Split "Section 1: … — “quoted sentence”" into its heading and its quote."""
    heading, _, quote = source.partition(" — ")
    return heading.strip(), quote.strip().strip("“”\"")


def render_citations(sources: list[str]) -> None:
    """The signature element: each source as a clause pulled from the policy.

    Serif for the quoted text, mono for the reference, a seal-coloured rule down
    the side -- so it reads as an excerpt from a document rather than as UI.
    """
    if not sources:
        return
    st.markdown(
        f'<div class="cited">Cited from the policy · {len(sources)}</div>',
        unsafe_allow_html=True,
    )
    for source in sources:
        heading, quote = split_source(source)
        st.markdown(
            f'<div class="clause">'
            f'<div class="clause-ref">{html.escape(heading)}</div>'
            f'<div class="clause-text">{html.escape(quote)}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )


def render_result(result: str) -> str:
    """Render a tool result, turning the untrusted-data fence into structure.

    The raw `<<<POLICY_EXCERPT>>>` markers are what the model actually receives,
    so the trace should still show that the text arrived quarantined -- but as a
    labelled, dashed-rule block, not as sentinel strings a reader has to decode.
    """
    if EXCERPT_FENCE in result:
        _, _, rest = result.partition(EXCERPT_FENCE)
        payload, _, trailing = rest.rpartition(EXCERPT_FENCE)
        body = (payload or trailing).strip()
        return (
            '<div class="envelope">'
            '<div class="envelope-label">Retrieved policy text · passed to the '
            "model as data, never as instructions</div>"
            f'<div class="envelope-body">{block(body)}</div>'
            "</div>"
        )
    return f'<div class="trace-out">{block(result)}</div>'


def render_trace(tool_calls: list[dict]) -> None:
    """Diagnostic, so it stays collapsed and quiet."""
    if not tool_calls:
        return
    names = ", ".join(call["name"] for call in tool_calls)
    with st.expander(f"Trace · {names}"):
        for call in tool_calls:
            mark = "→" if call.get("ok") else "×"
            args = ", ".join(f"{k}={v!r}" for k, v in (call.get("args") or {}).items())
            st.markdown(
                f'<div class="trace-row">{mark} {html.escape(call["name"])}</div>'
                f'<div class="trace-args">{html.escape(args)}</div>'
                + render_result(str(call.get("result"))[:600]),
                unsafe_allow_html=True,
            )


def ask(user_id: str, message: str) -> dict:
    """One turn. Every failure becomes a rendered message, never a traceback."""
    try:
        response = requests.post(
            f"{BACKEND_URL}/api/v1/chat",
            json={"user_id": user_id, "message": message},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        return {
            "response": f"Can't reach the assistant at {BACKEND_URL}. "
            "Check that the backend container is running.",
            "sources": [],
            "tool_calls": [],
            "notice": "seal",
        }

    if response.status_code == 200:
        return response.json()

    if response.status_code == 503:
        # The Gemini free tier allows 5 requests/minute. A raw status code here
        # would read as a broken app rather than a quota to wait out.
        wait = response.json().get("retry_after", 60)
        return {
            "response": f"Free-tier rate limit reached — 5 requests per minute. "
            f"Try again in about {wait} seconds.",
            "sources": [],
            "tool_calls": [],
            "notice": "amber",
        }

    if response.status_code == 404:
        return {
            "response": "That policyholder isn't on file.",
            "sources": [],
            "tool_calls": [],
            "notice": "seal",
        }

    return {
        "response": f"The assistant returned HTTP {response.status_code}.",
        "sources": [],
        "tool_calls": [],
        "notice": "seal",
    }


# ---------------------------------------------------------------- sidebar ----

with st.sidebar:
    st.markdown(
        '<div class="wordmark"><span class="mark"></span>OmniCare</div>'
        '<div class="wordmark-sub">Policy desk</div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="eyebrow">Signed in as</div>', unsafe_allow_html=True)
    user_id = st.selectbox(
        "Signed in as",
        options=list(POLICYHOLDERS),
        format_func=lambda uid: POLICYHOLDERS[uid][0],
        label_visibility="collapsed",
    )
    name, policies = POLICYHOLDERS[user_id]
    claims = fetch_claims(user_id)

    # Policies. Each detail is derived from data we actually hold -- no invented
    # policy metadata. Coverage limits live in the shared product document
    # (CONTEXT.md: the Policy Document applies to every policyholder), so the
    # per-policy detail is about this holder's activity on it.
    st.markdown('<div class="eyebrow">Policies held</div>', unsafe_allow_html=True)
    for policy in policies:
        on_policy = [c for c in claims if c["policy_number"] == policy]
        details = detail_rows(
            [
                ("Holder", name),
                ("Claims filed", str(len(on_policy))),
                ("Total claimed", money(sum(c["amount"] for c in on_policy))),
            ]
        ) + (
            '<span class="tip-note">Coverage limits come from the shared OmniCare '
            "product document, which applies to every policyholder.</span>"
        )
        st.markdown(
            f'<div class="row">'
            f'<span class="row-id">{html.escape(policy)}</span>{info(details)}'
            f"</div>",
            unsafe_allow_html=True,
        )

    # Claims on file, scoped by the backend to policies this holder owns.
    st.markdown('<div class="eyebrow">Claims on file</div>', unsafe_allow_html=True)
    if not claims:
        st.markdown(
            '<div class="row-empty">No claims yet. Ask the assistant to file one.</div>',
            unsafe_allow_html=True,
        )
    for claim in claims:
        tone = STATUS_TONE.get(claim["status"], "pending")
        details = detail_rows(
            [
                ("Claim", claim["claim_id"]),
                ("Policy", claim["policy_number"]),
                ("Type", claim["claim_type"]),
                ("Status", claim["status"]),
                ("Amount", money(claim["amount"])),
            ]
        )
        st.markdown(
            f'<div class="row">'
            f'<span class="status-dot {tone}"></span>'
            f'<span class="row-id">{html.escape(claim["claim_id"])}</span>'
            f'<span class="row-meta">{html.escape(claim["status"])}</span>'
            f"{info(details)}"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown('<div class="eyebrow">Backend</div>', unsafe_allow_html=True)
    healthy, detail = backend_health()
    st.markdown(
        f'<span class="pill {"ok" if healthy else "down"}">'
        f'<span class="dot"></span>{html.escape(detail)}</span>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="eyebrow">Session</div>', unsafe_allow_html=True)
    if st.button("Clear conversation", use_container_width=True):
        st.session_state.pop(f"history::{user_id}", None)
        st.rerun()

# ---------------------------------------------------------------- history ----

# Per-policyholder, so switching users in the sidebar never appears to carry one
# person's conversation into another's session.
history_key = f"history::{user_id}"
history = st.session_state.setdefault(history_key, [])

if not history:
    st.markdown(
        '<div class="lede">Ask what your policy<br>actually <em>covers</em>.</div>'
        '<div class="lede-sub">Every coverage answer quotes the clause it came from, '
        "so you can check it yourself. You can also look up a claim, or file a new one.</div>",
        unsafe_allow_html=True,
    )
    for group, prompts in STARTERS.items():
        st.markdown(f'<div class="eyebrow">{group}</div>', unsafe_allow_html=True)
        for i, starter in enumerate(prompts):
            if st.button(starter, key=f"starter-{group}-{i}", use_container_width=True):
                st.session_state.pending = starter
                st.rerun()

for turn in history:
    with st.chat_message(turn["role"]):
        st.markdown(
            f'<div class="speaker {"them" if turn["role"] == "assistant" else ""}">'
            f'{"OmniCare" if turn["role"] == "assistant" else "You"}</div>',
            unsafe_allow_html=True,
        )
        if turn.get("notice"):
            st.markdown(
                f'<div class="notice {turn["notice"]}">{block(turn["content"])}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(md(turn["content"]))
        render_citations(turn.get("sources", []))
        render_trace(turn.get("tool_calls", []))

# ------------------------------------------------------------------- turn ----

# Starter buttons and the composer share one path: chat_input cannot be filled
# programmatically, so a clicked starter parks the text here for the next run.
prompt = st.chat_input("Ask about your policy, or a claim…") or st.session_state.pop(
    "pending", None
)

if prompt:
    history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown('<div class="speaker">You</div>', unsafe_allow_html=True)
        st.markdown(md(prompt))

    with st.chat_message("assistant"):
        st.markdown('<div class="speaker them">OmniCare</div>', unsafe_allow_html=True)
        with st.spinner("Reading the policy…"):
            payload = ask(user_id, prompt)

        if payload.get("notice"):
            st.markdown(
                f'<div class="notice {payload["notice"]}">'
                f'{block(payload["response"])}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(md(payload["response"]))
        render_citations(payload.get("sources", []))
        render_trace(payload.get("tool_calls", []))

    history.append(
        {
            "role": "assistant",
            "content": payload["response"],
            "sources": payload.get("sources", []),
            "tool_calls": payload.get("tool_calls", []),
            "notice": payload.get("notice"),
        }
    )
    # Re-run when the empty state has to disappear (first message), or when a claim
    # was just filed: the sidebar is rendered before this turn is processed, so a
    # new claim would otherwise not show up until the next interaction.
    filed = any(
        call.get("name") == "submit_claim" and call.get("ok")
        for call in payload.get("tool_calls", [])
    )
    if len(history) == 2 or filed:
        st.rerun()
