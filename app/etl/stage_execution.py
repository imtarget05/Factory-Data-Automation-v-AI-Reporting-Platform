"""StageExecution domain semantics — the state machine, before any columns.

Deliberately PURE. No SQLAlchemy import, no session, no database. The business
rules of "what may follow what" are decided here so they can be read, tested and
mutation-controlled without a database, and so the persistence layer is a dumb
recorder of decisions this module already made.

Adding columns first is how you get a schema that permits states the business
does not allow. The constraint and the intent have to agree, and the intent has
to exist first.

IDENTITY
--------

    (run_id, stage)

is the semantic key. One logical unit of work, executed at most once.

`message_id` is NOT part of the key, and that is the load-bearing decision.
Service Bus is at-least-once: a redelivery may arrive carrying a new transport
message id while describing identical semantic work. Keying on message_id would
run the same stage twice on exactly the redelivery it was meant to deduplicate.
Keying on (run_id, stage) is correct for redelivery and wrong for a genuine
replay — which is why replay is an explicit separate operation carrying its own
attempt number, not a silently new key.

ATTEMPTS
--------

One row per ATTEMPT, not one row updated in place.

The alternative — a single row with an `attempt` counter that gets overwritten —
destroys the evidence this table exists to keep. "How many times did GOLD fail,
and with what error, before it succeeded?" is unanswerable once attempt 3
overwrites attempt 1. Crash investigation is the whole point of the table.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum

__all__ = [
    "Stage",
    "StageStatus",
    "TransitionError",
    "StageExecution",
    "AcquisitionResult",
    "MAX_ATTEMPTS_DEFAULT",
    "PIPELINE_ORDER",
    "TERMINAL",
    "can_transition",
    "next_status",
    "acquire",
]

MAX_ATTEMPTS_DEFAULT = 5
"""Bounded retry policy.

Five is not magic: short enough that genuinely broken input dead-letters in
minutes instead of holding a delivery slot for an hour, long enough to ride out
a database failover or a storage blip without dead-lettering work that would
have succeeded.
"""


class Stage(StrEnum):
    """The pipeline stages, in order.

    Order is declared in PIPELINE_ORDER rather than inferred from the enum,
    because the ordering is business meaning ("SILVER cannot precede TRANSFORM")
    and an enum's alphabetical order is not a contract.
    """

    INGEST = "INGEST"
    VALIDATE = "VALIDATE"
    TRANSFORM = "TRANSFORM"
    SILVER = "SILVER"
    GOLD = "GOLD"
    MART = "MART"
    QUALITY = "QUALITY"
    REPORT_ELIGIBILITY = "REPORT_ELIGIBILITY"


PIPELINE_ORDER: tuple[Stage, ...] = (
    Stage.INGEST,
    Stage.VALIDATE,
    Stage.TRANSFORM,
    Stage.SILVER,
    Stage.GOLD,
    Stage.MART,
    Stage.QUALITY,
    Stage.REPORT_ELIGIBILITY,
)


class StageStatus(StrEnum):
    """Stage lifecycle states. Every one has transition semantics."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    RETRYABLE = "RETRYABLE"
    FAILED = "FAILED"
    DEAD_LETTERED = "DEAD_LETTERED"


TERMINAL: frozenset[StageStatus] = frozenset({StageStatus.SUCCEEDED, StageStatus.DEAD_LETTERED})

# The permitted transition graph, stated once.
#
# FAILED is reachable only from RUNNING and leads nowhere. It means "this attempt
# died and retrying the same attempt is pointless" — a corrupt payload, an invalid
# envelope. RETRYABLE is the one that leads onward, and conflating the two is how
# poison messages end up in an infinite retry loop.
_ALLOWED: dict[StageStatus, frozenset[StageStatus]] = {
    StageStatus.PENDING: frozenset({StageStatus.RUNNING}),
    StageStatus.RUNNING: frozenset(
        {StageStatus.SUCCEEDED, StageStatus.RETRYABLE, StageStatus.FAILED}
    ),
    StageStatus.RETRYABLE: frozenset({StageStatus.RUNNING, StageStatus.DEAD_LETTERED}),
    StageStatus.SUCCEEDED: frozenset(),
    StageStatus.FAILED: frozenset(),
    StageStatus.DEAD_LETTERED: frozenset(),
}

