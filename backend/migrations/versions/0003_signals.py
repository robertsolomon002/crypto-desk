"""Weekly signals (Stage 7.1): append-only `signals`, outcome reference, brief payload

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-04 12:00:00

`signals` rows can be inserted, never updated or deleted (Decision 8): a trigger refuses both,
on top of the hash chain the app writes. TRUNCATE is not blocked (tests reset the database
with it; no app code truncates).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION signals_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'signals rows are append-only (% refused)', TG_OP
                USING ERRCODE = 'restrict_violation';
        END;
        $$;
        """
    )
    op.execute(
        "CREATE TRIGGER signals_append_only BEFORE UPDATE OR DELETE ON signals "
        "FOR EACH ROW EXECUTE FUNCTION signals_append_only()"
    )
    op.add_column("signal_outcomes", sa.Column("reference_close", sa.Double(), nullable=True))
    op.add_column(
        "briefs", sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("briefs", "payload")
    op.drop_column("signal_outcomes", "reference_close")
    op.execute("DROP TRIGGER signals_append_only ON signals")
    op.execute("DROP FUNCTION signals_append_only()")
