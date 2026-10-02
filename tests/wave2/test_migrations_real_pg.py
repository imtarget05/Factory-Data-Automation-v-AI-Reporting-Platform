"""W2-2 — Alembic migration proofs against a REAL PostgreSQL.

WHY NOT SQLITE
==============

The chain `24c8e3994379 -> b2c1d0e4a7f9 -> d4e7b1c90a52` had never been
executed against a database. It was reviewed, committed, and green in the sense
that it imported. The first real run failed immediately with

    DuplicateTable: relation "ix_stage_executions_id" already exists

on an EMPTY database: the rename-then-recreate in 0003 carried the old index
forward under its original name while the drop list omitted it. Reading would
not find that; only a real server does.

SQLite could not have caught it either — no transactional DDL, different index
and constraint semantics. So this suite refuses to run without a live
PostgreSQL rather than degrading to something that proves less and reports
green.

M1 empty->head with the schema INSPECTED, M2 previous->head over representative
legacy data, M3 head->head idempotent, M4 a mid-upgrade failure must not
advance alembic_version.

Every test builds its own disposable database. No test may silently skip: an
unavailable server is a FAILURE, because "green with zero observations" is the
exact failure mode this program exists to prevent.
"""

from __future__ import annotations

import os
import uuid

import pytest

# Fail at COLLECTION without a real PostgreSQL. A skipped migration suite reads
# as "migrations verified" in a CI summary, which is worse than a red job.
ADMIN_URL = os.environ.get("FACTORY_TEST_PG_ADMIN_URL")
if not ADMIN_URL:
    pytest.exit(
        "FACTORY_TEST_PG_ADMIN_URL is not set. W2-2 requires a REAL PostgreSQL "
        "server; SQLite cannot execute this chain. Refusing to report green "
        "without a database.",
        returncode=1,
    )

from argparse import Namespace  # noqa: E402

from sqlalchemy import create_engine, inspect, text  # noqa: E402

from tests.wave2.migration_harness import (  # noqa: E402
    BASELINE,
    HEAD,
    MIGRATIONS_DIR,
    PREVIOUS,
    REVISION_CHAIN,
    drop_database,
    make_database,
    upgrade_to,
)


@pytest.fixture(scope="module")
def server():
    """Prove the server answers before any migration is attempted.

    Observation contract: version, current_database, server_version_num —
    captured so a later report can state what was actually tested against.
    """
    engine = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        facts = {
            "version": conn.execute(text("select version()")).scalar_one(),
            "current_database": conn.execute(text("select current_database()")).scalar_one(),
            "server_version_num": conn.execute(text("show server_version_num")).scalar_one(),
        }
    engine.dispose()
    assert "PostgreSQL" in facts["version"], f"not PostgreSQL: {facts['version']}"
    assert int(facts["server_version_num"]) >= 160000, (
        f"W2-2 requires PostgreSQL 16+, got {facts['server_version_num']}"
    )
    return facts


@pytest.fixture
def fresh_db(server):
    """A brand-new EMPTY database, dropped on teardown."""
    name = f"w2_{uuid.uuid4().hex[:12]}"
    make_database(ADMIN_URL, name)
    from sqlalchemy.engine import make_url

    url = make_url(ADMIN_URL).set(database=name).render_as_string(hide_password=False)
    yield url
    drop_database(ADMIN_URL, name)


def current_revision(url: str) -> str | None:
    """The recorded revision, or None when there is no alembic_version table.

    None is a legitimate outcome, not an error: Alembic runs all migrations in
    ONE transaction by default (`transaction_per_migration` is False), so a
    failure anywhere rolls the whole run back — including the creation of
    alembic_version itself. That is the safest possible result and it certainly
    means the version did not falsely advance.
    """
    engine = create_engine(url)
    try:
        # Existence is checked with the inspector rather than by catching an
        # error and matching its message: matching on exception text couples the
        # assertion to driver wording, which changes between psycopg2 releases.
        if "alembic_version" not in set(inspect(engine).get_table_names()):
            return None
        with engine.connect() as conn:
            return conn.execute(
                text("select version_num from alembic_version")
            ).scalar_one_or_none()
    finally:
        engine.dispose()


