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

# Monotonic guard. Two UUIDv7 values minted inside the same millisecond must
# not merely share a timestamp — they must still be strictly increasing, or
# "time-ordered" silently degrades to "ordered per millisecond" and a burst
# inside one millisecond (the case a busy worker actually hits) sorts
# arbitrarily. The lock makes the read-modify-write of _LAST_MS/_SEQ safe across
# threads; the process-local counter makes it cheap under load.
_LOCK = threading.Lock()
_LAST_MS = 0
_SEQ = 0
_RAND_A = 0

# Width of the monotonic field. RFC 9562 section 5.7 splits the 74 random bits
# into rand_a (12) and rand_b (62). The sequence lives in rand_b, which gives
# 2^62 ids per millisecond before it could ever wrap in practice.
_SEQ_MASK = (1 << 62) - 1


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

    Layout:
        48 bit unix_ts_ms | ver(4)=0b0111 | rand_a(12) | var(2)=0b10 | seq(62)
    """
    global _LAST_MS, _SEQ, _RAND_A

    with _LOCK:
        now_ms = int(time.time() * 1000)
        if now_ms > _LAST_MS:
            # A new millisecond: reseed both random fields so ids minted in
            # different milliseconds do not form a countable run.
            _LAST_MS = now_ms
            _RAND_A = int.from_bytes(os.urandom(2), "big") & 0xFFF
            _SEQ = int.from_bytes(os.urandom(8), "big") & _SEQ_MASK
        else:
            # Same millisecond, or a clock that stepped BACKWARDS (NTP
            # correction, a container resuming from a snapshot). Either way the
            # timestamp must not go backwards, or the audit ledger's ordering
            # becomes a lie, so clamp to _LAST_MS and keep counting.
            #
            # Counting rather than merely clamping is the fix for the defect the
            # W2-1 tests found: the original guard pinned the timestamp but drew
            # fresh randomness, so two ids in one millisecond sorted
            # arbitrarily — exactly what this function promises not to do.
            _SEQ = (_SEQ + 1) & _SEQ_MASK
        ms = _LAST_MS
        rand_a = _RAND_A
        seq = _SEQ

    # BIT LAYOUT WAS WRONG — corrected here, caught by the W2-1 tests.
    #
    # The previous code did:
    #
    #     value = (ms << 80) | (0x7 << 76) | int.from_bytes(rand, "big")
    #
    # with `rand` being 10 bytes = 80 bits. But bits 76..79 are the VERSION
    # nibble and bits 74..63 are the VARIANT, so an 80-bit random draw OVERWRITES
    # both. Every id came out with `UUID.version is None` and `UUID.variant`
    # unset — not a UUIDv7 at all, and not detectable as one by anything that
    # reads the standard fields. It was still unique and still roughly ordered,
    # which is why the defect survived.
    #
    # RFC 9562 section 5.7:
    #     48 bit unix_ts_ms | ver(4)=0b0111 | rand_a(12) | var(2)=0b10 | rand_b(62)
    #
    # rand_a MUST be held constant for the whole millisecond. It sits ABOVE the
    # sequence in the value, so a fresh rand_a per call would decide the sort
    # order and make the sequence irrelevant — which is precisely the defect the
    # W2-1 monotonicity test catches, one level below the timestamp bug.
    value = (ms << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | seq
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
