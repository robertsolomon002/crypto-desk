"""MCO pipeline columns (Stage 6.1)

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-03 20:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("mco_videos", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("mco_videos", sa.Column("duration_s", sa.Integer(), nullable=True))
    op.add_column(
        "mco_videos", sa.Column("priority", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "mco_videos", sa.Column("attempts", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column("mco_videos", sa.Column("error", sa.String(length=64), nullable=True))
    op.add_column("mco_wave_labels", sa.Column("pivot_kind", sa.String(length=8), nullable=True))
    op.add_column("mco_wave_labels", sa.Column("snap_bars", sa.Integer(), nullable=True))
    op.add_column("mco_wave_labels", sa.Column("snap_pct", sa.Double(), nullable=True))
    op.add_column("mco_wave_labels", sa.Column("match_note", sa.String(length=128), nullable=True))


def downgrade() -> None:
    for col in ("match_note", "snap_pct", "snap_bars", "pivot_kind"):
        op.drop_column("mco_wave_labels", col)
    for col in ("error", "attempts", "priority", "duration_s", "description"):
        op.drop_column("mco_videos", col)
