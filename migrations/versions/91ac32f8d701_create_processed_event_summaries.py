"""Create processed event summaries.

Revision ID: 91ac32f8d701
Revises: 7d139e245aae
"""
from alembic import op
import sqlalchemy as sa

revision = "91ac32f8d701"
down_revision = "7d139e245aae"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "processed_events",
        sa.Column("event_id", sa.Uuid(), primary_key=True),
        sa.Column("interaction_id", sa.Uuid(), sa.ForeignKey("interaction.id"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("is_error", sa.Boolean(), nullable=False),
        sa.Column("output_empty", sa.Boolean(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("processed_events")
