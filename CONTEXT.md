# Context: OmniCare Financial Customer Assistant

Glossary for the OmniCare policyholder assistant domain. Terms here are the canonical vocabulary — code, prompts, tests, and docs should all use these words with these meanings.

## Policy Document

The **global product document** describing OmniCare's insurance coverage terms — limits, deductibles, and exclusions. It is a single document that applies to all policyholders; it is *not* per-policyholder paperwork.

Consequence: coverage answers are universal. Two different policyholders asking "is a burst pipe covered?" receive the same answer. Only claims are per-policyholder data.

## Coverage Question

A question answered *from the Policy Document* rather than from claim records. "Is water damage covered?" is a Coverage Question. "What's the status of my claim?" is not.

## Policyholder

A person who holds one or more policies with OmniCare, identified by a **User ID** (`usr_###`). The Policyholder is who the assistant is talking to.

## Policy Number

The identifier of a single policy (`POL-####`). Every Policy Number belongs to exactly one Policyholder; a Policyholder may hold several.

The Policy Number — not the User ID — is what Claims are filed against. The link between the two is what makes Claim Ownership decidable.

## Claim

A policyholder's request for payment under a policy. Identified by a **Claim ID** (`CLM-####`) and bound to exactly one **Policy Number** (`POL-####`).

## Claim Ownership

A Claim belongs to the Policyholder who holds the Claim's Policy Number. Ownership is the sole basis for deciding whether the assistant may reveal or create a Claim.

Consequence: knowing a Claim ID confers no access. Ownership is checked on every read and every write, and Claim IDs are therefore not secrets.

## Conversation

A continuing exchange between one Policyholder and the assistant. Continuity is per-Policyholder: an earlier turn's subject ("my other claim") remains available to later turns in the same Conversation, and never leaks across Policyholders.

## Claim Status

The lifecycle state of a Claim. Exactly three values:

- **Submitted** — newly created through the assistant; no human has adjudicated it yet.
- **Under Review** — an adjudicator is actively assessing it.
- **Approved** — adjudicated in the policyholder's favour.

`Submitted` is distinct from `Under Review` on purpose: the assistant records that a claim *arrived*, and must never imply an assessment that no adjudicator has performed.

## Source

The provenance of a claim made in a Coverage Question answer. A Source is a **section heading paired with the verbatim sentence relied upon** — not a filename, not an opaque chunk identifier.

Consequence: a reader can verify any answer against its Source by eye, without consulting the Policy Document.

## Citation

A Source as rendered to the policyholder — the user-facing form of provenance. Every factual assertion about coverage carries one.
