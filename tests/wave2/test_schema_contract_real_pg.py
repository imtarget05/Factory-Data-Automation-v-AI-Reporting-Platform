"""Remaining W2-2 exit evidence: schema uniqueness, downgrade, roundtrip.

M1-M4 and the historical-precedence cases (B4/B5) are already covered in
`test_migrations_real_pg.py`. What is still unproven is whether the migrated
schema actually ENFORCES the semantic rule, and whether the downgrade is
honest about what it cannot preserve.

Both need a real PostgreSQL. `test_migrations_real_pg.py` already establishes
that convention; this module follows it rather than inventing a second one.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, text

ADMIN_URL = os.getenv("FACTORY_TEST_PG_ADMIN_URL")
if not ADMIN_URL:
    raise RuntimeError(
        "FACTORY_TEST_PG_ADMIN_URL is not set. These proofs require a REAL "
        "PostgreSQL server. Refusing to report green without a database."
    )

from tests.wave2.migration_harness import (  # noqa: E402
    database_url_for,
    downgrade_to,
    drop_database,
    make_database,
    upgrade_to,
)

PRE_SPLIT = "b2c1d0e4a7f9"  # 0002, before the semantic/attempt split
HEAD = "d4e7b1c90a52"  # 0003


@pytest.fixture
def db_url():
    name = f"factory_close_{uuid.uuid4().hex[:8]}"
    make_database(ADMIN_URL, name)
    url = database_url_for(ADMIN_URL, name)
    try:
        yield url
    finally:
        drop_database(ADMIN_URL, name)


def _exec(url: str, sql: str) -> None:
    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        conn.execute(text(sql))
    engine.dispose()


def _scalar(url: str, sql: str):
    engine = create_engine(url, future=True)
    with engine.connect() as conn:
        value = conn.execute(text(sql)).scalar()
    engine.dispose()
    return value


# ── the semantic uniqueness is structural, not conventional ────────────────


def test_semantic_key_rejects_a_second_row_for_the_same_work(db_url):
    """uq_stage_executions_semantic must be a real constraint.

    Read the schema and you learn what was INTENDED. Try the insert and you
    learn what is ENFORCED. Only the second one is worth asserting: an index
    that exists in a migration but not in the database produces a pipeline that
    believes it is idempotent right up until two workers run at once.
    """
    upgrade_to(db_url, HEAD)

    _exec(
        db_url,
        """
        INSERT INTO stage_executions
            (run_id, stage, status, attempt_count, created_at, updated_at)
        VALUES ('run-x', 'GOLD', 'RUNNING', 1, now(), now())
        """,
    )

    with pytest.raises(Exception, match="uq_stage_executions_semantic"):
        _exec(
            db_url,
            """
            INSERT INTO stage_executions
                (run_id, stage, status, attempt_count, created_at, updated_at)
            VALUES ('run-x', 'GOLD', 'RUNNING', 1, now(), now())
            """,
        )

    assert _scalar(db_url, "SELECT count(*) FROM stage_executions WHERE run_id = 'run-x'") == 1


def test_different_stage_of_the_same_run_is_not_a_duplicate(db_url):
    """The constraint is (run_id, stage), not run_id alone.

    Over-tightening here would be just as broken as leaving it out: a run has
    several stages, and they must be able to proceed independently.
    """
    upgrade_to(db_url, HEAD)

    _exec(
        db_url,
        """
        INSERT INTO stage_executions
            (run_id, stage, status, attempt_count, created_at, updated_at)
        VALUES
            ('run-y', 'GOLD',  'RUNNING', 1, now(), now()),
            ('run-y', 'SILVER','RUNNING', 1, now(), now())
        """,
    )

    assert _scalar(db_url, "SELECT count(*) FROM stage_executions WHERE run_id = 'run-y'") == 2


def test_attempt_identity_is_unique_per_run_stage_attempt(db_url):
    """The audit table must refuse to fold two attempts into one number.

    If it could, retry history would silently lose entries and the count on the
    semantic row would be counting something that does not exist.
    """
    upgrade_to(db_url, HEAD)

    _exec(
        db_url,
        """
        INSERT INTO stage_attempts
            (run_id, stage, attempt, status, created_at, updated_at)
        VALUES ('run-z', 'GOLD', 1, 'RUNNING', now(), now())
        """,
    )
    with pytest.raises(Exception, match="uq_stage_attempts_run_stage_attempt"):
        _exec(
            db_url,
            """
            INSERT INTO stage_attempts
                (run_id, stage, attempt, status, created_at, updated_at)
            VALUES ('run-z', 'GOLD', 1, 'RUNNING', now(), now())
            """,
        )


def test_succeeded_semantic_row_must_carry_a_completion_time(db_url):
    """ck_stage_executions_succeeded_final encodes "success is a fact, not a hope".

    A SUCCEEDED row with no timestamp cannot be audited: there is no way to say
    when the work finished or to build a freshness SLI on it.
    """
    upgrade_to(db_url, HEAD)

    with pytest.raises(Exception, match="ck_stage_executions_succeeded_final"):
        _exec(
            db_url,
            """
            INSERT INTO stage_executions
                (run_id, stage, status, attempt_count, succeeded_at, created_at, updated_at)
            VALUES ('run-w', 'GOLD', 'SUCCEEDED', 1, NULL, now(), now())
            """,
        )


# ── downgrade: honest about what it cannot preserve ───────────────────────


def test_downgrade_restores_the_pre_split_shape_and_keeps_attempts(db_url):
    """Downgrading to 0002 must return the ACTUAL 0002 structure, from evidence.

    0002 had one table holding every attempt. 0003 split that into semantic
    state plus attempt history, so the downgrade has to rebuild the single
    table from the attempts rather than collapsing the semantic rows, which
    would throw away the history this whole migration exists to preserve.

    Exit code 0 is not the test. The shape and the row count are.
    """
    upgrade_to(db_url, HEAD)
    _exec(
        db_url,
        """
        INSERT INTO stage_attempts
            (run_id, stage, attempt, status, completed_at, created_at, updated_at)
        VALUES
            ('run-d', 'GOLD', 1, 'RETRYABLE', now(), now(), now()),
            ('run-d', 'GOLD', 2, 'SUCCEEDED',  now(), now(), now())
        """,
    )
    _exec(
        db_url,
        """
        INSERT INTO stage_executions
            (run_id, stage, status, attempt_count, succeeded_at, created_at, updated_at)
        VALUES ('run-d', 'GOLD', 'SUCCEEDED', 2, now(), now(), now())
        """,
    )

    downgrade_to(db_url, PRE_SPLIT)

    # The split table is gone. The single pre-split table is back under its
    # original name: 0003 renames the fresh table to stage_executions only at
    # the END of the downgrade, so stage_executions is the name to assert, not
    # the temporary legacy one.
    assert (
        _scalar(
            db_url,
            "SELECT count(*) FROM information_schema.tables WHERE table_name = 'stage_attempts'",
        )
        == 0
    )
    assert (
        _scalar(
            db_url,
            "SELECT count(*) FROM information_schema.tables WHERE table_name = 'stage_executions'",
        )
        == 1
    )
    assert (
        _scalar(
            db_url,
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name = 'stage_executions_legacy'",
        )
        == 0
    )

    # Both attempts survived. Collapsing to one row would lose the evidence of
    # the failure that caused the retry.
    assert _scalar(db_url, "SELECT count(*) FROM stage_executions WHERE run_id = 'run-d'") == 2
    assert (
        _scalar(
            db_url,
            "SELECT count(*) FROM stage_executions WHERE run_id = 'run-d' "
            "AND attempt = 2 AND status = 'SUCCEEDED'",
        )
        == 1
    )


def test_roundtrip_returns_to_head_without_losing_semantics(db_url):
    """downgrade then upgrade must be a round trip, not a one-way door.

    Stronger than checking the downgrade's exit code: it proves the forward
    migration still works on a database that has been through the inverse, which
    is where index-carrying renames and leftover constraints normally break.
    """
    upgrade_to(db_url, HEAD)
    _exec(
        db_url,
        """
        INSERT INTO stage_attempts
            (run_id, stage, attempt, status, completed_at, created_at, updated_at)
        VALUES ('run-r', 'GOLD', 1, 'SUCCEEDED', now(), now(), now())
        """,
    )
    _exec(
        db_url,
        """
        INSERT INTO stage_executions
            (run_id, stage, status, attempt_count, succeeded_at, created_at, updated_at)
        VALUES ('run-r', 'GOLD', 'SUCCEEDED', 1, now(), now(), now())
        """,
    )

    downgrade_to(db_url, PRE_SPLIT)
    upgrade_to(db_url, HEAD)

    assert (
        _scalar(
            db_url,
            "SELECT count(*) FROM stage_attempts WHERE run_id = 'run-r' AND attempt = 1",
        )
        == 1
    )
    assert (
        _scalar(
            db_url,
            "SELECT status FROM stage_executions WHERE run_id = 'run-r' AND stage = 'GOLD'",
        )
        == "SUCCEEDED"
    )
    assert (
        _scalar(
            db_url,
            "SELECT attempt_count FROM stage_executions WHERE run_id = 'run-r' AND stage = 'GOLD'",
        )
        == 1
    )


def test_sticky_success_survives_a_full_roundtrip(db_url):
    """The precedence rule must hold on data that has been downgraded and back.

    A SUCCEEDED attempt must still produce a SUCCEEDED semantic row after the
    round trip. If the downgrade rebuilds attempts in a way the forward
    migration reads differently, this is where it shows up.
    """
    upgrade_to(db_url, HEAD)
    _exec(
        db_url,
        """
        INSERT INTO stage_attempts
            (run_id, stage, attempt, status, completed_at, created_at, updated_at)
        VALUES
            ('run-s', 'GOLD', 1, 'SUCCEEDED', now(), now(), now()),
            ('run-s', 'GOLD', 2, 'FAILED',    now(), now(), now())
        """,
    )
    _exec(
        db_url,
        """
        INSERT INTO stage_executions
            (run_id, stage, status, attempt_count, succeeded_at, created_at, updated_at)
        VALUES ('run-s', 'GOLD', 'SUCCEEDED', 2, now(), now(), now())
        """,
    )

    downgrade_to(db_url, PRE_SPLIT)
    upgrade_to(db_url, HEAD)

    assert (
        _scalar(
            db_url,
            "SELECT status FROM stage_executions WHERE run_id = 'run-s' AND stage = 'GOLD'",
        )
        == "SUCCEEDED"
    ), "a later FAILED attempt must not erase an earlier SUCCEEDED"
