# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A prototype policyholder assistant for "OmniCare Financial", built as a Konecta
technical assessment (the brief is `GenAI Engineer v1.0.pdf`, gitignored). It answers
policy coverage questions with citations, looks up claim statuses, and files claims.

Read `CONTEXT.md` first — it is the domain glossary, and its vocabulary (Policyholder,
Policy Number, Claim Ownership, Source, Claim Status) is the vocabulary used in code,
prompts, tests, and docs. Keep them aligned; if a term changes meaning, change it there
too. `CONTEXT.md` is a glossary only — no implementation details.

## Commands

```bash
# Full stack (needs GEMINI_API_KEY in .env)
docker compose up --build           # backend :8000, frontend :8501

# Backend dev
cd backend
uv sync --extra dev
uv run pytest                       # 96 hermetic tests, ~1.5s, no key, no network
uv run pytest -m live               # 5 real-API tests; auto-skip without a key
uv run pytest tests/test_rag.py::test_irrelevant_chunks_are_filtered_out   # single test
uv run uvicorn app.main:app --reload

# Frontend dev (expects backend on :8000)
cd frontend && streamlit run app.py
```

`uv` is the package manager; there is no `requirements.txt` for the backend. The
frontend uses plain pip because it needs only Streamlit and requests.

## Architecture

Request path: Streamlit → `POST /api/v1/chat` → injection screen → LangGraph agent →
tools (`search_policy`, `get_claim_status`, `submit_claim`) → response carrying prose,
`sources`, and `tool_calls`.

The graph (`app/agent/graph.py`) is a hand-written `StateGraph`, not `create_agent`
(which is deprecated in LangGraph v1). It is written out because the tool node records
each invocation as it executes — that is where `tool_calls` in the API response comes
from, rather than reconstructing it from message history.

Key seams:

- **`app/llm/base.py`** — one factory returns a LangChain chat model for Gemini, an
  OpenAI-compatible backup (serves OpenAI/Groq/Ollama), or a scripted fake. This single
  seam provides both the backup provider and the offline test suite.
- **`app/tools/repository.py`** — ownership is enforced here, not in the tools, so
  neither the agent nor the REST endpoints can bypass it.
- **`app/rag/store.py`** — the embedder's `fingerprint` is part of the Chroma collection
  name, so changing embedder or dimensions forces a rebuild rather than querying an
  incompatible vector space.

`AssistantService` (`app/agent/service.py`) owns what must outlive a request: the index,
repositories, chat model, and the `MemorySaver` checkpointer. The graph is rebuilt per
request because tools close over the caller's identity; **the checkpointer must not be**
— a per-request saver silently discards conversation memory.

## Things that will bite you

- **Gemini 3.x ignores `temperature`.** There is no way to make the live model
  deterministic, so never assert exact tool choice or wording against it. Use the
  scripted model in `app/llm/fake.py` for control-flow tests.
- **Gemini 3.x returns content as a list of blocks**, not a string. Always route model
  output through `message_text()` or Python reprs and thought signatures leak into the
  API response.
- **Free tier is 5 requests/minute.** A tool-using turn spends two. Live tests
  self-throttle at 14s; expect 429s when demoing. They surface as HTTP 503 with
  `Retry-After` via `app/llm/errors.py`.
- **Streamlit renders paired `$` as LaTeX.** Every currency amount must go through
  `md()` in `frontend/app.py`, or "$25,000 with a $500 deductible" renders as a maths
  block.
- **`relevance_margin` (0.10) is measured, not arbitrary.** It was tuned against real
  `gemini-embedding-001` distances; the first guess of 0.25 filtered nothing. Changing
  embedder or dimensions invalidates it — re-measure rather than adjusting by feel.
- **Identity is never a tool parameter.** Tools close over `user_id`. Adding it as an
  argument would let a prompt injection name another policyholder; a test asserts it is
  absent from every tool schema.
- **Refusals must stay non-confirmatory.** "Claim not found" and "not your claim" return
  byte-identical text so the check can't be used as an existence oracle. Tests assert
  equality — don't "improve" either message independently.

## Conventions

- New claims are always `Submitted`. Status is not caller-supplied; the assistant
  records that a claim arrived and never implies an adjudication.
- `data/sample_policy.md` and `data/mock_claims.json` are the brief's fixtures and stay
  byte-for-byte as provided. `data/mock_users.json` is an addition — see
  `docs/adr/0002-ownership-based-authorization.md`.
- Reset `data/mock_claims.json` to its two seeded records before recording a demo;
  `submit_claim` appends to it through the mounted volume.
- ADRs live in `docs/adr/`. Add one only for decisions that are hard to reverse,
  surprising without context, and the result of a real trade-off.
