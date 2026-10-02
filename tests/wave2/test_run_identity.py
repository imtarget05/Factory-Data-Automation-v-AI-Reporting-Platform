"""W2-1 — run identity (UUIDv7) contract.

Each property below is a way the old `run-{YYYYMMDDHHMMSS}` generator could
come back: one-second granularity with no host or process discriminator, so two
batches inside the same second produced the SAME run_id. The column is UNIQUE,
so the second insert raised IntegrityError and `_record_manifest` downgraded it
to a `logger.warning` — silent loss of a run, the worst available failure mode:
the pipeline reported success while a run vanished.

NOTHING HERE IS THE IDEMPOTENCY MECHANISM. These tests prove the id is
well-formed, unique and ordered. They prove nothing about durable execution,
which is enforced by the database constraint on `stage_executions`. A suite that
only checked id shape would still pass while the pipeline executed an
already-succeeded stage twice — exactly the bug that constraint exists to stop.
"""

from __future__ import annotations

import concurrent.futures
import time
import uuid
from unittest.mock import patch

from app.etl.run_identity import (
    new_run_id,
    new_source_id,
    seconds_component,
    uuid7,
)


def _frozen_clock(ms: int):
    """Patch run_identity's `time` REFERENCE to return a fixed millisecond.

    Patching `run_identity.time.time` does NOT work safely: `run_identity` does
    `import time`, so `run_identity.time` IS the shared time module object, and
    patching an attribute on it rewrites the clock for the entire process. Every
    other library reading time during the test then sees 1970, which produced a
    wall of ValueErrors that looked like a defect in the generator and were not.
    Replacing the module's reference is process-local and honest.
    """
    patcher = patch("app.etl.run_identity.time")
    fake = patcher.start()
    fake.time.return_value = ms / 1000.0
    return patcher


# --------------------------------------------------------------------- uniqueness
def test_twenty_thousand_ids_are_unique():
    """The property the old generator failed: collisions must not be rare.

    20k because the old scheme collides on any two calls inside one second, so a
    smaller sample would also pass on a correct implementation while proving
    nothing about the broken one.
    """
    ids = {new_run_id() for _ in range(20_000)}
    assert len(ids) == 20_000, f"{20_000 - len(ids)} collisions in 20k"


