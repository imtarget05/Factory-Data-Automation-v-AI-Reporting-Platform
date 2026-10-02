"""Shared helpers for the W2-2 real-PostgreSQL migration proofs.

Deliberately thin. Every function here is something that would be WRONG to
reimplement per test: the revision chain is read from the migration source
rather than hardcoded, so a new revision cannot leave the tests asserting
against a stale head.

The revision constants are read by parsing `migrations/versions/*.py` for the
`revision` / `down_revision` literals. That keeps the tests honest about what the
repository actually contains — if someone renames a revision, the tests follow
and then FAIL on behaviour, not on a name mismatch.
"""

from __future__ import annotations

import re
from argparse import Namespace
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / "migrations"
VERSIONS_DIR = MIGRATIONS_DIR / "versions"


def _read_chain() -> dict[str, str | None]:
    """revision -> down_revision, parsed from the migration source."""
    chain: dict[str, str | None] = {}
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        rev = re.search(r'^revision\s*=\s*["\']([^"\']+)["\']', source, re.M)
        down = re.search(r'^down_revision\s*=\s*["\']([^"\']+)["\']', source, re.M)
        if rev:
            chain[rev.group(1)] = down.group(1) if down else None
    return chain


_REVISIONS = _read_chain()
ROOT = next(r for r, d in _REVISIONS.items() if d is None)
HEAD = next(r for r in _REVISIONS if r not in set(_REVISIONS.values()))


#: Linearise the chain from root to head.
def _linear() -> list[str]:
    ordered = [ROOT]
    while True:
        children = [r for r, d in _REVISIONS.items() if d == ordered[-1]]
        if not children:
            break
        if len(children) > 1:
            raise RuntimeError(f"branching migration chain at {ordered[-1]}: {children}")
        ordered.append(children[0])
    return ordered


REVISION_CHAIN: list[str] = _linear()

BASELINE: str = REVISION_CHAIN[0]
PREVIOUS: str = REVISION_CHAIN[-2]
HEAD: str = REVISION_CHAIN[-1]


def alembic_config(url: str) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    # env.py reads `-x url=...` first and only then DATABASE_URL. Passing it
    # explicitly means a stray DATABASE_URL in the ambient environment cannot
    # silently redirect a migration at a different database than the test made.
    #
    # `cmd_opts` must be a Namespace carrying `.x`, NOT a plain list: env.py
    # calls `context.get_x_argument()`, which reads `config.cmd_opts.x`.
    cfg.cmd_opts = Namespace(x=[f"url={url}"])
    return cfg


def alembic_command(url: str, *args: str) -> None:
    command.upgrade(alembic_config(url), *args) if args[0] == "upgrade" else command.downgrade(
        alembic_config(url), *args
    )


def upgrade_to(url: str, revision: str) -> None:
    command.upgrade(alembic_config(url), revision)


def downgrade_to(url: str, revision: str) -> None:
    command.downgrade(alembic_config(url), revision)


def make_database(admin_url: str, name: str) -> None:
    """CREATE DATABASE. Cannot run inside a transaction block."""
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    engine.dispose()


def drop_database(admin_url: str, name: str) -> None:
    """Best-effort teardown. A leftover scratch database is noise, not a failure."""
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :n AND pid <> pg_backend_pid()"
                ),
                {"n": name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
    except Exception:  # noqa: BLE001 — teardown must not mask a real failure
        pass
    finally:
        engine.dispose()


def database_url_for(admin_url: str, name: str) -> str:
    return make_url(admin_url).set(database=name).render_as_string(hide_password=False)
