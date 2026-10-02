"""PostgreSQL-backed ownership of a semantic stage.

`app/etl/stage_execution.py` decides WHO may execute. This module decides that
atomically and persists it. The separation is deliberate: the race between two
workers is closed by a database constraint, not by a Python branch, and a rule
that only LOOKS like it closes the race is worse than no rule at all because it
reads like a guarantee.

Identity, stated once so the rest of the codebase cannot get it wrong:

  semantic identity    (run_id, stage)   -- what work is this?
  attempt identity     (run_id, stage, attempt)
  transport identity   message_id        -- evidence, NEVER authority

The rule this module exists to enforce:

    once (run_id, stage) reaches SUCCEEDED, ordinary redelivery must NEVER
    execute it again.

That is what `TelemetryConsumer.processed_ids` could not do. An in-process set
is correct for exactly one process on exactly one machine, for exactly as long
as it is not restarted. Service Bus is at-least-once, workers scale to N
replicas, and both facts make the set wrong.

Correct claim shape, not a boolean. `False` cannot distinguish "another worker
has it" from "it is finished" from "you may retry", and the worker needs all
three to decide whether to execute, ack, or dead-letter.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.database.stage_models import StageAttemptRow, StageExecutionRow
from app.etl.stage_execution import MAX_ATTEMPTS_DEFAULT, Stage, StageStatus

DEFAULT_LEASE_SECONDS = 60


class ClaimOutcome(StrEnum):
    """What `claim_stage` decided. Every value implies exactly one next action."""

    ACQUIRED_NEW = "ACQUIRED_NEW"
    ACQUIRED_RETRY = "ACQUIRED_RETRY"
    ALREADY_RUNNING = "ALREADY_RUNNING"
    ALREADY_SUCCEEDED = "ALREADY_SUCCEEDED"
    TERMINAL_FAILED = "TERMINAL_FAILED"
    DEAD_LETTERED = "DEAD_LETTERED"
    STALE_CLAIM_RECOVERED = "STALE_CLAIM_RECOVERED"


#: Outcomes where this caller owns the work and MUST execute it.
OWNS_WORK: frozenset[ClaimOutcome] = frozenset(
    {
        ClaimOutcome.ACQUIRED_NEW,
        ClaimOutcome.ACQUIRED_RETRY,
        ClaimOutcome.STALE_CLAIM_RECOVERED,
    }
)

#: Outcomes where the work is finished and must NEVER be executed again.
ALREADY_DONE: frozenset[ClaimOutcome] = frozenset(
    {
        ClaimOutcome.ALREADY_SUCCEEDED,
        ClaimOutcome.TERMINAL_FAILED,
        ClaimOutcome.DEAD_LETTERED,
    }
)


@dataclass(frozen=True)
class Claim:
    """The verdict plus the identifiers a caller needs to act on it.

    `attempt` is None when this caller does not own the work, because there is
    no attempt of its own to report. Handing back a plausible-looking number
    would invite a caller to log an attempt that does not exist.
    """

    outcome: ClaimOutcome
    run_id: str
    stage: Stage
    attempt: int | None
    status: StageStatus
    owner: str | None
    lease_expires_at: datetime | None


class StageClaimRaceError(RuntimeError):
    """The row changed between reading it and taking it.

    Not a bug and not a duplicate: it means another worker moved the stage in
    the window this transaction was open. The caller retries the DECISION and
    gets whatever the new state implies. Silently continuing would mean acting
    on a stale read.
    """


def _db_now(session: Session) -> datetime:
    """Read the DATABASE clock.

    Lease correctness must not depend on worker clocks agreeing. Two containers
    with skewed clocks would otherwise disagree about who owns a claim, and the
    loser would execute work the winner also believes it owns.
    """
    return session.execute(select(func.now())).scalar_one()


def _claim(
    outcome: ClaimOutcome,
    *,
    run_id: str,
    stage: Stage,
    attempt: int | None,
    status: StageStatus,
    owner: str | None,
    lease_expires_at: datetime | None,
) -> Claim:
    return Claim(
        outcome=outcome,
        run_id=run_id,
        stage=stage,
        attempt=attempt,
        status=status,
        owner=owner,
        lease_expires_at=lease_expires_at,
    )


def _from_row(row: StageExecutionRow, outcome: ClaimOutcome) -> Claim:
    """Verdict for a caller that does NOT own the work.

    `attempt` is None here on purpose. Reporting the existing attempt number
    would invite a caller to log or ack an attempt that is not its own.
    """
    return _claim(
        outcome,
        run_id=row.run_id,
        stage=Stage(row.stage),
        attempt=None,
        status=StageStatus(row.status),
        owner=row.claim_owner,
        lease_expires_at=row.lease_expires_at,
    )


def _insert_attempt(
    session: Session,
    *,
    run_id: str,
    stage: Stage,
    attempt: int,
    message_id: str | None,
    correlation_id: str | None,
    now: datetime,
) -> None:
    session.add(
        StageAttemptRow(
            run_id=run_id,
            stage=stage.value,
            attempt=attempt,
            status=StageStatus.RUNNING.value,
            message_id=message_id,
            correlation_id=correlation_id,
            started_at=now,
            created_at=now,
            updated_at=now,
        )
    )


def claim_stage(
    session: Session,
    *,
    run_id: str,
    stage: Stage,
    owner: str | None = None,
    message_id: str | None = None,
    correlation_id: str | None = None,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> Claim:
    """Take ownership of one semantic stage, or report why not.

    Atomic. Two workers calling this for the same (run_id, stage) concurrently
    produce exactly one ACQUIRED_* and one duplicate verdict; the DATABASE
    decides, not the order the two Python processes happen to run in.

    The insert uses ON CONFLICT DO NOTHING, so the loser of the race neither
    raises nor has to catch UniqueViolation just to learn it lost. It re-reads
    the row the winner wrote and reports the matching verdict. A SELECT-then-
    INSERT would leave a window where both workers see no row and both insert.
    """
    owner = owner or f"worker-{uuid.uuid4().hex[:12]}"
    now = _db_now(session)
    lease_until = now + timedelta(seconds=lease_seconds)

    # 1. Try to create the semantic row. DO NOTHING, not DO UPDATE: a blind
    #    upsert would let a duplicate silently steal a live claim.
    inserted_id = session.execute(
        pg_insert(StageExecutionRow)
        .values(
            run_id=run_id,
            stage=stage.value,
            status=StageStatus.RUNNING.value,
            attempt_count=1,
            message_id=message_id,
            correlation_id=correlation_id,
            claim_owner=owner,
            claimed_at=now,
            lease_expires_at=lease_until,
            heartbeat_at=now,
            started_at=now,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(index_elements=["run_id", "stage"])
        .returning(StageExecutionRow.id)
    ).scalar_one_or_none()

    if inserted_id is not None:
        # 2. We created it, so we own it. The attempt row goes in the SAME
        #    transaction: a semantic row claiming attempt_count=1 with no
        #    matching attempt would make the count a lie.
        _insert_attempt(
            session,
            run_id=run_id,
            stage=stage,
            attempt=1,
            message_id=message_id,
            correlation_id=correlation_id,
            now=now,
        )
        session.flush()
        return _claim(
            ClaimOutcome.ACQUIRED_NEW,
            run_id=run_id,
            stage=stage,
            attempt=1,
            status=StageStatus.RUNNING,
            owner=owner,
            lease_expires_at=lease_until,
        )

    # 3. Someone else got there first. Read what they left behind.
    row = session.execute(
        select(StageExecutionRow).where(
            StageExecutionRow.run_id == run_id,
            StageExecutionRow.stage == stage.value,
        )
    ).scalar_one()

    # SUCCEEDED is sticky. Checked first and returned with no mutation at all:
    # no new attempt, no lease refresh, no field touched. This is the branch
    # that makes redelivery-after-success a no-op instead of a second
    # execution, and it is the single most important behaviour here.
    if row.status == StageStatus.SUCCEEDED:
        return _from_row(row, ClaimOutcome.ALREADY_SUCCEEDED)

    if row.status == StageStatus.DEAD_LETTERED:
        return _from_row(row, ClaimOutcome.DEAD_LETTERED)

    # FAILED is terminal for ORDINARY delivery. Only a governed replay may
    # revive it, and replay is a separate operation that does not come through
    # this function.
    if row.status == StageStatus.FAILED:
        return _from_row(row, ClaimOutcome.TERMINAL_FAILED)

    if row.status == StageStatus.RUNNING:
        expired = row.lease_expires_at is not None and row.lease_expires_at <= now
        if not expired:
            return _from_row(row, ClaimOutcome.ALREADY_RUNNING)
        # Lease expired: the previous owner crashed or was killed. Its attempt
        # is NOT deleted or rewritten -- it becomes RETRYABLE, which is honest
        # about what happened, and the recovering worker takes attempt N+1.
        # Deleting it would erase the only evidence that it existed.
        session.execute(
            update(StageAttemptRow)
            .where(
                StageAttemptRow.run_id == run_id,
                StageAttemptRow.stage == stage.value,
                StageAttemptRow.attempt == row.attempt_count,
            )
            .values(status=StageStatus.RETRYABLE.value, completed_at=now, updated_at=now)
        )
        outcome = ClaimOutcome.STALE_CLAIM_RECOVERED
    else:
        # PENDING or RETRYABLE: an ordinary retry, if budget remains. The count
        # is re-read from the row rather than taken from a Python-side counter
        # for the same reason the increment below is done in SQL.
        current = session.execute(
            select(StageExecutionRow.attempt_count).where(StageExecutionRow.id == row.id)
        ).scalar_one()
        if current >= MAX_ATTEMPTS_DEFAULT:
            return _from_row(row, ClaimOutcome.TERMINAL_FAILURE)
        outcome = ClaimOutcome.ACQUIRED_RETRY

    # 4. Take the claim. Two things are load-bearing here.
    #
    #    (a) The WHERE clause is the concurrency guard: it matches only while
    #        status and owner are still what we just read, so if another worker
    #        changed them in the window this transaction was open, the update
    #        affects zero rows and we detect that instead of clobbering the new
    #        owner.
    #
    #    (b) The next attempt number is computed by the DATABASE
    #        (attempt_count + 1), not in Python from `row.attempt_count`. A
    #        Session's identity map can hand back an object whose fields were
    #        synchronised by an earlier statement in this same transaction, so
    #        the Python-side value is not necessarily what is in the row. Doing
    #        the arithmetic in Python produced attempts 1 then 3 with a
    #        semantic count of 2 -- a gap that made attempt_count disagree with
    #        the attempt rows it claims to count. RETURNING the database's own
    #        value keeps the two in step by construction.
    taken = session.execute(
        update(StageExecutionRow)
        .where(
            StageExecutionRow.id == row.id,
            StageExecutionRow.status == row.status,
            StageExecutionRow.claim_owner == row.claim_owner,
        )
        .values(
            status=StageStatus.RUNNING.value,
            attempt_count=StageExecutionRow.attempt_count + 1,
            claim_owner=owner,
            claimed_at=now,
            lease_expires_at=lease_until,
            heartbeat_at=now,
            started_at=now,
            updated_at=now,
        )
        .returning(StageExecutionRow.attempt_count)
    )
    new_attempt = taken.scalar_one_or_none()
    if new_attempt is None:
        session.rollback()
        raise StageClaimRaceError(
            f"stage {stage.value} of run {run_id} changed while claiming; re-read and decide again"
        )

    _insert_attempt(
        session,
        run_id=run_id,
        stage=stage,
        attempt=new_attempt,
        message_id=message_id,
        correlation_id=correlation_id,
        now=now,
    )
    session.flush()
    return _claim(
        outcome,
        run_id=run_id,
        stage=stage,
        attempt=new_attempt,
        status=StageStatus.RUNNING,
        owner=owner,
        lease_expires_at=lease_until,
    )


def complete_stage(
    session: Session,
    *,
    run_id: str,
    stage: Stage,
    attempt: int,
    owner: str,
    output_artifact_ref: str | None = None,
    output_checksum: str | None = None,
) -> bool:
    """Record durable success for an attempt this caller owns.

    SUCCEEDED is sticky, so this is the only forward move available from
    RUNNING and it is irreversible.

    The owner is part of the WHERE clause, and that is not bookkeeping. A worker
    whose lease was already recovered by somebody else must not be able to
    finish work it no longer owns, because its output was computed under a lease
    that had expired and may have been written concurrently with the new
    owner's. Returns False when the guard rejected the write, so the caller
    learns its result was discarded rather than assuming it was recorded.
    """
    now = _db_now(session)
    semantic = session.execute(
        update(StageExecutionRow)
        .where(
            StageExecutionRow.run_id == run_id,
            StageExecutionRow.stage == stage.value,
            StageExecutionRow.claim_owner == owner,
            StageExecutionRow.status == StageStatus.RUNNING.value,
        )
        .values(
            status=StageStatus.SUCCEEDED.value,
            completed_at=now,
            succeeded_at=now,
            output_artifact_ref=output_artifact_ref,
            output_checksum=output_checksum,
            # Lease released. A SUCCEEDED row is not being worked on, so keeping
            # an owner would misrepresent who holds it.
            claim_owner=None,
            lease_expires_at=None,
            updated_at=now,
        )
    )
    if semantic.rowcount != 1:
        return False

    session.execute(
        update(StageAttemptRow)
        .where(
            StageAttemptRow.run_id == run_id,
            StageAttemptRow.stage == stage.value,
            StageAttemptRow.attempt == attempt,
        )
        .values(
            status=StageStatus.SUCCEEDED.value,
            completed_at=now,
            output_artifact_ref=output_artifact_ref,
            output_checksum=output_checksum,
            updated_at=now,
        )
    )
    session.flush()
    return True