# Why a status is terminal, quoted in the error, because "not allowed" with no
# reason is the kind of error that gets worked around instead of understood.
_TERMINAL_REASON = {
    StageStatus.SUCCEEDED: (
        "stage already SUCCEEDED; re-running it would duplicate a semantic "
        "output. Use the explicit replay operation if that is genuinely intended."
    ),
    StageStatus.DEAD_LETTERED: "stage is DEAD_LETTERED; retry budget spent. Replay required.",
    StageStatus.FAILED: "this attempt FAILED permanently; a NEW attempt is needed.",
}


class TransitionError(RuntimeError):
    """Raised when a transition is not permitted by the state machine."""


def can_transition(current: StageStatus, target: StageStatus) -> bool:
    """Whether ``current -> target`` is permitted.

    Separate from ``next_status`` so a caller can ASK rather than catch. That
    matters on a hot path where "is this a duplicate?" is the normal case and an
    exception would be the wrong control flow.
    """
    return target in _ALLOWED[current]


def next_status(current: StageStatus, target: StageStatus) -> StageStatus:
    """Validate and return the new status, or raise ``TransitionError``."""
    if can_transition(current, target):
        return target


@dataclass(frozen=True)
class StageExecution:
    """One attempt at one stage of one run.

    Frozen: a transition returns a NEW value and nothing mutates in place, so a
    caller holding an older reference cannot watch the row change underneath it,
    and "who changed this and when" stays answerable from the audit trail.
    """

    run_id: str
    stage: Stage
    status: StageStatus = StageStatus.PENDING
    attempt: int = 1
    message_id: str | None = None
    correlation_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    input_artifact_ref: str | None = None
    output_artifact_ref: str | None = None
    input_checksum: str | None = None
    output_checksum: str | None = None
    safe_error_code: str | None = None
    safe_error_message: str | None = None
    created_at: datetime = None  # type: ignore[assignment]
    updated_at: datetime = None  # type: ignore[assignment]

    @classmethod
    def start(
        cls,
        *,
        run_id: str,
        stage: Stage,
        attempt: int,
        message_id: str | None = None,
        correlation_id: str | None = None,
        input_artifact_ref: str | None = None,
        input_checksum: str | None = None,
        now: datetime | None = None,
    ) -> StageExecution:
        """Create a PENDING execution. ``started_at`` is NOT set here.

        It is set when the stage actually begins, which is a different moment
        from when it was scheduled. Conflating them makes a stage that waited
        thirty seconds behind a lock look like it ran for thirty seconds.
        """
        ts = now or datetime.now(UTC)
        return cls(
            run_id=run_id,
            stage=stage,
            status=StageStatus.PENDING,
            attempt=attempt,
            message_id=message_id,
            correlation_id=correlation_id,
            input_artifact_ref=input_artifact_ref,
            input_checksum=input_checksum,
            created_at=ts,
            updated_at=ts,
        )

    def to(self, target: StageStatus, now: datetime | None = None) -> StageExecution:
        """Return a new value in ``target`` with timestamps consistent with it.

        Timestamps are set HERE rather than at each call site so that
        "SUCCEEDED implies completed_at is set" cannot be violated by a caller
        that forgets.
        """
        ts = now or datetime.now(UTC)
        next_status(self.status, target)

        updates: dict[str, object] = {"status": target, "updated_at": ts}
        if target is StageStatus.RUNNING:
            updates["started_at"] = ts
        # A new attempt starts clean. Carrying the previous error into a RUNNING
        # row would make a live stage look like it had already failed.
        if target is StageStatus.RUNNING:
            updates["safe_error_code"] = None
            updates["safe_error_message"] = None
        if target in (StageStatus.SUCCEEDED, StageStatus.DEAD_LETTERED):
            updates["completed_at"] = ts
        return replace(self, **updates)

    def fail(
        self, error_code: str, error_message: str, *, now: datetime | None = None
    ) -> StageExecution:
        """Return RETRYABLE, or DEAD_LETTERED once the budget is spent.

        The decision is made in ONE place. Split between the caller and the retry
        loop, the two would eventually disagree about whether a poison message is
        still retryable, and that disagreement is an infinite loop.
        """
        if self.attempt >= MAX_ATTEMPTS_DEFAULT:
            return self.dead_letter(error_code, error_message, now=now)
        return self.to(StageStatus.RETRYABLE, now=now)

    def dead_letter(
        self, error_code: str, error_message: str, *, now: datetime | None = None
    ) -> StageExecution:
        """Terminal: retry budget spent. Only replay can revive this."""
        moved = self.to(StageStatus.DEAD_LETTERED, now=now)
        return replace(moved, safe_error_code=error_code, safe_error_message=error_message)

    def succeed(
        self,
        *,
        output_artifact_ref: str | None = None,
        output_checksum: str | None = None,
        now: datetime | None = None,
    ) -> StageExecution:
        """Terminal success, with the output reference recorded.

        The checksum is recorded alongside the reference on purpose: an artifact
        at a path proves nothing if the bytes behind it can change. This is what
        makes a redelivered GOLD distinguishable from the original GOLD.
        """
        moved = self.to(StageStatus.SUCCEEDED, now=now)
        return replace(
            moved,
            output_artifact_ref=output_artifact_ref,
            output_checksum=output_checksum,
        )


