"""Persist Student Studio evidence separately from answer events."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_f10_1_learning_evidence"
down_revision = "0003_f10_learning_intelligence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # New events keep only raw answer fields on the attempt. Existing F9 JSON
    # remains intact and is copied below for compatibility and retrieval.
    with op.batch_alter_table("studio_learning_attempts") as batch_op:
        batch_op.alter_column("evidence_record", existing_type=sa.JSON(), nullable=True)

    op.create_table(
        "studio_evidence_records",
        sa.Column("evidence_id", sa.String(80), primary_key=True),
        sa.Column("profile_id", sa.String(128), nullable=False),
        sa.Column("source_event_id", sa.String(36), nullable=False),
        sa.Column("topic_id", sa.String(160), nullable=False),
        sa.Column("lesson_id", sa.String(160), nullable=False),
        sa.Column("question_id", sa.String(160), nullable=False),
        sa.Column("evidence_record", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["studio_profiles.profile_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_event_id"], ["studio_learning_attempts.attempt_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("profile_id", "source_event_id", name="uq_studio_evidence_source_event"),
    )
    op.create_index(
        "ix_studio_evidence_profile_time", "studio_evidence_records", ["profile_id", "created_at"]
    )
    op.create_index(
        "ix_studio_evidence_profile_topic", "studio_evidence_records", ["profile_id", "topic_id"]
    )
    op.create_index(
        "ix_studio_evidence_profile_lesson", "studio_evidence_records", ["profile_id", "lesson_id"]
    )

    # F9 stored a canonical record on the attempt. Copy valid historical records
    # into the new evidence table while retaining every original attempt row.
    connection = op.get_bind()
    attempts = sa.table(
        "studio_learning_attempts",
        sa.column("attempt_id", sa.String()),
        sa.column("profile_id", sa.String()),
        sa.column("topic_id", sa.String()),
        sa.column("lesson_id", sa.String()),
        sa.column("question_id", sa.String()),
        sa.column("event_timestamp", sa.String()),
        sa.column("evidence_record", sa.JSON()),
    )
    evidence = sa.table(
        "studio_evidence_records",
        sa.column("evidence_id", sa.String()),
        sa.column("profile_id", sa.String()),
        sa.column("source_event_id", sa.String()),
        sa.column("topic_id", sa.String()),
        sa.column("lesson_id", sa.String()),
        sa.column("question_id", sa.String()),
        sa.column("evidence_record", sa.JSON()),
        sa.column("created_at", sa.String()),
    )
    for row in connection.execute(sa.select(attempts)).mappings():
        record = row["evidence_record"]
        if not isinstance(record, dict):
            continue
        provenance = record.get("provenance", {})
        temporal = record.get("temporal", {})
        if (not record.get("evidence_id")
                or record.get("learner_id") != row["profile_id"]
                or provenance.get("source_dataset") != "mcp-ri-student-studio"
                or provenance.get("source_record_id") != row["attempt_id"]
                or record.get("content", {}).get("topic_id") != row["topic_id"]
                or record.get("content", {}).get("lesson_id") != row["lesson_id"]
                or record.get("content", {}).get("question_id") != row["question_id"]):
            # Keep malformed legacy payloads untouched on their original event;
            # do not fabricate or reinterpret an evidence record during upgrade.
            continue
        connection.execute(evidence.insert().values(
            evidence_id=record["evidence_id"],
            profile_id=row["profile_id"],
            source_event_id=row["attempt_id"],
            topic_id=row["topic_id"],
            lesson_id=row["lesson_id"],
            question_id=row["question_id"],
            evidence_record=record,
            created_at=temporal.get("ingestion_timestamp") or row["event_timestamp"],
        ))

    op.execute(sa.text(
        "UPDATE app_metadata SET value='migrations/0004_f10_1_learning_evidence' WHERE key='schema_contract'"
    ))


def downgrade() -> None:
    # Restore the legacy inline copy before removing the derived-record table,
    # so a downgrade retains every event/evidence pair created after 0004.
    connection = op.get_bind()
    attempts = sa.table(
        "studio_learning_attempts",
        sa.column("attempt_id", sa.String()),
        sa.column("evidence_record", sa.JSON()),
    )
    evidence = sa.table(
        "studio_evidence_records",
        sa.column("source_event_id", sa.String()),
        sa.column("evidence_record", sa.JSON()),
    )
    for row in connection.execute(sa.select(evidence)).mappings():
        connection.execute(
            attempts.update().where(attempts.c.attempt_id == row["source_event_id"])
            .where(attempts.c.evidence_record.is_(None))
            .values(evidence_record=row["evidence_record"])
        )
    op.execute(sa.text(
        "UPDATE app_metadata SET value='migrations/0003_f10_learning_intelligence' WHERE key='schema_contract'"
    ))
    op.drop_index("ix_studio_evidence_profile_lesson", table_name="studio_evidence_records")
    op.drop_index("ix_studio_evidence_profile_topic", table_name="studio_evidence_records")
    op.drop_index("ix_studio_evidence_profile_time", table_name="studio_evidence_records")
    op.drop_table("studio_evidence_records")
    with op.batch_alter_table("studio_learning_attempts") as batch_op:
        batch_op.alter_column("evidence_record", existing_type=sa.JSON(), nullable=False)
