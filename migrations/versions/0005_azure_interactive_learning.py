"""Persist validated generated lessons and lesson-scoped tutor history."""

from alembic import op
import sqlalchemy as sa


revision = "0005_azure_interactive_learning"
down_revision = "0004_f10_1_learning_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "studio_generated_lessons",
        sa.Column("lesson_id", sa.String(160), primary_key=True),
        sa.Column("request_id", sa.String(160), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("topic_id", sa.String(160), nullable=False),
        sa.Column("subject", sa.String(160), nullable=False),
        sa.Column("learning_level", sa.String(24), nullable=False),
        sa.Column("content_version", sa.String(40), nullable=False),
        sa.Column("lesson_data", sa.JSON(), nullable=False),
        sa.Column("questions_data", sa.JSON(), nullable=False),
        sa.Column("usage_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("request_id", name="uq_studio_generated_request_id"),
    )
    op.create_index("ix_studio_generated_topic_created", "studio_generated_lessons", ["topic_id", "created_at"])
    op.create_table(
        "studio_tutor_interactions",
        sa.Column("interaction_id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("studio_learning_sessions.session_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("turn_id", sa.String(80), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("lesson_id", sa.String(160), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.String(5000), nullable=False),
        sa.Column("usage_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("session_id", "turn_id", "role", name="uq_studio_tutor_session_turn_role"),
    )
    op.create_index("ix_studio_tutor_session_time", "studio_tutor_interactions", ["session_id", "created_at"])
    op.execute(sa.text(
        "UPDATE app_metadata SET value='migrations/0005_azure_interactive_learning' WHERE key='schema_contract'"
    ))


def downgrade() -> None:
    op.execute(sa.text(
        "UPDATE app_metadata SET value='migrations/0004_f10_1_learning_evidence' WHERE key='schema_contract'"
    ))
    op.drop_index("ix_studio_tutor_session_time", table_name="studio_tutor_interactions")
    op.drop_table("studio_tutor_interactions")
    op.drop_index("ix_studio_generated_topic_created", table_name="studio_generated_lessons")
    op.drop_table("studio_generated_lessons")