class AcquisitionResult(StrEnum):
    """What happened when a worker tried to take ownership of a stage."""

    ACQUIRED = "ACQUIRED"
    ALREADY_RUNNING = "ALREADY_RUNNING"
    ALREADY_SUCCEEDED = "ALREADY_SUCCEEDED"
    RETRY_ALLOWED = "RETRY_ALLOWED"
    TERMINAL_FAILURE = "TERMINAL_FAILURE"


def acquire(
    existing: StageExecution | None,
    *,
    run_id: str,
    stage: Stage,
    attempt: int,
    message_id: str | None = None,
    correlation_id: str | None = None,
    now: datetime | None = None,
) -> tuple[AcquisitionResult, StageExecution]:
    """Decide whether this worker may execute the stage.

    PURE. The caller performs the database transaction; this function only
    answers the question. That split matters: the race is closed by a database
    constraint, not by this code, and a rule that LOOKS like it closes the race
    when it does not is worse than no rule at all.

    Returns the verdict and the row to persist, which is the existing row
    unchanged when this worker is a duplicate.
    """
    if existing is None:
        return AcquisitionResult.ACQUIRED, StageExecution.start(
            run_id=run_id,
            stage=stage,
            attempt=attempt,
            message_id=message_id,
            correlation_id=correlation_id,
            now=now,
        )

    # A different stage under the same run is a programming error, not a
    # duplicate. Treating it as a duplicate would hide a bug behind a
    # normal-looking "already done" response.
    if existing.stage != stage:
        raise TransitionError(
            f"existing execution for run {run_id} is stage "
            f"{existing.stage.value}, not {stage.value}"
        )

    if existing.status is StageStatus.SUCCEEDED:
        return AcquisitionResult.ALREADY_SUCCEEDED, existing
    if existing.status is StageStatus.RUNNING:
        return AcquisitionResult.ALREADY_RUNNING, existing
    if existing.status in (StageStatus.DEAD_LETTERED, StageStatus.FAILED):
        # A permanent failure or a spent retry budget means this work is done.
        # A NEW attempt number is a new logical attempt, which is a replay
        # decision -- not something a redelivery may take on its own.
        return AcquisitionResult.TERMINAL_FAILURE, existing
    if existing.attempt >= MAX_ATTEMPTS_DEFAULT:
        return AcquisitionResult.TERMINAL_FAILURE, existing
    # PENDING or RETRYABLE: this worker may take it.
    return AcquisitionResult.RETRY_ALLOWED, existing
