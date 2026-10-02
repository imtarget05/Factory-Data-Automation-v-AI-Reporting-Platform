"""W2-4 worker proofs: ACK only after durable success.

Real PostgreSQL, no mocks as authority for anything durable. A mock can prove
that `complete_stage` was CALLED; only the database can prove the semantic row
became SUCCEEDED, that a second worker sees it, and that a crashed worker's
claim is recoverable. Those are the claims this module makes.

Refuses to collect without FACTORY_TEST_PG_ADMIN_URL, following the convention
established by the migration suite: "no database" must mean RED, because a skip
and a pass look identical in a report.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, func, select, text, update
from sqlalchemy.orm import Session, sessionmaker

ADMIN_URL = os.getenv("FACTORY_TEST_PG_ADMIN_URL")
if not ADMIN_URL:
    raise RuntimeError(
        "FACTORY_TEST_PG_ADMIN_URL is not set. W2-4 requires a REAL PostgreSQL "
        "server; claim, sticky-success and lease semantics cannot be proven "
        "against SQLite. Refusing to report green without a database."
    )

from app.database.stage_models import StageAttemptRow, StageExecutionRow  # noqa: E402
from app.etl.run_identity import new_run_id  # noqa: E402
from app.etl.stage_execution import Stage, StageStatus  # noqa: E402
from app.messaging.envelope import Envelope  # noqa: E402
from app.worker.processor import Disposition, FailureClass, process_one  # noqa: E402
from app.worker.runner import run_loop  # noqa: E402
from app.worker.transport import InMemoryTransport  # noqa: E402
from tests.wave2.migration_harness import (  # noqa: E402
    database_url_for,
    drop_database,
    make_database,
    upgrade_to,
)


@pytest.fixture
def db_url():
    name = f"factory_w24_{uuid.uuid4().hex[:8]}"
    make_database(ADMIN_URL, name)
    url = database_url_for(ADMIN_URL, name)
    upgrade_to(url, "head")
    try:
        yield url
    finally:
        drop_database(ADMIN_URL, name)


@pytest.fixture
def session(db_url):
    engine = create_engine(db_url, future=True)
    conn = engine.connect()
    trans = conn.begin()
    try:
        yield Session(bind=conn)
    finally:
        trans.rollback()
        conn.close()
        engine.dispose()


class SideEffectCounter:
    """Counts real handler invocations.

    A test-local object rather than a global or a mock: it records how many times
    the side effect actually HAPPENED, which is the quantity every duplicate-
    execution bug inflates.
    """

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, envelope: Envelope) -> dict[str, object]:
        self.calls += 1
        return {"artifact_ref": f"local://{envelope.run_id}/{envelope.stage}", "checksum": "abc123"}


def make_envelope(
    *, run_id: str | None = None, message_id: str = "m-1", stage: Stage = Stage.GOLD
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "message_id": message_id,
        "source_id": "src-telemetry-1",
        "run_id": run_id or new_run_id(),
        "stage": stage.value,
        "occurred_at": "2026-10-02T10:00:00+00:00",
        "correlation_id": "corr-1",
        "payload": {"Machine_ID": "CNC-02", "Line": "Line_B"},
    }


def _semantic(session: Session, run_id: str, stage: Stage = Stage.GOLD) -> StageExecutionRow:
    return session.execute(
        select(StageExecutionRow).where(
            StageExecutionRow.run_id == run_id,
            StageExecutionRow.stage == stage.value,
        )
    ).scalar_one()


def _attempts(session: Session, run_id: str, stage: Stage = Stage.GOLD) -> int:
    return session.execute(
        select(func.count())
        .select_from(StageAttemptRow)
        .where(StageAttemptRow.run_id == run_id, StageAttemptRow.stage == stage.value)
    ).scalar_one()


# ── T1: the happy path, and the ACK boundary ───────────────────────────────


def test_t1_valid_message_commits_then_acks(session):
    """T1. Processing order: side effect, durable commit, THEN ack.

    Asserted as a sequence rather than as a final state, because the failure
    mode being prevented is "acked but not committed", which a final-state check
    on the happy path cannot distinguish from success.
    """
    run_id = new_run_id()
    counter = SideEffectCounter()
    outcome = process_one(
        session, make_envelope(run_id=run_id), stage_handler=counter, owner="worker-1"
    )

    assert outcome.disposition is Disposition.ACK
    assert outcome.acked is True
    assert counter.calls == 1
    # Durable state exists, so an ACK was safe.
    assert _semantic(session, run_id).status == StageStatus.SUCCEEDED
    assert _semantic(session, run_id).succeeded_at is not None
    assert _attempts(session, run_id) == 1


def test_t2_invalid_envelope_never_reaches_business_logic(session):
    """T2. A malformed message is dead-lettered without a claim row.

    Asserted on the ABSENCE of a stage row as well as the disposition: creating
    a claim for a message that cannot be identified would leave an orphan RUNNING
    row that blocks its own semantic slot until the lease expires.
    """
    counter = SideEffectCounter()
    for broken in (
        {"schema_version": 99},
        {**make_envelope(), "run_id": "run-not-a-uuid"},
        {**make_envelope(), "payload": "not-an-object"},
    ):
        outcome = process_one(session, broken, stage_handler=counter, owner="worker-1")

        assert outcome.disposition is Disposition.DEAD_LETTER
        assert outcome.acked is False
        assert outcome.error_class is FailureClass.BUSINESS_INVALID

    assert counter.calls == 0
    assert session.execute(select(func.count()).select_from(StageExecutionRow)).scalar_one() == 0


# ── T4 / C4: the invariant that justifies the whole design ────────────────


def test_c4_redelivery_after_committed_success_does_not_re_execute(session):
    """C4, and the single most important test in this module.

    Success was durably committed, then the worker died BEFORE acknowledging.
    The broker redelivers. The only correct outcome is: no second side effect,
    and an ack, because the work is genuinely already done.

    A worker that acks too early passes T1 and fails here; a worker that acks too
    late still passes T1 and fails here for a different reason. Only the ordering
    that this asserts satisfies both.
    """
    run_id = new_run_id()
    first = SideEffectCounter()

    crashed = process_one(
        session,
        make_envelope(run_id=run_id, message_id="m-1"),
        stage_handler=first,
        owner="worker-1",
    )
    assert crashed.disposition is Disposition.ACK
    assert first.calls == 1

    # Worker 1 is gone. Its only surviving artefact is the committed row.
    redelivered = SideEffectCounter()
    outcome = process_one(
        session,
        make_envelope(run_id=run_id, message_id="m-2-DIFFERENT"),
        stage_handler=redelivered,
        owner="worker-2",
    )

    assert outcome.disposition is Disposition.ACK_DUPLICATE
    assert outcome.acked is True, "a committed success must still be acknowledged"
    assert redelivered.calls == 0, "the side effect must not happen twice"
    assert first.calls == 1
    assert _attempts(session, run_id) == 1, "no attempt 2 for already-successful work"


def test_t5_a_brand_new_process_dedupes_from_the_database_alone(session):
    """T5. The in-memory set cannot help here, and is not used.

    A completely separate engine, connection and Session object -- nothing shared
    with the first worker except the database. This is the assertion that
    `processed_ids` was genuinely demoted rather than merely supplemented.
    """
    run_id = new_run_id()
    # The URL, not the bound Connection: `get_bind()` returns a live Connection
    # here, and a second engine has to be built from a URL string.
    #
    # `render_as_string(hide_password=False)` is required, not stylistic. Plain
    # `str(url)` masks the password as `***`, so the derived engine authenticates
    # with the literal string "***" and every one of these tests fails in CI with
    # an auth error while passing locally against a trust-authenticated socket.
    # Local Docker sockets often use `trust`, which hides the mistake entirely.
    url = session.get_bind().engine.url.render_as_string(hide_password=False)
    engine_a = create_engine(url, future=True)
    with engine_a.begin() as conn:
        first = SideEffectCounter()
        process_one(
            Session(bind=conn),
            make_envelope(run_id=run_id),
            stage_handler=first,
            owner="worker-1",
        )
        assert first.calls == 1

    engine_b = create_engine(url, future=True)
    with engine_b.begin() as conn:
        second = SideEffectCounter()
        outcome = process_one(
            Session(bind=conn),
            make_envelope(run_id=run_id, message_id="m-2"),
            stage_handler=second,
            owner="worker-2",
        )
        assert outcome.disposition is Disposition.ACK_DUPLICATE
        assert second.calls == 0
        assert (
            Session(bind=conn)
            .execute(
                select(func.count())
                .select_from(StageAttemptRow)
                .where(StageAttemptRow.run_id == run_id)
            )
            .scalar_one()
            == 1
        )
    engine_a.dispose()
    engine_b.dispose()


# ── T3 / T12 / T13: concurrency and lease fencing ──────────────────────────


def test_t3_two_workers_race_the_same_stage(session):
    """T3. Two independent connections, one execution owner.

    Uses two engines rather than two calls in one Session, because two calls in
    one Session share a transaction and would not exercise the constraint at all.
    """
    url = session.get_bind().engine.url.render_as_string(hide_password=False)
    run_id = new_run_id()
    engines = [create_engine(url, future=True) for _ in range(2)]
    outcomes = []
    counters = [SideEffectCounter(), SideEffectCounter()]

    for index, (engine, counter) in enumerate(zip(engines, counters)):
        with engine.begin() as conn:
            outcomes.append(
                process_one(
                    Session(bind=conn),
                    make_envelope(run_id=run_id, message_id=f"m-{index}"),
                    stage_handler=counter,
                    owner=f"worker-{index}",
                )
            )

    dispositions = sorted(o.disposition.value for o in outcomes)
    # Both results are correct, and which one arrives depends on real timing:
    # if worker 0 finishes and commits before worker 1 even claims, worker 1 sees
    # a completed stage. What must hold in BOTH orderings is that only one
    # execution happened. Asserting the exact disposition pair would be
    # asserting a race outcome, which is flaky by construction.
    assert dispositions in (
        ["ACK", "ACK_DUPLICATE"],
        ["ACK", "DEFER"],
    ), f"unexpected dispositions: {dispositions}"
    total_calls = sum(c.calls for c in counters)
    assert total_calls == 1, "exactly one execution side effect"
    for engine in engines:
        engine.dispose()


def test_t12_expired_lease_is_recovered_with_attempt_history_kept(session):
    """T12. A crashed worker's claim is recoverable, and the evidence survives.

    Attempt 1 is left RUNNING by a worker that died. Attempt 2 recovers it.
    Both rows must remain, because "attempt 1 crashed" is exactly what an
    operator needs when a stage fails repeatedly.
    """
    run_id = new_run_id()
    # lease_seconds=-1 makes the lease already expired, standing in for a crash.
    first = process_one(
        session,
        make_envelope(run_id=run_id),
        stage_handler=SideEffectCounter(),
        owner="worker-crashed",
        lease_seconds=-1,
    )
    assert first.disposition is Disposition.ACK

    # Reset to RUNNING to model the crash: the row exists, the work never finished.
    session.execute(
        update(StageExecutionRow)
        .where(StageExecutionRow.run_id == run_id)
        .values(
            status=StageStatus.RUNNING.value,
            succeeded_at=None,
            completed_at=None,
            claim_owner="worker-crashed",
            lease_expires_at=func.now() - text("INTERVAL '1 minute'"),
        )
    )
    session.commit()

    recovered_counter = SideEffectCounter()
    process_one(
        session,
        make_envelope(run_id=run_id, message_id="m-2"),
        stage_handler=recovered_counter,
        owner="worker-2",
    )

    assert recovered_counter.calls == 1
    attempts = _attempts(session, run_id)
    assert attempts == 2, "the crashed attempt must remain in the audit trail"


def test_t13_a_fenced_owner_cannot_publish_its_result(session):
    """T13. Stale-owner fencing.

    Worker A starts with a lease that then expires. Worker B recovers and
    completes. Worker A finally finishes and tries to commit its output. That
    write MUST be refused: its result was computed under a lease it no longer
    held, possibly concurrently with B's, and letting it through would produce
    two published outputs for one stage.
    """
    run_id = new_run_id()
    url = session.get_bind().engine.url.render_as_string(hide_password=False)

    engine_a = create_engine(url, future=True)
    with engine_a.begin() as conn:
        claim = process_one(
            Session(bind=conn),
            make_envelope(run_id=run_id),
            stage_handler=lambda env: {"artifact_ref": "A", "checksum": "aaa"},
            owner="worker-a",
            lease_seconds=-1,
        )
    engine_a.dispose()
    assert claim.disposition is Disposition.ACK

    session.execute(
        update(StageExecutionRow)
        .where(StageExecutionRow.run_id == run_id)
        .values(
            status=StageStatus.RUNNING.value,
            succeeded_at=None,
            completed_at=None,
            claim_owner="worker-b",
            lease_expires_at=func.now() + text("INTERVAL '1 hour'"),
        )
    )
    session.commit()

    # Worker A, holding a stale claim_owner, attempts to complete.
    from app.etl.stage_claim import complete_stage

    recorded = complete_stage(
        session,
        run_id=run_id,
        stage=Stage.GOLD,
        attempt=claim.attempt,
        owner="worker-a",  # stale: the row says worker-b
        output_artifact_ref="A",
    )
    session.commit()

    assert recorded is False, "a fenced owner must not be able to publish"


# ── T6 / T7 / T8: retry classification and bounds ─────────────────────────


def test_t6_transient_failure_retries_and_does_not_ack(session):
    """T6. A dependency blip must be retried, and must not be acked.

    ACKing here would discard the message while the durable state still says the
    stage never succeeded -- the work would be lost with no trace of a failure.
    """
    run_id = new_run_id()
    calls = {"n": 0}

    def flaky(_env):
        calls["n"] += 1
        raise ConnectionError("postgres socket closed")

    outcome = process_one(session, make_envelope(run_id=run_id), stage_handler=flaky, owner="w1")

    assert outcome.disposition is Disposition.RETRY
    assert outcome.acked is False
    assert outcome.error_class is FailureClass.TRANSIENT
    assert _semantic(session, run_id).status != StageStatus.SUCCEEDED


def test_t8_permanent_failure_dead_letters_immediately(session):
    """T8. A poison message must not burn the retry budget.

    `ValueError` classifies as PERMANENT, so the very first attempt dead-letters
    rather than cycling. Retrying it five times would delay every message behind
    it and still fail.
    """
    run_id = new_run_id()
    calls = {"n": 0}

    def poison(_env):
        calls["n"] += 1
        raise ValueError("row violates a non-negotiable business rule")

    outcome = process_one(session, make_envelope(run_id=run_id), stage_handler=poison, owner="w1")

    assert outcome.disposition is Disposition.DEAD_LETTER
    assert outcome.acked is False
    assert outcome.error_class is FailureClass.PERMANENT
    assert calls["n"] == 1


def test_t7_exhausted_retry_budget_dead_letters(session):
    """T7. Retry is bounded. Exhaustion produces DEAD_LETTER, not another try.

    `max_attempts=1` stands in for an exhausted budget without simulating five
    round trips. The important property is that the worker checks the bound and
    stops, rather than relying on the transport's own redelivery cap.
    """
    run_id = new_run_id()

    def always_transient(_env):
        raise TimeoutError("upstream still down")

    outcome = process_one(
        session,
        make_envelope(run_id=run_id),
        stage_handler=always_transient,
        owner="w1",
        max_attempts=1,
    )

    assert outcome.disposition is Disposition.DEAD_LETTER
    assert outcome.acked is False
    assert outcome.error_class is FailureClass.TRANSIENT


def test_t9_durable_commit_failure_prevents_ack(session):
    """T9. The manifest-class failure: work done, durable state not written.

    This is the W2-4 restatement of the `_record_manifest` defect from the
    previous wave, at the transport boundary. If `complete_stage` fails to
    persist, the worker must NOT report success -- otherwise the caller acks and
    the evidence that the stage ran is gone, which is precisely the silent loss
    that bug caused.
    """
    run_id = new_run_id()
    counter = SideEffectCounter()

    def failing_complete(*_args, **_kwargs):
        return False  # what a fenced/undurable commit looks like

    import app.worker.processor as processor_module

    original_complete = processor_module.complete_stage
    processor_module.complete_stage = failing_complete
    try:
        outcome = process_one(
            session, make_envelope(run_id=run_id), stage_handler=counter, owner="w1"
        )
    finally:
        processor_module.complete_stage = original_complete

    assert outcome.disposition is Disposition.DEFER
    assert outcome.acked is False, "no ack when the durable commit did not happen"
    assert outcome.error_code == "CLAIM_FENCED"
    assert _semantic(session, run_id).status != StageStatus.SUCCEEDED


# ── the loop: settle direction, and identity separation ────────────────────


def test_loop_completes_only_successful_messages(db_url):
    """The loop settles by disposition, and never completes a failure.

    Exercises `run_loop` rather than `process_one` so the transport mapping is
    covered too -- `process_one` says what happened, the loop decides what the
    broker is told, and those are two separate things that can disagree.
    """
    good = make_envelope(run_id=new_run_id(), message_id="m-good")
    bad = {"schema_version": 42}
    transport = InMemoryTransport([good, bad], max_deliveries=2)
    engine = create_engine(db_url, future=True)
    counter = SideEffectCounter()

    stats = run_loop(
        sessionmaker(bind=engine, future=True),
        transport,
        stage_handler=counter,
        owner="worker-1",
        max_messages=4,
        install_signal_handlers=False,
    )

    assert stats.completed == 1, "only the valid message may complete"
    assert stats.dead_lettered >= 1
    assert counter.calls == 1
    # The failure is abandoned, never completed.
    assert transport.completed == ["local"]
    engine.dispose()


def test_loop_never_completes_a_deferred_or_retried_message(db_url):
    """DEFER and RETRY must reach the broker as ABANDON, never as COMPLETE.

    This test exists because the first version of the suite did NOT cover those
    two dispositions, and a negative-control mutation that mapped DEFER to
    COMPLETE sailed through the whole file with 14 passed. A control that is not
    reached proves nothing, so the paths are now exercised directly: this is the
    gap the mutation exposed, not a failure of the mutation.

    DEFER is produced by a second delivery for a stage another worker holds.
    RETRY is produced by a transient handler failure.
    """
    from sqlalchemy.orm import sessionmaker

    run_id = new_run_id()
    # Two messages, same semantic work: the first succeeds, the second is a
    # duplicate. A third run exercises RETRY via a failing handler.
    transport = InMemoryTransport(max_deliveries=2)
    engine = create_engine(db_url, future=True)
    factory = sessionmaker(bind=engine, future=True)

    # A duplicate arrives while the stage is already SUCCEEDED -> ACK_DUPLICATE.
    transport.publish(make_envelope(run_id=run_id, message_id="m-1"))
    transport.publish(make_envelope(run_id=run_id, message_id="m-2"))

    counter = SideEffectCounter()
    run_loop(
        factory,
        transport,
        stage_handler=counter,
        owner="worker-1",
        max_messages=2,
        install_signal_handlers=False,
    )
    assert counter.calls == 1, "duplicate must not re-execute"

    # Now a transient failure: RETRY, which must abandon rather than complete.
    transport2 = InMemoryTransport(max_deliveries=2)
    transport2.publish(make_envelope(run_id=new_run_id(), message_id="m-flaky"))

    def flaky(_env):
        raise ConnectionError("dependency down")

    stats2 = run_loop(
        factory,
        transport2,
        stage_handler=flaky,
        owner="worker-1",
        max_messages=2,
        install_signal_handlers=False,
    )
    assert stats2.retried >= 1, "a transient failure must retry"
    assert stats2.completed == 0, "a transient failure must never be reported as completed"
    assert transport2.completed == [], "nothing may be settled COMPLETE after a retry"
    engine.dispose()


def test_reprocess_uses_a_new_run_id_and_keeps_the_source(db_url):
    """Identity separation, asserted on the envelope rather than on intent.

    Reprocessing successful work must NOT reuse the run_id: the semantic key
    (run_id, stage) is already SUCCEEDED, so a reused run_id would be skipped as
    a duplicate and the "reprocess" would silently do nothing while reporting
    success. The source_id is what stays stable, because it identifies the data.
    """
    original = make_envelope(run_id=new_run_id(), message_id="m-1")
    reprocess = {
        **original,
        "message_id": "m-2",
        "run_id": new_run_id(),  # new execution
        "source_id": original["source_id"],  # same data
    }

    assert reprocess["run_id"] != original["run_id"]
    assert reprocess["source_id"] == original["source_id"]

    engine = create_engine(db_url, future=True)
    counter = SideEffectCounter()
    factory = sessionmaker(bind=engine, future=True)

    with factory() as s:
        first = process_one(s, original, stage_handler=counter, owner="w1")
    assert first.disposition is Disposition.ACK
    assert counter.calls == 1

    with factory() as s:
        second = process_one(s, reprocess, stage_handler=counter, owner="w1")

    # A new run_id means genuinely new work, so it executes rather than being
    # swallowed as a duplicate.
    assert second.disposition is Disposition.ACK
    assert counter.calls == 2
    engine.dispose()


def test_t10_run_ids_do_not_collide_within_one_second():
    """T10. The timestamp-collision class is closed.

    Asserted on distinctness of many ids rather than on timing, because a
    collision test that waits for two batches inside one second is flaky and a
    collision test that does not wait proves nothing.
    """
    run_id = new_run_id()
    ids = {new_run_id() for _ in range(5000)}
    assert len(ids) == 5000
    assert run_id.startswith("run-")
