"""Create and seed the installation-wide bootstrap lock."""

import sqlalchemy as sa
from alembic import op

revision = "e612f4b9c310"
down_revision = "d47ac76b15fa"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "instance_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("tenant.id", ondelete="RESTRICT")),
        sa.Column("initialized_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_instance_settings_singleton"),
    )
    op.execute("INSERT INTO instance_settings (id, created_at) VALUES (1, CURRENT_TIMESTAMP)")


def downgrade():
    op.drop_table("instance_settings")
