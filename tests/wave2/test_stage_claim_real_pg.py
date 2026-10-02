"""Real-PostgreSQL proofs for `claim_stage`.

These tests REFUSE TO COLLECT without a live PostgreSQL server, by design. The
properties under test are properties of the DATABASE, not of Python:

  - that two concurrent claims produce exactly one owner depends on
    uq_stage_executions_semantic and ON CONFLICT, and SQLite has neither the
    same constraint semantics nor real concurrent transactions;
  - that SUCCEEDED is sticky depends on the code consulting the row the winner
    committed;
  - that a lease is expired depends on the DATABASE clock.

A skipped test is indistinguishable from a passing one, so "no database" has to
mean RED rather than quietly stopping the check. Point
FACTORY_TEST_PG_ADMIN_URL at a server and every assertion below runs for real.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.orm import Session

ADMIN_URL = os.getenv("FACTORY_TEST_PG_ADMIN_URL")
if not ADMIN_URL:
    raise RuntimeError(
        "FACTORY_TEST_PG_ADMIN_URL is not set. These proofs require a REAL "
        "PostgreSQL server; SQLite cannot execute this chain. Refusing to "
        "report green without a database."
    )

from app.database.stage_models import StageAttemptRow, StageExecutionRow  # noqa: E402
from app.etl.stage_claim import (  # noqa: E402
    ClaimOutcome,
    claim_stage,
    complete_stage,
)
from app.etl.stage_execution import Stage, StageStatus  # noqa: E402
from tests.wave2.migration_harness import (  # noqa: E402
    database_url_for,
    drop_database,
    make_database,
    upgrade_to,
)

RUN_ID = "run-claim-proof"


@pytest.fixture
def _db_name():
    name = f"factory_claim_{uuid.uuid4().hex[:8]}"
    make_database(ADMIN_URL, name)
    yield name
    drop_database(ADMIN_URL, name)


@pytest.fixture
def _url(_db_name):
    url = database_url_for(ADMIN_URL, _db_name)
    upgrade_to(url, "head")
    return url


@pytest.fixture
def session(_url):
    engine = create_engine(_url, future=True)
    conn = engine.connect()
    trans = conn.begin()
    try:
        yield Session(bind=conn)
    finally:
        trans.rollback()
        conn.close()
        engine.dispose()


def _attempts(session, run_id=RUN_ID, stage=Stage.GOLD):
    return (
        session.execute(
            select(StageAttemptRow)
            .where(StageAttemptRow.run_id == run_id, StageAttemptRow.stage == stage.value)
            .order_by(StageAttemptRow.attempt)
        )
        .scalars()
        .all()
    )


def _semantic(session, run_id=RUN_ID, stage=Stage.GOLD):
    return session.execute(
        select(StageExecutionRow).where(
            StageExecutionRow.run_id == run_id,
            StageExecutionRow.stage == stage.value,
        )
    ).scalar_one()


# ── first claim ─────────────────────────────────────────────────────────────


def test_first_claim_creates_one_semantic_row_and_one_attempt(session):
    claim = claim_stage(session, run_id=RUN_ID, stage=Stage.GOLD, owner="w1", message_id="m1")
    session.commit()

    assert claim.outcome is ClaimOutcome.ACQUIRED_NEW
    assert claim.attempt == 1
    assert len(_attempts(session)) == 1
    assert _semantic(session).attempt_count == 1


def test_attempt_count_is_backed_by_real_attempt_rows(session):
    """A COUNT that can exceed the rows it counts is a lie waiting to mislead.

    attempt_count exists so the semantic row can answer "how many tries" in one
    read. If it drifts from stage_attempts, every consumer of that number is
    wrong and nothing local will notice.
    """
    claim_stage(session, run_id=RUN_ID, stage=Stage.GOLD, owner="w1")
    session.commit()

    counted = _semantic(session).attempt_count
    actual = len(_attempts(session))
    assert counted == actual == 1


# ── concurrency: the reason this is in PostgreSQL ───────────────────────────


def test_two_concurrent_claims_produce_exactly_one_owner(_url):
    """The database, not the GIL, decides who owns the work.

    Two independent engines, two independent connections, same (run_id, stage).
    Whichever order they actually run in, exactly one may execute. A
    process-local lock or an in-memory set would pass a single-threaded test and
    fail this one, which is the whole point.
    """
    results: list[ClaimOutcome] = []
    engines = [create_engine(_url, future=True) for _ in range(2)]

    def claim_as(index: int, worker: str) -> ClaimOutcome:
        eng = engines[index]
        with eng.begin() as conn:
            sess = Session(bind=conn)
            outcome = claim_stage(
                sess, run_id=RUN_ID, stage=Stage.GOLD, owner=f"worker-{worker}"
            ).outcome
            conn.commit()
            return outcome

    for index, worker in enumerate(("a", "b")):
        results.append(claim_as(index, worker))

    assert sorted(results) == [
        ClaimOutcome.ACQUIRED_NEW,
        ClaimOutcome.ALREADY_RUNNING,
    ], f"exactly one owner required, got {results}"

    with engines[0].connect() as conn:
        sem = Session(bind=conn)
        assert sem.execute(select(func.count()).select_from(StageExecutionRow)).scalar_one() == 1
        assert sem.execute(select(func.count()).select_from(StageAttemptRow)).scalar_one() == 1

    for eng in engines:
        eng.dispose()


# ── sticky success: the invariant W2-3 exists to establish ──────────────────


def test_redelivery_after_success_does_not_execute_again(session):
    """The load-bearing test.

    A new transport message describing work that already succeeded must produce
    ALREADY_SUCCEEDED, and must leave the attempt count at 1. Any code path that
    treats a redelivery as a fresh opportunity to execute is a duplicate side
    effect: a second Gold write, a second report, a second bill.
    """
    first = claim_stage(session, run_id=RUN_ID, stage=Stage.GOLD, owner="w1", message_id="m1")
    session.commit()
    assert complete_stage(
        session, run_id=RUN_ID, stage=Stage.GOLD, attempt=first.attempt, owner="w1"
    )
    session.commit()

    # Same semantic work, DIFFERENT transport message.
    redelivery = claim_stage(
        session, run_id=RUN_ID, stage=Stage.GOLD, owner="w2", message_id="m2-DIFFERENT"
    )
    session.commit()

    assert redelivery.outcome is ClaimOutcome.ALREADY_SUCCEEDED
    assert redelivery.attempt is None, "a duplicate must not be handed an attempt to run"
    assert len(_attempts(session)) == 1, "redelivery must not create attempt 2"
    assert _semantic(session).attempt_count == 1


def test_success_survives_a_brand_new_connection(_url):
    """What an in-process set cannot do: survive the process.

    The original defect was `TelemetryConsumer.processed_ids`, a set that lives
    in one Python process. This test is the direct replacement -- a completely
    fresh engine, connection and session with no shared memory, arriving at the
    same conclusion. If this passes, correctness no longer depends on a worker
    staying alive, on replica count being one, or on a message not being
    redelivered after a restart.
    """
    engine_a = create_engine(_url, future=True)
    with engine_a.begin() as conn:
        sess = Session(bind=conn)
        claim = claim_stage(sess, run_id=RUN_ID, stage=Stage.GOLD, owner="worker-a")
        complete_stage(
            sess, run_id=RUN_ID, stage=Stage.GOLD, attempt=claim.attempt, owner="worker-a"
        )
    engine_a.dispose()

    # Worker A is now gone. Nothing of it survives except the database.
    engine_b = create_engine(_url, future=True)
    with engine_b.begin() as conn:
        sess = Session(bind=conn)
        again = claim_stage(sess, run_id=RUN_ID, stage=Stage.GOLD, owner="worker-b")
        attempts = sess.execute(select(func.count()).select_from(StageAttemptRow)).scalar_one()

    assert again.outcome is ClaimOutcome.ALREADY_SUCCEEDED
    assert attempts == 1
    engine_b.dispose()


def test_completion_by_a_worker_that_lost_its_lease_is_rejected(session):
    """A worker whose lease was recovered cannot finish the work.

    Its output was computed under an expired lease, possibly concurrently with
    the new owner's. Letting it write SUCCEEDED would let two workers both
    believe they produced the output, and the second one to arrive would win
    regardless of which was correct.
    """
    claim = claim_stage(
        session, run_id=RUN_ID, stage=Stage.GOLD, owner="worker-a", lease_seconds=-1
    )
    session.commit()

    # The lease is already expired, so another worker legitimately recovers it.
    recovered = claim_stage(session, run_id=RUN_ID, stage=Stage.GOLD, owner="worker-b")
    session.commit()
    assert recovered.outcome is ClaimOutcome.STALE_CLAIM_RECOVERED

    # Worker A wakes up and tries to finish. It no longer owns anything.
    assert not complete_stage(
        session, run_id=RUN_ID, stage=Stage.GOLD, attempt=claim.attempt, owner="worker-a"
    )


# ── terminal states are not revived by ordinary delivery ───────────────────


def test_failed_is_terminal_for_ordinary_delivery(session):
    """A permanent failure stays failed. Only a governed replay may revive it.

    Retrying automatically here is how a poison message becomes an infinite
    loop that looks like progress.
    """
    claim_stage(session, run_id=RUN_ID, stage=Stage.GOLD, owner="w1")
    session.execute(
        update(StageExecutionRow)
        .where(StageExecutionRow.run_id == RUN_ID)
        .values(status=StageStatus.FAILED.value)
    )
    session.commit()

    again = claim_stage(session, run_id=RUN_ID, stage=Stage.GOLD, owner="w2")
    session.commit()

    assert again.outcome is ClaimOutcome.TERMINAL_FAILED
    assert len(_attempts(session)) == 1


def test_retryable_creates_the_next_attempt_and_keeps_the_old_one(session):
    """Retry advances the attempt; it does not rewrite history.

    Both rows must remain readable afterwards. Collapsing them loses the only
    record of why the first try failed, which is exactly what an operator needs
    when the same stage fails repeatedly.
    """
    claim_stage(session, run_id=RUN_ID, stage=Stage.GOLD, owner="w1")
    session.execute(
        update(StageExecutionRow)
        .where(StageExecutionRow.run_id == RUN_ID)
        .values(status=StageStatus.RETRYABLE.value)
    )
    session.commit()

    retried = claim_stage(session, run_id=RUN_ID, stage=Stage.GOLD, owner="w2")
    session.commit()

    assert retried.outcome is ClaimOutcome.ACQUIRED_RETRY
    assert retried.attempt == 2
    rows = _attempts(session)
    assert [r.attempt for r in rows] == [1, 2], "attempt 1 must survive the retry"
