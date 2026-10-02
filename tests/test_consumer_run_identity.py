"""Defects found while removing `processed_ids` as the correctness authority.

Two of these are silent-data-loss bugs that no existing test could see, because
both only misbehave under conditions the suite never produced: two batches in
the same second, and a database that refuses a write.
"""

from __future__ import annotations

import pytest

from app.etl.run_identity import new_run_id
from app.etl.servicebus_consumer import TelemetryConsumer


def test_two_batches_in_the_same_second_get_distinct_run_ids():
    """`run-{YYYYMMDDHHMMSS}` collided; two runs then shared one manifest row.

    The collision was invisible in tests because they never created two batches
    inside one second, and because _record_manifest swallowed the resulting
    IntegrityError as a warning. The second run looked successful and left no
    trace.
    """
    ids = {new_run_id() for _ in range(5000)}
    assert len(ids) == 5000


def test_consumer_batch_run_id_is_not_second_resolution():
    """A generated run_id must not encode second-resolution timestamps.

    Asserted on the value rather than on timing: a probabilistic collision test
    would pass most of the time and prove nothing when it did.

    `_record_manifest` is stubbed so this stays a pure identity test. Calling
    `process_batch` for real pulls in the SQLite manifest table, which exists in
    a developer's working copy and not in a clean CI checkout -- which is how
    this first landed as a failure about a missing table rather than about run
    identity.
    """
    consumer = TelemetryConsumer()
    consumer._record_manifest = lambda **_: None  # type: ignore[method-assign]

    result = consumer.process_batch([{"id": "m1", "Machine_ID": "M", "Date": "d", "Line": "L"}])
    run_id = result["run_id"]

    # Old format was `run-20261002120000`: 14 digits, all numeric, no hyphens.
    timestamp_part = run_id.removeprefix("run-")
    assert not timestamp_part.isdigit(), f"second-resolution run_id regressed: {run_id}"
    assert new_run_id() != run_id


def test_manifest_write_failure_is_not_swallowed():
    """A manifest that cannot be persisted must not report SUCCESS.

    The old handler caught every exception and logged a warning, so the caller
    received a SUCCESS summary for a run that was never recorded. Losing a run
    manifest quietly is worse than failing loudly: the data looks fine and the
    evidence that it ran is gone.
    """
    consumer = TelemetryConsumer()
    # Force the write to fail in a way the old blanket handler would have eaten.
    with pytest.MonkeyPatch.context() as mp:
        import app.etl.servicebus_consumer as mod

        class Boom:
            def __init__(self):
                self.added = False

            def add(self, _obj):
                raise RuntimeError("disk is on fire")

            def commit(self):
                pass

            def rollback(self):
                pass

            def close(self):
                pass

        mp.setattr(mod, "SessionLocal", lambda: Boom())
        with pytest.raises(RuntimeError, match="disk is on fire"):
            consumer._record_manifest(
                run_id="run-boom",
                started_at=None,
                completed_at=None,
                status="SUCCESS",
                rows_ingested=1,
                rows_quarantined=0,
                checksum_sha256="x",
            )