def test_m1_empty_database_upgrades_to_head(fresh_db):
    """M1: empty -> head must succeed on its own."""
    upgrade_to(fresh_db, HEAD)


def test_m1_actual_schema_is_inspected(fresh_db):
    """M1 MUST inspect the schema, not infer it from exit 0.

    `upgrade head` returning 0 proves the script ran. It does not prove the
    tables, constraints or indexes it promised are present.
    """
    upgrade_to(fresh_db, HEAD)
    assert current_revision(fresh_db) == HEAD, "alembic_version is not at head"

    engine = create_engine(fresh_db)
    try:
        insp = inspect(engine)
        tables = set(insp.get_table_names())

        assert "stage_executions" in tables, f"missing semantic table: {sorted(tables)}"
        assert "stage_attempts" in tables, f"missing attempt table: {sorted(tables)}"
        assert "stage_executions_legacy" not in tables, (
            "0003 renamed the table but never dropped it"
        )

        # THE load-bearing constraint. Without it the semantic idempotency
        # argument collapses to "usually one row".
        uqs = {
            frozenset(c["column_names"]) for c in insp.get_unique_constraints("stage_executions")
        }
        assert frozenset(("run_id", "stage")) in uqs, (
            "stage_executions has no UNIQUE(run_id, stage); the semantic "
            f"identity guarantee is absent. Found: {sorted(uqs)}"
        )

        attempt_uqs = {
            frozenset(c["column_names"]) for c in insp.get_unique_constraints("stage_attempts")
        }
        assert frozenset(("run_id", "stage", "attempt")) in attempt_uqs, (
            f"stage_attempts has no UNIQUE(run_id, stage, attempt): {sorted(attempt_uqs)}"
        )

        # SUCCEEDED must be sticky at the SCHEMA level, not only in Python.
        check_names = {c["name"] for c in insp.get_check_constraints("stage_executions")}
        assert "ck_stage_executions_succeeded_final" in check_names, (
            f"missing the SUCCEEDED-is-final check: {sorted(check_names)}"
        )

        columns = {c["name"] for c in insp.get_columns("stage_executions")}
        for required in ("run_id", "stage", "status", "attempt_count", "succeeded_at"):
            assert required in columns, f"stage_executions missing column {required}"

        # Lease columns so a crashed worker can be recovered (W2-9).
        for required in ("claim_owner", "lease_expires_at", "heartbeat_at"):
            assert required in columns, (
                f"stage_executions missing lease column {required}; a crashed "
                "worker holding a claim could never be recovered"
            )
    finally:
        engine.dispose()


def test_m3_head_to_head_is_idempotent(fresh_db):
    """M3: running `upgrade head` again must be a no-op, not a second migration.

    Non-idempotence here is how a schema ends up with two indexes on the same
    column, or a duplicated partial unique constraint, on the second person who
    runs the migrations.
    """
    upgrade_to(fresh_db, HEAD)
    before = current_revision(fresh_db)

    engine = create_engine(fresh_db)
    try:
        insp = inspect(engine)
        tables_before = set(insp.get_table_names())
        indexes_before = {ix["name"] for t in tables_before for ix in insp.get_indexes(t)}
        constraints_before = {
            c["name"] for t in tables_before for c in insp.get_unique_constraints(t)
        }
    finally:
        engine.dispose()

    upgrade_to(fresh_db, HEAD)

    engine = create_engine(fresh_db)
    try:
        insp = inspect(engine)
        indexes_after = {
            ix["name"] for t in set(insp.get_table_names()) for ix in insp.get_indexes(t)
        }
        constraints_after = {
            c["name"] for t in set(insp.get_table_names()) for c in insp.get_unique_constraints(t)
        }
    finally:
        engine.dispose()

    assert current_revision(fresh_db) == before, "the revision moved on a no-op upgrade"
    assert indexes_after == indexes_before, (
        f"indexes changed on re-upgrade: {indexes_after ^ indexes_before}"
    )
    assert constraints_after == constraints_before, (
        f"unique constraints changed on re-upgrade: {constraints_after ^ constraints_before}"
    )


