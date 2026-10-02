"""Alembic environment.

Three things this file is careful about:

1. **THE URL IS NOT HERE.** It comes from the application's own configuration, so
   a migration can never be pointed at a different database than the running
   app. It is resolved once, at import time, and it is visible in the log line
   Alembic prints -- with the password redacted, because the error path that
   prints it is exactly the path where it lands in a CI log.

2. **OFFLINE AND ONLINE BOTH WORK.** Offline mode (`--sql`) is how a DBA reviews
   a migration before it runs. Supporting only online mode means nobody can
   inspect the DDL without a live database.

3. **AUTOGENERATE IS NEVER TRUSTED BLINDLY.** `target_metadata` is set so
   `alembic revision --autogenerate` works, but autogenerate cannot see data
   migrations, and it silently misses things a CHECK constraint should encode.
   Those are written by hand on purpose.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make the application importable when Alembic is invoked from the repo root.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.database.models import Base  # noqa: E402  (needs sys.path first)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    """Resolve the database URL from the environment, never from a committed file.

    Priority is deliberate: an explicit migration-time override wins, then the
    application's own ``DATABASE_URL``, then nothing -- because silently falling
    back to a default is how a migration ends up running against the wrong
    database.

    Alembic-specific override is ``-x url=...`` rather than a config-file edit,
    which is what makes the override visible in the command line of a runbook.
    """
    override = context.get_x_argument(as_dictionary=True).get("url")
    if override:
        return override
    from_env = os.getenv("DATABASE_URL")
    if from_env:
        return from_env
    raise RuntimeError(
        "No database URL for migrations. Set DATABASE_URL, or pass "
        "`alembic -x url=...`. This file deliberately carries no default: a "
        "migration run against the wrong database is not recoverable by "
        "noticing it later."
    )


def _redacted(url: str) -> str:
    """Strip the password before a URL reaches a log line or a traceback."""
    if "@" not in url or "://" not in url:
        return url
    scheme, _, rest = url.partition("://")
    creds, _, host = rest.rpartition("@")
    if ":" not in creds:
        return url
    user, _, _ = creds.partition(":")
    return f"{scheme}://{user}:***@{host}"


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting. Used to review a migration."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect and apply migrations."""
    url = _database_url()
    print(f"[alembic] database: {_redacted(url)}")

    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = url

    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Type and server-default comparison are ON so autogenerate notices
            # a column that changed type or gained a default. A schema diff that
            # only compares column names misses the change that actually breaks
            # an existing reader.
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
