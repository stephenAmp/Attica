"""Tenant ingestion credentials and interaction attribution."""

from alembic import op
import sqlalchemy as sa

revision = "c376c92ef104"
down_revision = "b57fa389c302"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ingestion_api_key",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("secret_hash", sa.String(64), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_ingestion_api_key_tenant_id", "ingestion_api_key", ["tenant_id"])
    op.add_column("interaction", sa.Column("ingestion_key_id", sa.Uuid(), sa.ForeignKey("ingestion_api_key.id")))
    op.alter_column("interaction", "created_by", nullable=True)
    op.create_check_constraint("ck_interaction_source", "interaction", "num_nonnulls(created_by, ingestion_key_id) = 1")


def downgrade():
    # Fails atomically if key-attributed interactions require the newer schema.
    op.alter_column("interaction", "created_by", nullable=False)
    op.drop_constraint("ck_interaction_source", "interaction", type_="check")
    op.drop_column("interaction", "ingestion_key_id")
    op.drop_table("ingestion_api_key")
