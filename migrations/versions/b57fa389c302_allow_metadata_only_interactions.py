"""Allow metadata-only interactions and distinguish unobserved output."""

from alembic import op

revision = "b57fa389c302"
down_revision = "e04615b5a37e"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("interaction", "input", nullable=True)
    op.alter_column("processed_events", "output_empty", nullable=True)
    op.execute("""
        UPDATE processed_events AS p SET output_empty = NULL
        FROM interaction AS i
        WHERE p.interaction_id = i.id AND p.tenant_id = i.tenant_id
          AND i.output IS NULL AND p.output_empty IS TRUE
    """)


def downgrade():
    # PostgreSQL rejects this downgrade if metadata-only inputs exist.
    op.alter_column("interaction", "input", nullable=False)
    op.execute("UPDATE processed_events SET output_empty = TRUE WHERE output_empty IS NULL")
    op.alter_column("processed_events", "output_empty", nullable=False)
