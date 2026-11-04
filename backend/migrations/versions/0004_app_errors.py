"""Error counts for the admin Health page (Stage 8.1, D53)

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-04 18:00:00

`app_errors` holds a place and a kind per API or agent error, never a message. A new table, so
the live revision keeps working while this deploy migrates (docs/OPS.md, Migrations).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_errors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("where", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("status", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_app_errors")),
    )
    op.create_index(op.f("ix_app_errors_where"), "app_errors", ["where"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_app_errors_where"), table_name="app_errors")
    op.drop_table("app_errors")
