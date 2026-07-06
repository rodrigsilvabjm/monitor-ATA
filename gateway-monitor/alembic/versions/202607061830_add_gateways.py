"""add gateways table

Revision ID: 202607061830
Revises: 202607061400
Create Date: 2026-07-06 18:30:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607061830"
down_revision: str | None = "202607061400"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gateways",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("host", sa.String(length=120), nullable=False),
        sa.Column("snmp_community", sa.String(length=120), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_gateways_id"), "gateways", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_gateways_id"), table_name="gateways")
    op.drop_table("gateways")
