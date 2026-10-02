"""SQLAlchemy mapping for the `stage_executions` / `stage_attempts` pair created by
migration 0003.

These tables are NOT in `app/database/models.py` on purpose. That module is the
legacy surface: it calls `Base.metadata.create_all()` and defaults to SQLite, which
is fine for the demo domain records but wrong for the run-state ledger. Run state
decides whether a piece of work has already happened, so it gets a real migration,
real constraints and real tests against a real PostgreSQL.

The split the schema encodes, and that this module has to keep straight:

  stage_executions  ONE row per (run_id, stage) -- the semantic unit of work.
                    uq_stage_executions_semantic makes that structural.
  stage_attempts    ONE row per attempt, never overwritten. Audit evidence.

A transport `message_id` appears in both tables, but it is NOT the identity. A
redelivery is a new transport message describing the same semantic work, which is
exactly the case the `(run_id, stage)` key exists to collapse.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class StageBase(DeclarativeBase):
    """Own declarative base, separate from the legacy `models.Base`.

    Sharing one metadata would let `create_all()` on the legacy base silently
    create these tables outside any migration, which is the failure mode
    migration 0003 exists to eliminate.
    """


class StageExecutionRow(StageBase):
    """The semantic state of one unit of work: one row per (run_id, stage).

    The lease columns (claim_owner, claimed_at, lease_expires_at, heartbeat_at)
    are what make a crashed worker recoverable. Without lease_expires_at a
    RUNNING row occupies its own semantic slot forever, and the unit of work can
    never be retried by anyone.
    """

    __tablename__ = "stage_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    # A COUNT of attempt rows, not a licence to create one. claim_stage()
    # increments it in the same transaction that inserts the attempt, so the two
    # cannot disagree.
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
    message_id: Mapped[str | None] = mapped_column(String(128))
    correlation_id: Mapped[str | None] = mapped_column(String(128))

    # Lease. Written from the DATABASE clock, never a worker's clock, so two
    # workers with skewed clocks cannot disagree about who owns the work.
    claim_owner: Mapped[str | None] = mapped_column(String(128))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    succeeded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    output_artifact_ref: Mapped[str | None] = mapped_column(String(512))
    output_checksum: Mapped[str | None] = mapped_column(String(64))
    safe_error_code: Mapped[str | None] = mapped_column(String(64))
    safe_error_message: Mapped[str | None] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # THE semantic key. One row per unit of work for the whole life of that
        # unit. Not partial, not conditional.
        UniqueConstraint("run_id", "stage", name="uq_stage_executions_semantic"),
        CheckConstraint("attempt_count >= 0", name="ck_stage_executions_attempt_count"),
        CheckConstraint(
            "status <> 'SUCCEEDED' OR succeeded_at IS NOT NULL",
            name="ck_stage_executions_succeeded_final",
        ),
        Index("ix_stage_executions_run_id", "run_id"),
        Index("ix_stage_executions_status", "status"),
        Index("ix_stage_executions_correlation_id", "correlation_id"),
        # Recovery sweep: "find claims whose lease has run out".
        Index("ix_stage_executions_lease", "status", "lease_expires_at"),
    )


class StageAttemptRow(StageBase):
    """One row per attempt. Append-only: an attempt that happened is evidence.

    Never rewrite an attempt's status once it is terminal. A retry writes attempt
    N+1; the reason attempt N failed stays readable, which is the whole point of
    separating this table from stage_executions.
    """

    __tablename__ = "stage_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    message_id: Mapped[str | None] = mapped_column(String(128))
    correlation_id: Mapped[str | None] = mapped_column(String(128))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_artifact_ref: Mapped[str | None] = mapped_column(String(512))
    output_artifact_ref: Mapped[str | None] = mapped_column(String(512))
    input_checksum: Mapped[str | None] = mapped_column(String(64))
    output_checksum: Mapped[str | None] = mapped_column(String(64))
    safe_error_code: Mapped[str | None] = mapped_column(String(64))
    safe_error_message: Mapped[str | None] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("run_id", "stage", "attempt", name="uq_stage_attempts_run_stage_attempt"),
        CheckConstraint("attempt >= 1", name="ck_stage_attempts_attempt_positive"),
        CheckConstraint(
            "status <> 'SUCCEEDED' OR completed_at IS NOT NULL",
            name="ck_stage_attempts_succeeded_has_completed_at",
        ),
        Index("ix_stage_attempts_run_stage", "run_id", "stage"),
        Index("ix_stage_attempts_status", "status"),
    )