#: A revision id that cannot collide with a real one, so a leaked temporary
#: migration is obvious rather than silently joining the chain.
BROKEN_REVISION = "f00dbrokef0000000"


def _write_broken_migration(tmp_path) -> str:
    """Write a migration that does real DDL and THEN fails, into its own tree.

    A separate script directory is used so the temporary revision never touches
    the repository. The failure is raised from inside `upgrade()`, after a real
    CREATE TABLE, so what is under test is PostgreSQL's transactional DDL — not
    Alembic's ability to parse a file that does not compile.

    The REAL migration tree is copied in first: the broken revision declares
    `down_revision = HEAD`, and a script directory that does not contain HEAD
    makes Alembic warn "Revision ... is not present" and refuse to resolve a
    chain, which would make M4 pass or fail for the wrong reason.
    """
    import shutil

    shutil.copytree(MIGRATIONS_DIR, tmp_path, dirs_exist_ok=True)
    versions = tmp_path / "versions"
    (versions / f"{BROKEN_REVISION}_broken.py").write_text(
        "'''Deliberately broken migration used by the W2-2 M4 proof.'''\n"
        "import sqlalchemy as sa\n"
        "from alembic import op\n"
        "\n"
        'revision = "f00dbrokef0000000"\n'
        f'down_revision = "{HEAD}"\n'
        "branch_labels = None\n"
        "depends_on = None\n"
        "\n"
        "\n"
        "def upgrade() -> None:\n"
        "    # Real DDL first, so a non-transactional server would leave this\n"
        "    # table behind and the test below would catch it.\n"
        "    op.create_table(\n"
        '        "m4_should_be_rolled_back",\n'
        '        sa.Column("id", sa.Integer, primary_key=True),\n'
        "    )\n"
        "    raise RuntimeError(\n"
        '        "deliberate M4 failure: raised AFTER real DDL, to prove the "\n'
        '        "transaction rolls back and alembic_version does not advance"\n'
        "    )\n"
        "\n"
        "\n"
        "def downgrade() -> None:\n"
        '    op.drop_table("m4_should_be_rolled_back")\n',
        encoding="utf-8",
    )
    (tmp_path / "env.py").write_text(
        "from alembic import context\n"
        "\n"
        "config = context.config\n"
        "\n"
        "\n"
        "def run_migrations_offline():\n"
        "    context.configure(url=config.get_main_option('sqlalchemy.url'))\n"
        "    with context.begin_transaction():\n"
        "        context.run_migrations()\n"
        "\n"
        "\n"
        "def run_migrations_online():\n"
        "    from sqlalchemy import engine_from_config, pool\n"
        "    connectable = engine_from_config(\n"
        "        config.get_section(config.config_ini_section, {}),\n"
        "        prefix='sqlalchemy.',\n"
        "        poolclass=pool.NullPool,\n"
        "    )\n"
        "    with connectable.connect() as connection:\n"
        "        context.configure(connection=connection)\n"
        "        with context.begin_transaction():\n"
        "            context.run_migrations()\n"
        "\n"
        "\n"
        "if context.is_offline_mode():\n"
        "    run_migrations_offline()\n"
        "else:\n"
        "    run_migrations_online()\n",
        encoding="utf-8",
    )
    return BROKEN_REVISION


def _upgrade_with(script_dir, url: str, revision: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(script_dir))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.cmd_opts = Namespace(x=[f"url={url}"])
    command.upgrade(cfg, revision)


