"""split semantic stage state from attempt history; make SUCCEEDED sticky

WHY THIS MIGRATION EXISTS
=========================

The previous revision (0002) put semantic ownership in a PARTIAL UNIQUE index:

    UNIQUE(run_id, stage) WHERE status IN ('PENDING','RUNNING','RETRYABLE')

That proved exactly one thing: at most one IN-FLIGHT attempt. It did NOT prove
at most one SUCCESSFUL semantic execution, and the difference is the whole
point. The observed sequence was:

    attempt 1  RUNNING     -> holds the slot
    attempt 1  SUCCEEDED   -> terminal, slot RELEASED
    attempt 2  RUNNING     -> allowed again, same (run_id, stage)

Attempt 2 re-executes the side effects of a stage that already succeeded. Two
Gold marts, two reports, one run -- and nothing downstream can tell them apart.
A partial index over non-terminal states is the wrong shape for this problem:
it makes SUCCEEDED mean "finished and therefore available again", when it has
to mean "finished and therefore never again, for this (run_id, stage)".

THE SPLIT
=========

stage_executions  SEMANTIC state, one row per (run_id, stage)
    The trust question: is this unit of work running, done, retryable, or dead?
    Its status is STICKY. SUCCEEDED is final.

stage_attempts    AUDIT history, one row per (run_id, stage, attempt)
    The evidence question: what happened, how many times, with which error.
    Append-only; never updated in place, never deleted.

A retry after a retryable failure is a new ROW in stage_attempts while
stage_executions keeps its identity and moves RETRYABLE -> RUNNING. Audit
history is preserved and semantic identity is not weakened by several attempts.

SUCCEEDED IS STICKY
===================

    ck_stage_executions_succeeded_final
        status <> 'SUCCEEDED' OR succeeded_at IS NOT NULL

plus the absence of any transition out of SUCCEEDED in
app.etl.stage_execution. A redelivery of a succeeded stage returns
ALREADY_SUCCEEDED and creates no attempt. There is deliberately NO database path
that reopens a SUCCEEDED stage.

REPROCESSING IS A NEW RUN
========================

"Recompute Gold for the same source" is a NEW run_id with the SAME source_id --
which is exactly why run_identity.py keeps the two concepts separate. Same
run_id with a higher attempt is NOT the reprocess mechanism; allowing it is the
bug this migration removes.

DATA SAFETY
===========

Existing attempt rows are COPIED, not dropped: each becomes a stage_attempts
row, and a stage_executions row is synthesised per (run_id, stage) carrying the
LATEST attempt's outcome. A run that already SUCCEEDED arrives as SUCCEEDED,
which is the sticky state we want.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d4e7b1c90a52"
down_revision = "b2c1d0e4a7f9"
branch_labels = None
depends_on = None

# Statuses that are not final. FAILED and DEAD_LETTERED are excluded because
# both need an EXPLICIT replay, which a plain redelivery must never trigger.
_LIVE = "'PENDING', 'RUNNING', 'RETRYABLE'"


def upgrade() -> None:
    # Move the OLD table out of the way FIRST. Creating a table that already
    # exists is a DuplicateTable error, and dropping first would throw away the
    # evidence the copy step below reads. Renaming is the only ordering that
    # makes both the CREATE and the copy work, and it is done inside the
    # migration's transaction so a failure rolls the rename back too.
    op.rename_table("stage_executions", "stage_executions_legacy")

    # Drop the old indexes NOW, before the CREATE below. Renaming the table
    # carried its indexes along, and they keep their original names -- so
    # `ix_stage_executions_id` still exists and the new table's id index cannot
    # be created. The data is all that is being carried forward, so the indexes
    # are genuinely disposable here and are rebuilt by the new CREATE blocks.
    for legacy_index in (
        "uq_stage_executions_semantic_active",
        "ix_stage_executions_status_started_at",
        "ix_stage_executions_correlation_id",
        "ix_stage_executions_status",
        "ix_stage_executions_run_id_stage",
        "ix_stage_executions_run_id",
    ):
        op.drop_index(legacy_index, table_name="stage_executions_legacy")

    # ── 1. semantic state ────────────────────────────────────────────────────
    op.create_table(
        "stage_executions",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        # A COUNT of evidence rows, not a licence to create one. claim_stage()
        # increments it in the same transaction that inserts the attempt, so
        # the two can never disagree.
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("message_id", sa.String(128), nullable=True),
        sa.Column("correlation_id", sa.String(128), nullable=True),
        # Lease fields. lease_expires_at is what makes a crashed worker's claim
        # recoverable; without it a RUNNING row blocks its own semantic slot
        # forever. Written from the DATABASE clock (now()), never from a
        # worker's clock, so two workers with skewed clocks cannot disagree
        # about who owns the lease.
        sa.Column("claim_owner", sa.String(128), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("succeeded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("output_artifact_ref", sa.String(512), nullable=True),
        sa.Column("output_checksum", sa.String(64), nullable=True),
        sa.Column("safe_error_code", sa.String(64), nullable=True),
        sa.Column("safe_error_message", sa.String(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        # THE semantic key. Not partial, not conditional, not negotiable: one
        # row per unit of work for the whole life of that unit.
        sa.UniqueConstraint("run_id", "stage", name="uq_stage_executions_semantic"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_stage_executions_attempt_count"),
        sa.CheckConstraint(
            "status <> 'SUCCEEDED' OR succeeded_at IS NOT NULL",
            name="ck_stage_executions_succeeded_final",
        ),
    )

    op.create_index("ix_stage_executions_run_id", "stage_executions", ["run_id"])
    op.create_index("ix_stage_executions_status", "stage_executions", ["status"])
    op.create_index(
        "ix_stage_executions_correlation_id", "stage_executions", ["correlation_id"]
    )
    # Recovery sweep: "find claims whose lease has run out".
    op.create_index(
        "ix_stage_executions_lease", "stage_executions", ["status", "lease_expires_at"]
    )

    # ── 2. attempt history ───────────────────────────────────────────────────
    op.create_table(
        "stage_attempts",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("attempt", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("message_id", sa.String(128), nullable=True),
        sa.Column("correlation_id", sa.String(128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input_artifact_ref", sa.String(512), nullable=True),
        sa.Column("output_artifact_ref", sa.String(512), nullable=True),
        sa.Column("input_checksum", sa.String(64), nullable=True),
        sa.Column("output_checksum", sa.String(64), nullable=True),
        sa.Column("safe_error_code", sa.String(64), nullable=True),
        sa.Column("safe_error_message", sa.String(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "run_id", "stage", "attempt", name="uq_stage_attempts_run_stage_attempt"
        ),
        sa.CheckConstraint("attempt >= 1", name="ck_stage_attempts_attempt_positive"),
        sa.CheckConstraint(
            "status <> 'SUCCEEDED' OR completed_at IS NOT NULL",
            name="ck_stage_attempts_succeeded_has_completed_at",
        ),
    )

    op.create_index("ix_stage_attempts_run_stage", "stage_attempts", ["run_id", "stage"])
    # ── 3. migrate the evidence, do not destroy it ───────────────────────────
    # Every existing attempt row becomes a stage_attempts row verbatim.
    op.execute(
        """
        INSERT INTO stage_attempts (
            run_id, stage, attempt, status, message_id, correlation_id,
            started_at, completed_at, input_artifact_ref, output_artifact_ref,
            input_checksum, output_checksum, safe_error_code, safe_error_message,
            created_at, updated_at
        )
        SELECT run_id, stage, attempt, status, message_id, correlation_id,
               started_at, completed_at, input_artifact_ref, output_artifact_ref,
               input_checksum, output_checksum, safe_error_code, safe_error_message,
               created_at, updated_at
        FROM stage_executions_legacy
        """
    )

    # One semantic row per (run_id, stage), carrying the LATEST attempt.
    # DISTINCT ON is the honest way to say "newest evidence wins" in one
    # statement, and doing it in SQL keeps it inside the migration's transaction
    # rather than depending on application code that may change underneath it.
    op.execute(
        """
        INSERT INTO stage_executions (
            run_id, stage, status, attempt_count, message_id, correlation_id,
            started_at, completed_at, succeeded_at, output_artifact_ref,
            output_checksum, safe_error_code, safe_error_message,
            created_at, updated_at
        )
        SELECT DISTINCT ON (run_id, stage)
               run_id, stage, status, attempt,
               message_id, correlation_id,
               started_at, completed_at,
               CASE WHEN status = 'SUCCEEDED'
                    THEN COALESCE(completed_at, updated_at) END,
               output_artifact_ref, output_checksum,
               safe_error_code, safe_error_message,
               created_at, updated_at
        FROM stage_executions_legacy
        ORDER BY run_id, stage, attempt DESC
        """
    )

    # The old table's data is now in stage_attempts AND stage_executions.
    op.drop_table("stage_executions_legacy")


def downgrade() -> None:
    # Re-merged into one table. The semantic/attempt distinction is LOST on the
    # way down, which is the honest cost: downgrading re-introduces the
    # released-slot behaviour this migration exists to remove. Stated so nobody
    # downgrades production expecting behaviour to be preserved.
    op.create_table(
        "stage_executions_legacy",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("attempt", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("message_id", sa.String(128), nullable=True),
        sa.Column("correlation_id", sa.String(128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input_artifact_ref", sa.String(512), nullable=True),
        sa.Column("output_artifact_ref", sa.String(512), nullable=True),
        sa.Column("input_checksum", sa.String(64), nullable=True),
        sa.Column("output_checksum", sa.String(64), nullable=True),
        sa.Column("safe_error_code", sa.String(64), nullable=True),
        sa.Column("safe_error_message", sa.String(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute(
        "INSERT INTO stage_executions_legacy SELECT run_id, stage, attempt, status, "
        "message_id, correlation_id, started_at, completed_at, input_artifact_ref, "
        "output_artifact_ref, input_checksum, output_checksum, safe_error_code, "
        "safe_error_message, created_at, updated_at FROM stage_attempts"
    )
    op.drop_table("stage_attempts")
    op.drop_index("ix_stage_executions_lease", table_name="stage_executions")
    op.drop_index("ix_stage_executions_status", table_name="stage_executions")
    op.drop_index("ix_stage_executions_correlation_id", table_name="stage_executions")
    op.drop_index("ix_stage_executions_run_id", table_name="stage_executions")
    op.drop_table("stage_executions")
    op.rename_table("stage_executions_legacy", "stage_executions")
    op.execute(
        f"CREATE UNIQUE INDEX uq_stage_executions_semantic_active "
        f"ON stage_executions (run_id, stage) WHERE status IN ({_LIVE})"
    )
    op.create_index("ix_stage_attempts_status", "stage_attempts", ["status"])