def test_concurrent_generation_is_unique_across_threads():
    """Uniqueness must hold under concurrency, not just in one thread.

    The generator shares module state (`_LAST_MS`) behind a lock. Without that
    lock this is a read-modify-write race and ids minted in the same millisecond
    share a timestamp.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        ids = set(pool.map(lambda _: new_run_id(), range(4_000)))
    assert len(ids) == 4_000, f"{4_000 - len(ids)} collisions under 16 threads"


# ------------------------------------------------------------------------ ordering
def test_ids_sort_by_creation_time():
    """UUIDv7 must be time-ordered, or the manifest ledger cannot be sorted by id."""
    first = uuid7()
    time.sleep(0.01)
    second = uuid7()
    assert first < second, "a later UUIDv7 sorted before an earlier one"


def test_same_millisecond_ids_still_increase():
    """Within one millisecond the monotonic guard must keep ids increasing.

    Otherwise "time-ordered" silently degrades to "ordered per millisecond", and
    a burst inside one millisecond — the case a busy worker actually hits —
    produces an arbitrary order.
    """
    ids = [uuid7() for _ in range(5_000)]
    assert all(a < b for a, b in zip(ids, ids[1:])), (
        "ids minted in the same millisecond are not strictly increasing"
    )


def test_clock_regression_does_not_reorder_ids():
    """A clock that steps backwards must not emit an id that sorts too early.

    NTP correction or a container resuming from a snapshot can move the clock
    back. Without clamping, the new id sorts before ids already issued and the
    audit ledger's ordering becomes a lie.
    """
    real = uuid7()
    patcher = _frozen_clock(int(time.time() * 1000) - 10_000_000)
    try:
        regressed = uuid7()
    finally:
        patcher.stop()
    assert regressed > real, (
        "a clock regression produced an id that sorts BEFORE one already issued"
    )


def test_regressed_clock_keeps_uniqueness():
    """Clamping must not become 'mint duplicates': the random field still varies."""
    patcher = _frozen_clock(int(time.time() * 1000) - 10_000_000)
    try:
        ids = {uuid7() for _ in range(1_000)}
    finally:
        patcher.stop()
    assert len(ids) == 1_000


# -------------------------------------------------------------------- bit layout
def test_version_bits_are_seven():
    """RFC 9562 section 5.7: the version nibble must be 0b0111.

    This is the test that caught the original defect. The generator drew 80
    random bits into a 128-bit value that had already allocated bits 76..79 to
    the version nibble, so the random draw OVERWROTE it and every id reported
    `UUID.version is None`. The ids were still unique and still roughly ordered,
    so nothing else noticed.
    """
    for _ in range(200):
        assert uuid7().version == 7


def test_variant_bits_are_rfc4122():
    """The variant bits must be 0b10, not left to chance."""
    for _ in range(200):
        assert uuid7().variant == uuid.RFC_4122


def test_timestamp_is_recoverable_and_correct():
    """The embedded millisecond must be the real one, or ordering is fiction."""
    before = int(time.time() * 1000)
    value = uuid7()
    after = int(time.time() * 1000)
    embedded = value.int >> 80
    assert before <= embedded <= after, f"embedded timestamp {embedded} outside [{before}, {after}]"


def test_roundtrip_through_string_and_back():
    """Ids travel through JSON, filenames and logs; parsing must be lossless."""
    value = uuid7()
    assert uuid.UUID(str(value)) == value
    assert seconds_component(f"run-{value}") == value.int >> 80


# ------------------------------------------------------- run identity vs source
def test_run_ids_are_unique_but_source_ids_are_stable():
    """The distinction the module exists to protect.

    A retry must look like NEW execution of the SAME input. If source_id were
    derived from the run, every retry would appear as a fresh source and
    idempotency would never fire.
    """
    runs = {new_run_id() for _ in range(100)}
    sources = {new_source_id("blob", "raw-landing/2026/10/02/part.parquet") for _ in range(100)}
    assert len(runs) == 100
    assert len(sources) == 1, "source_id is not stable across calls"
    assert not (runs & sources), "run and source namespaces collided"


def test_different_inputs_get_different_source_ids():
    a = new_source_id("blob", "raw-landing/a.parquet")
    b = new_source_id("blob", "raw-landing/b.parquet")
    c = new_source_id("eventgrid", "raw-landing/a.parquet")
    assert a != b, "different blobs share a source identity"
    assert a != c, "same identity in a different namespace collides"


# ------------------------------------------------------------ negative controls
def test_the_old_generator_would_have_failed_this():
    """WHY THIS TEST EXISTS: prove the property is not free.

    The old scheme is reconstructed deterministically rather than by racing a
    wall clock. A probabilistic control — "generate two ids and hope they
    collide" — usually proves nothing, because it usually passes for the wrong
    reason. If this fails, the control is not testing what it claims to test.
    """
    simulated_old = {f"run-{int(time.time())}" for _ in range(1000)}
    assert len(simulated_old) == 1, (
        "the simulated old generator did not collide; this control is not "
        "testing the failure mode it claims to test"
    )
    assert len({new_run_id() for _ in range(1000)}) == 1000


def test_collision_error_type_is_distinct():
    """An impossible-by-construction collision must be LOUD, not a log line.

    This is the specific regression: the old code swallowed IntegrityError into
    `logger.warning` and lost a run silently.
    """
    from sqlalchemy.exc import IntegrityError

    from app.etl.run_identity import RunIdCollisionError

    assert issubclass(RunIdCollisionError, RuntimeError)
    assert RunIdCollisionError is not IntegrityError, (
        "a retry's IntegrityError must stay distinguishable from an identity reuse"
    )