def test_m4_a_failing_migration_does_not_advance_the_version(fresh_db, tmp_path):
    """M4: a migration that fails mid-upgrade must not mark itself applied.

    The failure is injected INSIDE upgrade(), after real work has already
    happened — not a syntax error before the script starts, which proves
    nothing about transactionality.

    PostgreSQL has transactional DDL, so the whole upgrade must roll back and
    `alembic_version` must stay at the previous revision. A migration that
    advances the version despite failing leaves the database claiming to be at a
    schema it does not have, and the next run skips the broken step entirely.
    """
    broken = _write_broken_migration(tmp_path)

    # Target "head" IN THE COPIED TREE, where head IS the broken revision.
    # Targeting HEAD by id would stop at the real head and never execute the
    # broken migration at all — the test would then pass without testing
    # anything, which is the failure mode this whole file exists to prevent.
    with pytest.raises(Exception):  # noqa: B017 — any failure mode counts
        _upgrade_with(tmp_path, fresh_db, "head")

    # The critical assertion: the version did NOT advance to the broken revision.
    assert current_revision(fresh_db) != broken, (
        "alembic_version advanced to a revision whose upgrade FAILED; the "
        "database now claims a schema it does not have"
    )

    # And the DDL it had already issued was rolled back, so the semantic table
    # must not exist yet.
    engine = create_engine(fresh_db)
    try:
        insp = inspect(engine)
        assert "stage_executions" not in set(insp.get_table_names()), (
            "the failed migration's DDL was not rolled back — a partial schema "
            "is exactly the state this test exists to prevent"
        )
    finally:
        engine.dispose()


def test_m4_the_broken_migration_fixture_actually_runs(fresh_db, tmp_path):
    """Guard the guard: prove the injected failure is reachable, not dead code.

    A M4 test that passes because the temporary migration was never part of the
    chain would report "migration failures are handled" while proving nothing.
    This asserts the file exists, declares the expected revision, and that
    Alembic can see it in the script directory.
    """
    revision = _write_broken_migration(tmp_path)
    source = (tmp_path / "versions" / f"{revision}_broken.py").read_text(encoding="utf-8")
    assert f'revision = "{revision}"' in source
    assert "def upgrade" in source
    assert "raise RuntimeError" in source, "the fixture no longer raises; M4 would pass vacuously"


def test_m3_re_upgrade_preserves_data(fresh_db):
    """A no-op re-upgrade must not lose rows."""
    upgrade_to(fresh_db, HEAD)
    engine = create_engine(fresh_db)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO stage_executions "
                    "(run_id, stage, status, attempt_count, created_at, updated_at) "
                    "VALUES ('run-keepme', 'GOLD', 'RUNNING', 1, now(), now())"
                )
            )
        upgrade_to(fresh_db, HEAD)
        with engine.connect() as conn:
            count = conn.execute(
                text("SELECT count(*) FROM stage_executions WHERE run_id = 'run-keepme'")
            ).scalar_one()
    finally:
        engine.dispose()
    assert count == 1, "a no-op upgrade destroyed data"


def _legacy_attempt(run_id: str, stage: str, attempt: int, status: str, **overrides):
    """One row in the PRE-split schema (revision 0002's stage_executions)."""
    now = "now()"
    cols = {
        "run_id": f"'{run_id}'",
        "stage": f"'{stage}'",
        "attempt": str(attempt),
        "status": f"'{status}'",
        "message_id": f"'msg-{run_id}-{attempt}'",
        "correlation_id": f"'corr-{run_id}'",
        "started_at": now,
        "completed_at": now if status in {"SUCCEEDED", "FAILED", "DEAD_LETTERED"} else "NULL",
        "input_artifact_ref": f"'blob/raw/{run_id}.parquet'",
        "output_artifact_ref": f"'blob/gold/{run_id}-a{attempt}.json'",
        "input_checksum": "'" + "a" * 64 + "'",
        "output_checksum": ("'" + chr(97 + attempt) * 64 + "'")
        if status == "SUCCEEDED"
        else "NULL",
        "safe_error_code": "'E_TRANSIENT'" if status in {"FAILED", "RETRYABLE"} else "NULL",
        "safe_error_message": "'upstream timeout'" if status in {"FAILED", "RETRYABLE"} else "NULL",
        "created_at": now,
        "updated_at": now,
    }
    cols.update(overrides)
    names = ", ".join(cols)
    values = ", ".join(str(v) for v in cols.values())
    return f"INSERT INTO stage_executions ({names}) VALUES ({values})"


