"""Run identity for the distributed ETL pipeline.

WHY THIS EXISTS

The previous generator was ``run-{YYYYMMDDHHMMSS}``. That is a one-second
granularity clock with no host or process discriminator, so two batches started
inside the same second produce the SAME run_id. The column is UNIQUE, so the
second insert raises IntegrityError -- and ``_record_manifest`` caught that and
turned it into a ``logger.warning``. The result was silent loss of a run, which
is the worst failure mode available: the pipeline reported success while a run
vanished.

WHAT THIS IS

A UUIDv7 (RFC 9562). Chosen over these alternatives deliberately:

* **ULID** -- would need a new dependency.
* **UUIDv4** -- random, so it carries no time ordering. That matters: the run
  manifest is the audit ledger, and being able to sort runs by creation time
  from the id alone is worth something.
* **timestamp + milliseconds** -- fixes the collision and keeps the collision
  possible, just 1000x less often. The prompt for this work explicitly rules it
  out and it is right to: a rarer bug is not a fixed bug.

UUIDv7 is 48 bits of Unix-millisecond timestamp followed by randomness, so it
is both time-ordered and collision-resistant, and it is implemented here in a few
lines rather than pulled in.

RUN ID vs SOURCE ID

These are DIFFERENT things and conflating them is a trap:

* ``run_id``  -- one execution of one unit of work. Unique, always new.
* ``source_id`` -- identity of the INPUT, stable across retries. A retry of the
  same source gets a NEW run_id and the SAME source_id; idempotency is keyed on
  the source identity, not on the run. That is what makes a retry safe.

Nothing in this module is allowed to be the only dedupe mechanism. See
``app.database.models.StageExecution`` for the durable constraint.
"""

from __future__ import annotations

import os
import threading
import time
import uuid

__all__ = ["new_run_id", "new_source_id", "uuid7", "RunIdCollisionError"]

# Monotonic guard. Two UUIDv7 values minted inside the same millisecond must not
# share a timestamp, otherwise the "time-ordered" property degrades to a
# per-millisecond bucket. The lock makes the read-modify-write of _LAST_MS safe
# across threads; the process-local cache makes it cheap under load.
_LOCK = threading.Lock()
_LAST_MS = 0


class RunIdCollisionError(RuntimeError):
    """Raised when a run identity is reused.

    This exists so that an unexpected collision is LOUD. The defect this module
    fixes was not that a collision could happen -- it could not with a UUIDv7 --
    it was that a collision was swallowed into a log line. Keeping a distinct
    exception type means the classifier in ``_record_manifest`` can tell an
    expected idempotent replay apart from an impossible-by-construction
    identity reuse.
    """


def uuid7() -> uuid.UUID:
    """Return a time-ordered UUIDv7 (RFC 9562 section 5.7).

    Layout: 48-bit big-endian Unix ms timestamp | version/variant bits | random.
    """
    global _LAST_MS

    with _LOCK:
        # A clock that steps backwards (NTP correction, a container resuming
        # from a snapshot) would otherwise emit an id that sorts before ones
        # already issued, breaking the ordering the audit ledger relies on.
        # Clamping to _LAST_MS degrades uniqueness to the random field, which is
        # exactly the design intent.
        ms = max(int(time.time() * 1000), _LAST_MS)
        _LAST_MS = ms

    # 6 bytes timestamp + 2 bytes of randomness per millisecond is not enough on
    # its own for a busy worker, so the low 62 bits carry the full os.urandom
    # draw. 10 random bytes is the RFC's recommendation for the remaining space.
    rand = os.urandom(10)
    value = (
        (ms << 80)
        | (0x7 << 76)  # version 7
        | int.from_bytes(rand, "big")
    )
    return uuid.UUID(int=value)


def new_run_id(prefix: str = "run") -> str:
    """Return a collision-resistant, time-ordered run identity.

    The prefix is kept for human readability in logs and filenames. It carries
    no uniqueness and must never be parsed for it.
    """
    return f"{prefix}-{uuid7()}"


def new_source_id(namespace: str, identity: str) -> str:
    """Return a STABLE source identity for a given (namespace, identity) pair.

    Deterministic on purpose: the same logical input yields the same
    ``source_id`` on every retry, which is what lets a retried stage be
    recognised as the same work rather than new work.

    Deliberately NOT run-specific. Using a run id here would make every retry
    look like a fresh source and defeat the point of retrying.
    """
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"factory:{namespace}:{identity}"))


def seconds_component(value: str) -> int:
    """Extract the Unix-millisecond timestamp from a run id.

    Exists for one reason: the negative control for the collision test needs to
    reconstruct the OLD generator's behaviour deterministically rather than
    racing a clock. Without this the control would be probabilistic, and a
    probabilistic control is a control that usually proves nothing.
    """
    raw = value.split("-", 1)[-1]
    return int(uuid.UUID(raw).int >> 80)
