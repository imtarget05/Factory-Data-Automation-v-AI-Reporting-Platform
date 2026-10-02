"""add stage execution: durable stage state with semantic idempotency

THE TWO KEYS, AND WHY THEY ARE NOT THE SAME
============================================

audit identity
    UNIQUE(run_id, stage, attempt)
    One row per attempt, kept as evidence. "How many times did GOLD fail, and
    with what error, before it succeeded?" is unanswerable without it.

semantic ownership
    PARTIAL UNIQUE INDEX on (run_id, stage) WHERE the row is non-terminal

    This is the one that prevents duplicate execution, and it is why
    (run_id, stage, attempt) is not sufficient on its own.

The failure it guards against is specific and easy to ship by accident:

    attempt 1  RUNNING   <- worker A is mid-flight
    attempt 2  RUNNING   <- worker B, written helpfully, saw the first "in
                            progress" and started a second attempt anyway

Two workers, same (run_id, stage), two side effects, one of them a duplicate
Gold mart that nothing will ever reconcile. A plain UNIQUE on
(run_id, stage, attempt) does NOT stop this, because attempt 1 and attempt 2 are
different keys. Only the partial unique index does: at most one non-terminal row
per semantic unit of work, whatever the attempt number.

TERMINAL MEANS TERMINAL
-----------------------

The predicate excludes SUCCEEDED, DEAD_LETTERED and FAILED, so once work has
finished its (run_id, stage) identity is released and a genuine REPLAY can
create a new attempt. That is the only sanctioned way to re-run a stage, and it
is explicit -- a redelivery cannot reach it, because a redelivery has no new
attempt number to offer.

STALE RUNNING
-------------

RUNNING is not terminal, so a row abandoned by a crashed worker keeps holding
its semantic slot and the next delivery would see ALREADY_RUNNING forever. The
index therefore only half-solves the problem. `started_at` is the recovery
signal: a lease timeout moves an abandoned RUNNING row to RETRYABLE, releasing
the slot. That transition belongs to the recovery policy, not to this
constraint -- the index exists so the policy has something correct to act on.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b2c1d0e4a7f9"
down_revision = "24c8e3994379"
branch_labels = None
depends_on = None


# Statuses that RELEASE a semantic slot. Mirrors TERMINAL in
# app.etl.stage_execution plus FAILED, kept as a literal here on purpose: a
# migration must not import application code that may change underneath it. If
def upgrade() -> None:
    op.create_table(
        "stage_executions",
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
        # Free-text error is unbounded unless constrained, and this column is
        # written from exception text. Capped so a pathological exception cannot
        # blow up a ledger row.
        sa.Column("safe_error_code", sa.String(64), nullable=True),
        sa.Column("safe_error_message", sa.String(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        # Audit identity. NOT the idempotency guarantee.
        sa.UniqueConstraint(
            "run_id", "stage", "attempt", name="uq_stage_executions_run_stage_attempt"
        ),
        # attempt 0 or negative is a caller bug, and a bug that produces attempt
        # 0 is exactly the bug that would slip past an application-side
        # "attempt >= 1" check.
        sa.CheckConstraint("attempt >= 1", name="ck_stage_executions_attempt_positive"),
        # SUCCEEDED without completed_at is an unmeasurable timeline; it makes
        # every later "how long did this take" question unanswerable.
        sa.CheckConstraint(
            "status <> 'SUCCEEDED' OR completed_at IS NOT NULL",
            name="ck_stage_executions_succeeded_has_completed_at",
        ),
    )

    # Query dimensions that are actually used, and no others. run_id alone
    # because "everything about this run" is the most common question;
    # (run_id, stage) because that is the semantic key; status alone because the
    # recovery sweep and the "what is running" view both scan it.
    op.create_index("ix_stage_executions_run_id", "stage_executions", ["run_id"])
    op.create_index("ix_stage_executions_run_id_stage", "stage_executions", ["run_id", "stage"])
    op.create_index("ix_stage_executions_status", "stage_executions", ["status"])
    op.create_index("ix_stage_executions_correlation_id", "stage_executions", ["correlation_id"])
    # Recovery sweep: "find rows stuck in RUNNING past their lease".
    op.create_index(
        "ix_stage_executions_status_started_at", "stage_executions", ["status", "started_at"]
    )

    # THE idempotency guarantee: at most one non-terminal row per (run_id, stage).
    op.create_index(
        "uq_stage_executions_semantic_active",
        "stage_executions",
        ["run_id", "stage"],
        unique=True,
        postgresql_where=sa.text(f"status IN {_NON_TERMINAL}"),
    )


def downgrade() -> None:
    # The partial index first: it is a constraint-like object and leaving it
    # behind would block the DROP TABLE.
    op.drop_index("uq_stage_executions_semantic_active", table_name="stage_executions")
    op.drop_index("ix_stage_executions_status_started_at", table_name="stage_executions")
    op.drop_index("ix_stage_executions_correlation_id", table_name="stage_executions")
    op.drop_index("ix_stage_executions_status", table_name="stage_executions")
    op.drop_index("ix_stage_executions_run_id_stage", table_name="stage_executions")
    op.drop_index("ix_stage_executions_run_id", table_name="stage_executions")
    op.drop_table("stage_executions")


# the state machine grows a status, this index is reviewed at the same time.
_NON_TERMINAL = "('PENDING', 'RUNNING', 'RETRYABLE')"
