# OmniCare Financial — Customer Assistant

A prototype policyholder assistant: answers coverage questions from the policy
document with verifiable citations, looks up claim statuses, and files new claims.

Built with **FastAPI + LangGraph + Chroma + Gemini**, with a Streamlit chat UI.

---

## Quick start

```bash
cp .env.example .env          # then paste a free Gemini key into it
docker compose up --build
```

Open **http://localhost:8501**.

> The brief writes this as `docker-compose up`. Docker Compose v1 (the hyphenated
> binary) is no longer shipped with Docker Desktop, so the modern equivalent is
> `docker compose` — same file, same behaviour. Use `docker-compose up --build` if
> you still have v1 installed.

A free Gemini API key takes ~30 seconds at
[aistudio.google.com/apikey](https://aistudio.google.com/apikey) — no card, no
billing account.

> ### ⚠️ The free tier allows **5 requests per minute**
>
> A single coverage question spends two of them (one to choose the tool, one to
> answer). Asking questions back-to-back **will** hit the quota. The app handles
> this deliberately — HTTP 503 with `Retry-After`, and the UI says how long to
> wait — but when demoing, pause a few seconds between questions.

**No key? You can still verify the build.** The test suite is fully hermetic:

```bash
cd backend && uv sync --extra dev && uv run pytest    # 101 tests, ~1.5s, no network
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Streamlit UI  :8501                                                      │
│  message history · inline citations · tool-call trace · user switcher     │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │  HTTP  POST /api/v1/chat
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  FastAPI  :8000                                                           │
│  POST /api/v1/chat     GET /api/v1/health                                 │
│  GET  /api/v1/claims/{id}     POST /api/v1/claims      ← same domain layer │
└───────────────────────────────┬──────────────────────────────────────────┘
                                ▼
                    ┌───────────────────────┐
                    │  Injection screen     │  blatant attempts refused
                    │  (pre-model, 0 tokens)│  before any spend
                    └───────────┬───────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  LangGraph agent                                                          │
│                                                                           │
│    START ─► agent ──tool_calls?──► tools ──► agent ─► … ─► END            │
│               ▲                      │        (bounded: 4 rounds)         │
│               └──────────────────────┘                                    │
│                                                                           │
│  MemorySaver checkpointer, thread_id = user_id  (per-policyholder memory) │
└──────┬─────────────────────────┬──────────────────────┬──────────────────┘
       │                         │                      │
       ▼                         ▼                      ▼
┌──────────────┐   ┌──────────────────────┐   ┌────────────────────────┐
│ search_policy│   │ get_claim_status     │   │ submit_claim           │
│              │   │                      │   │                        │
│ Chroma       │   │  ownership-checked   │   │  Pydantic-validated    │
│ (persistent  │   │        ▼             │   │  ownership-checked     │
│  volume)     │   │  ┌───────────────────┴───┴──────────────────┐     │
│      │       │   │  │  ClaimsRepository                        │     │
│      ▼       │   └──┤  asyncio.Lock + atomic temp-file replace  │     │
│ Gemini       │      │  mock_claims.json · mock_users.json       │     │
│ embeddings   │      └───────────────────────────────────────────┘     │
└──────────────┘                                                         │
       │                                                                 │
       ▼   sources recorded at retrieval time, not self-reported ────────┘
```

**Request flow for a coverage question:** UI → `/api/v1/chat` → injection screen →
agent decides it needs policy text → `search_policy` embeds the query, Chroma
returns the nearest sentences, irrelevant neighbours are filtered out, the
surviving sentences are recorded as `sources` *and* handed to the model wrapped as
untrusted data → agent answers from that text → response carries prose, citations,
and the tool trace.

---

## Why LangGraph

The three candidates worth considering were LangChain's `AgentExecutor`, CrewAI, and
LangGraph.

- **CrewAI** is built for multi-agent collaboration. There is one agent and three
  tools here; role-playing crews would be ceremony without benefit.
- **LangChain `AgentExecutor`** would work, but the loop is opaque. The API contract
  requires returning `tool_calls`, and reconstructing those from an executor's
  callbacks is guesswork about someone else's internals.
- **LangGraph** makes the loop an explicit state machine I own. That pays off three
  times in this codebase:
  1. **`tool_calls` is observed, not reconstructed.** The tool node records every
     invocation as it executes, so the API reports what actually happened.
  2. **The loop is bounded.** `MAX_TOOL_ROUNDS = 4` — a confused model cannot spin.
  3. **Memory is one line.** `MemorySaver` with `thread_id=user_id` gives
     per-policyholder conversation continuity.

The graph is written out by hand rather than assembled with `create_agent`, which is
also now deprecated in LangGraph v1 in favour of `langchain.agents.create_agent`.

**Why Gemini**, when the brief lists OpenAI / Anthropic / Groq / Ollama: it was the
only zero-cost provider actually available in this environment, and uniquely it
supplies *both* generation and embeddings on the free tier — avoiding a ~500 MB
`sentence-transformers` download in the image. A backup **OpenAI-compatible adapter**
is wired and covers OpenAI, Groq, and Ollama alike (all three speak the same Chat
Completions shape); set `LLM_PROVIDER=openai_compat` and point `OPENAI_BASE_URL` at
your vendor. See [ADR-0001](docs/adr/0001-gemini-as-model-provider.md).

---

## Sample requests

```bash
# Health (also what compose gates the frontend on)
curl localhost:8000/api/v1/health
# {"status":"healthy"}

# Coverage question — RAG with citations
curl -X POST localhost:8000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"usr_123","message":"Is a burst pipe covered, and what is the deductible?"}'
```
```json
{
  "response": "Yes, water damage caused by a sudden pipe burst is covered up to $25,000, with a $500 deductible. Please note that gradual leaks and flood damage are strictly excluded under the policy.",
  "sources": [
    "Section 1: Home Water Damage Coverage — “Water damage caused by sudden pipe bursts is covered up to $25,000 with a $500 deductible.”",
    "Section 1: Home Water Damage Coverage — “Gradual leaks or flood damage are strictly excluded.”"
  ],
  "tool_calls": [
    {"name": "search_policy", "args": {"query": "burst pipe deductible"}, "ok": true, "result": "<<<POLICY_EXCERPT>>>…"}
  ]
}
```

```bash
# Claim status through the agent
curl -X POST localhost:8000/api/v1/chat -H 'Content-Type: application/json' \
  -d '{"user_id":"usr_123","message":"What is the status of claim CLM-8821?"}'

# File a claim through the agent
curl -X POST localhost:8000/api/v1/chat -H 'Content-Type: application/json' \
  -d '{"user_id":"usr_123","message":"File a water damage claim on POL-1092 for $4,200 — a pipe burst under the kitchen sink"}'
```

The tools are also reachable directly, over the same domain layer and the same
ownership check — no LLM, no quota:

```bash
# Read your own claim
curl -H 'X-User-Id: usr_123' localhost:8000/api/v1/claims/CLM-8821
# {"claim_id":"CLM-8821","policy_number":"POL-1092","claim_type":"Water Damage","status":"Approved","amount":3500.0}

# Someone else's claim — 404, identical to a claim that doesn't exist
curl -i -H 'X-User-Id: usr_123' localhost:8000/api/v1/claims/CLM-9014
# HTTP/1.1 404 · {"detail":"I couldn't find a claim with that ID under your policies."}

# File a claim
curl -X POST localhost:8000/api/v1/claims \
  -H 'X-User-Id: usr_123' -H 'Content-Type: application/json' \
  -d '{"policy_number":"POL-1092","claim_type":"Water Damage","amount":4200,"description":"Burst pipe"}'
# 201 · {"confirmation_id":"CLM-9204","status":"Submitted"}
```

---

## Design decisions worth calling out

### `user_id` is not decoration — claims are ownership-scoped

The brief puts `user_id` in the chat contract and never uses it, while claims are
keyed by `policy_number` with no link between the two. Left alone, `get_claim_status`
is an **IDOR**: anyone can read any claim by guessing an ID.

`data/mock_users.json` (added; the two provided fixtures are untouched) maps
policyholders to the policies they hold, and ownership is enforced **inside the
repository** — so no caller, agent or REST, can bypass it.

Two details make it real rather than nominal:

- **The refusal is non-confirmatory.** "Not found" and "not yours" return byte-identical
  text, so the check can't be used as an existence oracle to enumerate claim IDs.
  There is a test asserting the two responses are equal.
- **Identity is a closure, not a tool parameter.** The model never sees a `user_id`
  argument, so a prompt injection has no way to *name* another policyholder. A test
  asserts `user_id` is absent from every tool's JSON schema.

Claim IDs are therefore sequential (`CLM-` + max+1) and that is fine: guessing an ID
grants nothing when every read is ownership-checked. IDs are identifiers, not secrets.

### Citations that can actually be checked

A `Source` is a **section heading plus the verbatim sentence relied upon**. The
document is chunked at the sentence, carrying its parent heading as metadata, so the
citation *falls out of retrieval* rather than being the model's account of what it
used. A reviewer can verify any answer by eye.

Retrieval returns `k` nearest neighbours whether or not they're relevant, which on a
four-sentence corpus meant a burst-pipe answer citing the Personal Property clause.
A relevance filter (keep hits within `0.13` cosine distance of the best) fixes it.
**That margin is measured, not guessed** — against `gemini-embedding-001` at 768
dimensions this corpus produces:

| Query | distances (nearest → furthest) | kept |
|---|---|---|
| Is a burst pipe covered? | 0.208, 0.269, 0.366, 0.429 | both Section 1 sentences |
| Slow gradual leak? | 0.198, 0.303, 0.377, 0.417 | the exclusion only |
| Jewelry + appraisal? | 0.265, 0.270, 0.386, 0.412 | both Section 2 sentences |
| Is a $3000 laptop covered? | 0.239, 0.300, 0.326, 0.348 | both Section 2 sentences |

The first guess of `0.25` admitted the entire document on every query — the numbers
are what corrected it.

*Known limitation:* for a genuinely out-of-scope question ("earthquake damage") all
four chunks sit within 0.353–0.407 of each other, so no *relative* rule can separate
"nothing is relevant" from "everything is". The prompt handles that case by
instructing the model to say the policy doesn't address it.

### Prompt injection is stopped structurally, not by keyword matching

A denylist alone is theatre. What actually holds the boundary:

1. Identity is a closure — the model cannot act as anyone else.
2. Ownership is enforced in the repository, on every read and write.
3. Tool arguments are Pydantic-validated — a jailbreak still can't file a
   `-$5` or `$10¹²` claim.
4. Retrieved text is fenced in `<<<POLICY_EXCERPT>>>` markers and labelled as data;
   content cannot close the fence early to escape the envelope.

A narrow pattern screen runs *before* the model, so a blatant attempt costs zero
tokens. It is deliberately narrow — several tests assert that legitimate questions
containing words like "instructions", "previous", and "rules" are **not** refused,
because a false refusal is a worse product than an injection the structural defences
would have contained anyway.

### Retrieval is a tool, not an always-on step

`sources` is empty for "what's my claim status?" — attaching policy citations to a
question that never consulted the policy is noise dressed up as rigour.

### Two writers, one JSON file

`submit_claim` and `POST /api/v1/claims` both append to `mock_claims.json`, so writes
are serialised with an `asyncio.Lock` and land via atomic temp-file replace. A test
fires eight concurrent submissions and asserts none are lost. *This does not solve
multiple processes or replicas* — an in-process lock is invisible to them. That's the
honest boundary of a JSON-file datastore; a real deployment uses a database.

---

## Tests

```bash
cd backend
uv run pytest              # 101 hermetic tests, ~1.5s, no key, no network
uv run pytest -m live      # 5 integration tests against the real Gemini API
```

The default suite injects a scripted chat model through the same seam that provides
the backup provider. This is deliberate: **`gemini-3.6-flash` ignores `temperature`**,
so there is no way to make the real model deterministic, and asserting "the agent
chose this tool" against a live thinking model is inherently flaky. The scripted
model makes control flow exactly testable; the `live` suite proves the integration
really works.

Coverage: chunking · retrieval and relevance filtering · index idempotency and
fingerprinting · both tools · input validation · **authorization and the
non-confirmatory refusal** · injection screening and its false-positive cases ·
concurrent writes · rate-limit classification · every endpoint · graph control flow,
loop bounding, and conversation memory.

Live tests self-throttle at 14s intervals to stay inside the 5 RPM quota.

---

## Layout

```
├── backend/
│   ├── app/
│   │   ├── main.py              FastAPI routes and error handlers
│   │   ├── config.py            env-driven settings
│   │   ├── schemas.py           wire contracts + domain types
│   │   ├── agent/               graph, prompts, safety, service
│   │   ├── llm/                 provider seam, scripted model, error classification
│   │   ├── rag/                 chunker, embedders, Chroma store
│   │   └── tools/               claim tools, repository (lock + atomic write)
│   └── tests/                   101 hermetic + 5 live
├── frontend/app.py              Streamlit chat UI
├── data/                        sample_policy.md · mock_claims.json · mock_users.json
├── docs/adr/                    architecture decision records
├── CONTEXT.md                   domain glossary
└── docker-compose.yml
```

`CONTEXT.md` is the domain glossary — Policyholder, Claim Ownership, Source, Claim
Status — and the vocabulary in it is the vocabulary used in code, prompts, and tests.

---

## Known limitations

- **In-process conversation memory.** `MemorySaver` is per-process; horizontal scaling
  needs a shared checkpointer (LangGraph ships Postgres and Redis savers).
- **JSON-file datastore.** Safe for concurrent writes within one process only.
- **`user_id` is client-asserted**, because the brief's contract puts it in the request
  body. In production it comes from a verified token — the ownership *mechanism* is
  unchanged, only its input becomes trustworthy.
- **Out-of-scope questions still return citations** (see the retrieval note above).
- **Free-tier rate limits** (5 RPM) make rapid demoing impossible; handled gracefully,
  not eliminated.
