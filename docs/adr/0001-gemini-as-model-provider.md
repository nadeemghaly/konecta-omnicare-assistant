# 1. Gemini as the model provider, with an OpenAI-compatible backup

Date: 2026-08-18

## Status

Accepted

## Context

The assessment requires zero cost, and names OpenAI, Anthropic, or Groq free tiers,
or a local Ollama, as the expected options.

Surveying what was actually available in the build environment:

- No OpenAI, Anthropic, or Groq API key was present.
- Ollama was not installed, and pulling a tool-calling-capable local model plus an
  embedding model would cost several GB of download and put a slow model behind an
  agent that makes multiple sequential calls per turn.
- `GEMINI_API_KEY` was present and working.

The application needs two model capabilities, not one: **generation with tool
calling**, and **embeddings** for retrieval. That second requirement narrows the
field more than it first appears — Groq, the most commonly cited free tier, serves
no embedding models at all. Using Groq would have meant pairing it with a local
`sentence-transformers` model, adding roughly 500 MB to the backend image and a
model download to first startup.

Gemini's free tier supplies both. Verified before committing to it:
`gemini-3.6-flash` round-trips multi-turn tool calls (including the thought
signatures that 3.x thinking models emit), and `gemini-embedding-001` returns
usable embeddings with configurable output dimensionality.

## Decision

Use **Gemini** as the primary provider: `gemini-3.6-flash` for generation,
`gemini-embedding-001` at 768 dimensions for embeddings.

Ship a **backup provider** behind the same seam: one OpenAI-compatible adapter,
which serves OpenAI, Groq, and Ollama alike because all three speak the Chat
Completions shape. Selecting it is a config change — `LLM_PROVIDER=openai_compat`
plus `OPENAI_BASE_URL` — with no code change.

Pin the model rather than tracking `gemini-flash-latest`, and expose `GEMINI_MODEL`
as an override.

**Embeddings do not fall back.** Even when generation switches providers, embeddings
stay on Gemini.

## Consequences

**Good.** No local model download; the backend image stays small. Both model
capabilities come from one key, so a reviewer sets up one credential. The provider
seam that enables the backup is the same seam the hermetic test suite injects a
scripted model into — one abstraction, two payoffs.

**Bad.** Gemini is not on the brief's list, so this needs explaining — hence this
record. The free tier allows only **5 requests per minute**, and a single coverage
question spends two of them; the app returns HTTP 503 with `Retry-After` rather than
failing opaquely, but rapid demoing is not possible.

**Deliberate asymmetry.** Generation falls back; embeddings do not. Two embedders
produce different dimensions and different vector spaces, so querying an index built
by one with vectors from another returns plausible-looking garbage rather than an
error — a silent correctness failure, which is worse than an outage. The embedder's
fingerprint is baked into the Chroma collection name so that changing it forces a
clean rebuild instead of quietly poisoning retrieval.

**Pinning trades one risk for another.** `gemini-2.5-flash` was observed returning
404 to new keys *during this build*, redirecting to 3.x. A pin can therefore go stale;
the `GEMINI_MODEL` override makes that a one-line fix rather than a dead demo.