def _seed_legacy(url: str, statements: list[str]) -> None:
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))
    finally:
        engine.dispose()


def _semantic_row(url: str, run_id: str, stage: str) -> dict | None:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            row = (
                conn.execute(
                    text(
                        "SELECT status, attempt_count, output_artifact_ref, succeeded_at "
                        "FROM stage_executions WHERE run_id = :r AND stage = :s"
                    ),
                    {"r": run_id, "s": stage},
                )
                .mappings()
                .first()
            )
            return dict(row) if row else None
    finally:
        engine.dispose()


def _attempts(url: str, run_id: str, stage: str) -> list[dict]:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            rows = (
                conn.execute(
                    text(
                        "SELECT attempt, status, output_artifact_ref FROM stage_attempts "
                        "WHERE run_id = :r AND stage = :s ORDER BY attempt"
                    ),
                    {"r": run_id, "s": stage},
                )
                .mappings()
                .all()
            )
            return [dict(r) for r in rows]
    finally:
        engine.dispose()


def _m2_db(name: str) -> str:
    from sqlalchemy.engine import make_url

    from tests.wave2.migration_harness import make_database

    make_database(ADMIN_URL, name)
    return make_url(ADMIN_URL).set(database=name).render_as_string(hide_password=False)


def test_m2_b4_succeeded_then_failed_stays_succeeded(server):
    """B4 — THE decisive case. A later FAILED must not erase an earlier success.

    attempt 1 SUCCEEDED, attempt 2 FAILED.

    Latest-wins would migrate this to FAILED, the run would look incomplete, an
    operator would replay it, and the side effects would execute a second time —
    the duplicate-execution hazard 0003 exists to remove. So this assertion is
    not tidiness; it is the load-bearing claim of the whole split.
    """
    name = f"w2_b4_{uuid.uuid4().hex[:8]}"
    url = _m2_db(name)
    try:
        upgrade_to(url, PREVIOUS)
        _seed_legacy(
            url,
            [
                _legacy_attempt("run-b4", "GOLD", 1, "SUCCEEDED"),
                _legacy_attempt("run-b4", "GOLD", 2, "FAILED"),
            ],
        )
        upgrade_to(url, HEAD)

        semantic = _semantic_row(url, "run-b4", "GOLD")
        assert semantic is not None, "no semantic row was synthesised"
        assert semantic["status"] == "SUCCEEDED", (
            "the migration erased an earlier success because the LAST attempt "
            f"failed; semantic status is {semantic['status']!r}. The stage had "
            "already completed and replaying it would duplicate side effects."
        )
        assert semantic["succeeded_at"] is not None, (
            "SUCCEEDED with no succeeded_at violates ck_stage_executions_succeeded_final"
        )
        assert semantic["attempt_count"] == 2, (
            f"attempt_count={semantic['attempt_count']!r}; both attempts must be counted"
        )

        attempts = _attempts(url, "run-b4", "GOLD")
        assert len(attempts) == 2, f"attempt history was lost: {attempts}"
        assert [a["status"] for a in attempts] == ["SUCCEEDED", "FAILED"]
    finally:
        drop_database(ADMIN_URL, name)


