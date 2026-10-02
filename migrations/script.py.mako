"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Created: ${create_date}
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """${downgrades if downgrades else "pass"}

    Downgrades here exist only while the schema is still young. Once a table
    holds production rows, a downgrade is a data-loss decision and belongs in a
    reviewed runbook, not in a default path -- which is why dropping a table is
    written explicitly rather than inherited from autogenerate.
    """
    ${downgrades if downgrades else "pass"}