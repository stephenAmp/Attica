"""Store the credential type and ID on each interaction."""

from alembic import op
import sqlalchemy as sa

revision = "d47ac76b15fa"
down_revision = "c376c92ef104"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("interaction", sa.Column(
        "source_type", sa.String(7),
        sa.Computed("CASE WHEN ingestion_key_id IS NULL THEN 'user' ELSE 'api_key' END", persisted=True),
        nullable=False,
    ))
    op.add_column("interaction", sa.Column(
        "source_id", sa.Uuid(),
        sa.Computed("COALESCE(ingestion_key_id, created_by)", persisted=True),
        nullable=False,
    ))


def downgrade():
    op.drop_column("interaction", "source_id")
    op.drop_column("interaction", "source_type")