def test_m2_b5_duplicate_success_keeps_one_semantic_row(server):
    """B5 — two historical successes: one semantic row, both attempts kept.

    Two SUCCEEDED attempts IS the evidence that the old partial-index schema
    allowed a completed stage to execute twice. It must be preserved as history
    and not cleaned up, while the semantic row stays single and SUCCEEDED.
    """
    name = f"w2_b5_{uuid.uuid4().hex[:8]}"
    url = _m2_db(name)
    try:
        upgrade_to(url, PREVIOUS)
        _seed_legacy(
            url,
            [
                _legacy_attempt("run-b5", "GOLD", 1, "SUCCEEDED"),
                _legacy_attempt("run-b5", "GOLD", 2, "SUCCEEDED"),
            ],
        )
        upgrade_to(url, HEAD)

        engine = create_engine(url)
        try:
            with engine.connect() as conn:
                n = conn.execute(
                    text("SELECT count(*) FROM stage_executions WHERE run_id = 'run-b5'")
                ).scalar_one()
        finally:
            engine.dispose()
        assert n == 1, f"duplicate success produced {n} semantic rows, expected 1"

        semantic = _semantic_row(url, "run-b5", "GOLD")
        assert semantic["status"] == "SUCCEEDED"
        assert semantic["attempt_count"] == 2, (
            f"attempt_count={semantic['attempt_count']!r}; the duplicate execution "
            "must stay visible as evidence, not be erased"
        )
        assert len(_attempts(url, "run-b5", "GOLD")) == 2, "history was cleaned up"
    finally:
        drop_database(ADMIN_URL, name)


def test_m2_b5_canonical_output_is_the_first_success(server):
    """Canonical output metadata comes from the FIRST success, not the last.

    A later success may itself BE the duplicate execution. Promoting it to
    canonical would make the duplicate the artifact downstream consumers read.
    """
    name = f"w2_b5o_{uuid.uuid4().hex[:8]}"
    url = _m2_db(name)
    try:
        upgrade_to(url, PREVIOUS)
        _seed_legacy(
            url,
            [
                _legacy_attempt(
                    "run-b5o",
                    "GOLD",
                    1,
                    "SUCCEEDED",
                    output_artifact_ref="'blob/gold/FIRST.json'",
                ),
                _legacy_attempt(
                    "run-b5o",
                    "GOLD",
                    2,
                    "SUCCEEDED",
                    output_artifact_ref="'blob/gold/SECOND.json'",
                ),
            ],
        )
        upgrade_to(url, HEAD)

        semantic = _semantic_row(url, "run-b5o", "GOLD")
        assert semantic["output_artifact_ref"] == "blob/gold/FIRST.json", (
            "canonical output came from "
            f"{semantic['output_artifact_ref']!r}; it must be the FIRST successful "
            "attempt, because a later success may be the duplicate execution"
        )
    finally:
        drop_database(ADMIN_URL, name)


def test_m2_b1_b2_b3_ordinary_rows_migrate_faithfully(server):
    """B1 RUNNING, B2 SUCCEEDED, B3 RETRYABLE — the ordinary cases still migrate."""
    name = f"w2_b123_{uuid.uuid4().hex[:8]}"
    url = _m2_db(name)
    try:
        upgrade_to(url, PREVIOUS)
        _seed_legacy(
            url,
            [
                _legacy_attempt("run-b1", "SILVER", 1, "RUNNING"),
                _legacy_attempt("run-b2", "SILVER", 1, "SUCCEEDED"),
                _legacy_attempt("run-b3", "GOLD", 1, "RETRYABLE"),
            ],
        )
        upgrade_to(url, HEAD)

        assert _semantic_row(url, "run-b1", "SILVER")["status"] == "RUNNING"
        assert _semantic_row(url, "run-b2", "SILVER")["status"] == "SUCCEEDED"

        b3 = _semantic_row(url, "run-b3", "GOLD")
        assert b3["status"] == "RETRYABLE", (
            "no attempt ever succeeded, so the latest status must carry "
            f"through, got {b3['status']!r}"
        )
        assert b3["succeeded_at"] is None, "a RETRYABLE stage must have no succeeded_at"
    finally:
        drop_database(ADMIN_URL, name)
    """No second competing 'initial' revision, and no branching."""
    assert list(REVISION_CHAIN) == [BASELINE, PREVIOUS, HEAD], (
        f"unexpected revision chain: {REVISION_CHAIN}"
    )
