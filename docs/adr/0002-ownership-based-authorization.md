# 2. Ownership-based authorization, and the user↔policy mapping it required

Date: 2026-08-18

## Status

Accepted

## Context

The brief's chat contract carries `user_id`:

```json
{ "user_id": "usr_123", "message": "..." }
```

and then never mentions it again. Claims, meanwhile, are keyed by `policy_number`,
and the provided fixtures contain **no link between the two**.

Implemented literally, `get_claim_status(claim_id)` looks up any claim by ID for any
caller. That is an Insecure Direct Object Reference: `usr_123` reads `usr_456`'s
claim by asking for `CLM-9014`. With sequential-looking IDs, the whole claim table is
enumerable. The same gap lets any caller file a claim against a policy they don't hold.

There was a genuine tension to resolve. Enforcing ownership is impossible without
data the brief does not supply, so any fix means inventing something.

Options considered:

1. **Add a user→policy mapping** and enforce ownership in the data layer.
2. **Ask the user to state their policy number** in conversation and scope to that.
   Requires no new data, but the claim is self-asserted and trivially spoofed — it
   authenticates nothing.
3. **Leave it unscoped** and document the IDOR as a known limitation.

## Decision

Option 1. Add `data/mock_users.json` mapping each policyholder to the policies they
hold. The two provided fixtures — `sample_policy.md` and `mock_claims.json` — remain
byte-for-byte unchanged; the addition is purely additive.

Three properties make the enforcement real rather than nominal:

**Ownership lives in the repository.** `ClaimsRepository.get_owned()` takes the
caller's policy set and raises if the claim isn't in it. Neither the agent tool nor
the REST endpoint can read a claim without passing the check, because there is no
code path that skips it. A test asserts the repository refuses directly.

**The refusal is non-confirmatory.** "No such claim" and "not your claim" return
byte-identical text. Distinguishing them would turn the ownership check into an
existence oracle — an attacker learns which IDs are real by watching the error change.
A test asserts the two responses are equal, at both the tool and HTTP layers.

**Identity is a closure, not a tool parameter.** The tools are constructed per request,
closing over the caller's `user_id`. The model never sees a `user_id` argument, so a
prompt injection cannot *name* another policyholder — there is no field in which to
say who to be. A test asserts `user_id` appears in no tool's JSON schema.

A consequence worth stating: claim IDs are minted sequentially (`CLM-` + max+1) and
that is safe, because guessing an ID grants nothing when every read is
ownership-checked. Claim IDs are identifiers, not secrets. Randomising them *instead
of* scoping would be the naive trade.

## Consequences

**Good.** The most obvious security hole in the specified design is closed, with tests
that demonstrate it rather than assert it. Both API surfaces share one enforcement
point, so they cannot drift apart.

**Bad.** The system now depends on a fixture the brief didn't provide, so a reviewer
comparing against the original data will find an extra file. This record exists to
explain why.

**Unresolved.** `user_id` arrives in the request body, which means the *client asserts
its own identity* — anyone can send `usr_456` and be treated as Marcus. This is
forced: the brief's contract puts it there. In production the value would come from a
verified session token, and note that **only the input changes** — the ownership
mechanism, the repository check, the closure, and the non-confirmatory refusal all
stay exactly as they are. The `X-User-Id` header on the REST endpoints has the same
caveat and the same remedy.
