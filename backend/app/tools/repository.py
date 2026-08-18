"""Persistence for Claims and Policyholders.

`mock_claims.json` is a JSON array acting as a datastore, which means every write
is a read-modify-write of the whole file. There are two writers -- the agent's
`submit_claim` tool and `POST /api/v1/claims` -- so interleaved submissions would
lose records. Writes are therefore serialised by an asyncio lock and land via
atomic temp-file replace, so a crash mid-write cannot truncate the file.

What this does *not* solve: multiple processes or replicas, since an in-process
lock is invisible to them. A real deployment would use a database; this is the
honest boundary of a JSON-file store.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path

from ..config import Settings, get_settings
from ..schemas import Claim


class ClaimNotFound(Exception):
    """Raised when a claim is absent *or* not owned by the caller.

    Deliberately one exception for both cases: distinguishing them would turn the
    ownership check into an existence oracle, letting an attacker enumerate real
    claim IDs by probing. See CONTEXT.md, "Claim Ownership".
    """


class UnknownPolicy(Exception):
    """Raised when a policy number does not exist, or is not the caller's."""


class ClaimsRepository:
    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._path: Path = self._settings.claims_path
        self._lock = asyncio.Lock()

    def _read(self) -> list[Claim]:
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        return [Claim.model_validate(row) for row in raw]

    def _write(self, claims: list[Claim]) -> None:
        payload = json.dumps(
            [c.model_dump() for c in claims], indent=2, ensure_ascii=False
        )
        # Same directory as the target, so os.replace stays on one filesystem and
        # is therefore atomic.
        handle, tmp_name = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as fh:
                fh.write(payload + "\n")
            os.replace(tmp_name, self._path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    def all(self) -> list[Claim]:
        return self._read()

    def get_owned(self, claim_id: str, policy_numbers: set[str]) -> Claim:
        """Fetch a claim the caller owns, or raise ClaimNotFound.

        Ownership is checked here rather than by the caller so that no code path
        can read a claim without passing the check.
        """
        for claim in self._read():
            if claim.claim_id == claim_id and claim.policy_number in policy_numbers:
                return claim
        raise ClaimNotFound(claim_id)

    def next_claim_id(self, claims: list[Claim] | None = None) -> str:
        """Mint the next claim id as CLM-<max+1>.

        Sequential ids are guessable, which is acceptable *because* ownership is
        enforced on every read: guessing a neighbour's id grants nothing. Claim
        ids are identifiers, not secrets.
        """
        claims = claims if claims is not None else self._read()
        highest = max((int(c.claim_id.split("-")[1]) for c in claims), default=1000)
        return f"CLM-{highest + 1:04d}"

    async def append(self, policy_number: str, claim_type: str, amount: float) -> Claim:
        """Create a Submitted claim and persist it atomically."""
        async with self._lock:
            claims = self._read()
            claim = Claim(
                claim_id=self.next_claim_id(claims),
                policy_number=policy_number,
                claim_type=claim_type,
                # New claims are always Submitted. The assistant records that a
                # claim arrived; it never implies an adjudication nobody made.
                status="Submitted",
                amount=amount,
            )
            claims.append(claim)
            self._write(claims)
            return claim


class UserRepository:
    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._path: Path = self._settings.users_path

    def policies_for(self, user_id: str) -> set[str]:
        """The policy numbers a Policyholder holds. Empty set if unknown."""
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        record = raw.get(user_id)
        return set(record.get("policy_numbers", [])) if record else set()

    def name_for(self, user_id: str) -> str | None:
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        record = raw.get(user_id)
        return record.get("name") if record else None
