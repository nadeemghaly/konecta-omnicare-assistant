"""Streamlit chat UI for the OmniCare assistant.

Deliberately thin: it renders a conversation and calls the backend. All agent
logic, retrieval, and authorization live behind /api/v1/chat, so this file has no
opinions about insurance.

The policyholder switcher in the sidebar is not decoration -- switching users is
how you demonstrate that claim access is scoped, since Dana cannot see Marcus's
claim even by asking for it directly by ID.
"""

from __future__ import annotations

import os

import requests
import streamlit as st

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
REQUEST_TIMEOUT = 120  # Thinking models plus tool rounds can be slow.

# Mirrors data/mock_users.json. Kept here rather than fetched so the UI still
# renders when the backend is down.
POLICYHOLDERS = {
    "usr_123": "Dana Whitfield — POL-1092",
    "usr_456": "Marcus Adeyemi — POL-3341",
    "usr_789": "Priya Raghunathan — POL-1092, POL-3341",
}

st.set_page_config(page_title="OmniCare Assistant", page_icon="🛡️", layout="centered")


def md(text: str) -> str:
    """Escape dollar signs before rendering as markdown.

    Streamlit reads paired `$` as LaTeX math delimiters, so "$25,000 with a $500
    deductible" renders as a maths block instead of two currency amounts. Every
    coverage answer in this app contains dollar figures, so this is not cosmetic.
    """
    return str(text).replace("$", r"\$")


def backend_health() -> tuple[bool, str]:
    try:
        response = requests.get(f"{BACKEND_URL}/api/v1/health", timeout=5)
        payload = response.json()
        return payload.get("status") == "healthy", payload.get("detail") or payload.get(
            "status", "unknown"
        )
    except requests.RequestException as exc:
        return False, f"unreachable: {exc.__class__.__name__}"


with st.sidebar:
    st.subheader("Policyholder")
    user_id = st.selectbox(
        "Signed in as",
        options=list(POLICYHOLDERS),
        format_func=lambda uid: POLICYHOLDERS[uid],
    )

    healthy, detail = backend_health()
    st.caption(f"Backend: {'🟢 healthy' if healthy else f'🔴 {detail}'}")

    if st.button("Clear conversation"):
        st.session_state.pop(f"history::{user_id}", None)
        st.rerun()

    st.divider()
    st.caption(
        "Try: *Is a burst pipe covered?* · *Are gradual leaks covered?* · "
        "*What's the status of CLM-8821?* · *File a water damage claim for "
        r"\$4,200 on POL-1092*"
    )

st.title("🛡️ OmniCare Assistant")
st.caption("Policy coverage, claim status, and new claims — with sources for every answer.")

# History is per-policyholder so switching users in the sidebar does not appear to
# carry one person's conversation into another's session.
history_key = f"history::{user_id}"
history = st.session_state.setdefault(history_key, [])

for turn in history:
    with st.chat_message(turn["role"]):
        st.markdown(md(turn["content"]))
        if turn.get("sources"):
            with st.expander(f"📄 Sources ({len(turn['sources'])})"):
                for source in turn["sources"]:
                    st.markdown(f"- {md(source)}")
        if turn.get("tool_calls"):
            with st.expander(f"🔧 What I did ({len(turn['tool_calls'])})"):
                for call in turn["tool_calls"]:
                    status = "✅" if call.get("ok") else "⚠️"
                    st.markdown(f"{status} `{call['name']}`")
                    st.code(str(call.get("args")), language="python")
                    st.caption(md(str(call.get("result"))[:400]))

if prompt := st.chat_input("Ask about your policy, or a claim…"):
    history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(md(prompt))

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            try:
                response = requests.post(
                    f"{BACKEND_URL}/api/v1/chat",
                    json={"user_id": user_id, "message": prompt},
                    timeout=REQUEST_TIMEOUT,
                )
                if response.status_code == 200:
                    payload = response.json()
                elif response.status_code == 503:
                    # The Gemini free tier allows 5 requests/minute. Surfacing the
                    # raw status here would read as a broken app rather than a
                    # quota you simply have to wait out.
                    wait = response.json().get("retry_after", 60)
                    payload = {
                        "response": (
                            f"⏳ I've hit the free-tier rate limit (5 requests per "
                            f"minute). Please try again in about {wait} seconds."
                        ),
                        "sources": [],
                        "tool_calls": [],
                    }
                elif response.status_code == 404:
                    payload = {
                        "response": "That policyholder isn't on file.",
                        "sources": [],
                        "tool_calls": [],
                    }
                else:
                    payload = {
                        "response": f"The assistant returned HTTP {response.status_code}: "
                        f"{response.text[:300]}",
                        "sources": [],
                        "tool_calls": [],
                    }
            except requests.RequestException as exc:
                payload = {
                    "response": f"Could not reach the backend at {BACKEND_URL} ({exc}).",
                    "sources": [],
                    "tool_calls": [],
                }

        st.markdown(md(payload["response"]))
        if payload.get("sources"):
            with st.expander(f"📄 Sources ({len(payload['sources'])})"):
                for source in payload["sources"]:
                    st.markdown(f"- {md(source)}")
        if payload.get("tool_calls"):
            with st.expander(f"🔧 What I did ({len(payload['tool_calls'])})"):
                for call in payload["tool_calls"]:
                    status = "✅" if call.get("ok") else "⚠️"
                    st.markdown(f"{status} `{call['name']}`")
                    st.code(str(call.get("args")), language="python")
                    st.caption(md(str(call.get("result"))[:400]))

    history.append(
        {
            "role": "assistant",
            "content": payload["response"],
            "sources": payload.get("sources", []),
            "tool_calls": payload.get("tool_calls", []),
        }
    )
