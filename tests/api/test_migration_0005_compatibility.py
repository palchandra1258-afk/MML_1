from __future__ import annotations

import json
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError

from mcp_ri.api.persistence import (
    Database,
    StudentGeneratedLesson,
    StudentTutorInteraction,
)


ROOT = Path(__file__).resolve().parents[2]


def _alembic(database_path: Path) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    return config


def _seed_0004(database_path: Path) -> dict[str, list[tuple]]:
    config = _alembic(database_path)
    command.upgrade(config, "0004_f10_1_learning_evidence")
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.exec_driver_sql(
            "INSERT INTO studio_profiles VALUES (?, ?, ?)",
            ("synthetic-profile", "local_demo", "2026-01-01T00:00:00+00:00"),
        )
        connection.exec_driver_sql(
            "INSERT INTO studio_learning_sessions VALUES (?, ?, ?, ?, ?, ?)",
            ("synthetic-session", "synthetic-profile", "synthetic-lesson", "v1", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
        )
        connection.exec_driver_sql(
            "INSERT INTO studio_lesson_progress VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("synthetic-profile", "synthetic-lesson", "synthetic-course", "synthetic-topic", "v1", "section-1", json.dumps(["section-1"]), "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00", None, 2),
        )
        connection.exec_driver_sql(
            "INSERT INTO studio_learning_attempts (attempt_id, profile_id, session_id, submission_id, course_id, topic_id, lesson_id, question_id, attempt_number, event_sequence, submitted_response, is_correct, feedback, content_version, event_timestamp, evidence_record) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("synthetic-attempt", "synthetic-profile", "synthetic-session", "synthetic-submit", "synthetic-course", "synthetic-topic", "synthetic-lesson", "synthetic-question", 1, 1, "{}", 1, "{}", "v1", "2026-01-01T00:00:00+00:00", None),
        )
        connection.exec_driver_sql(
            "INSERT INTO studio_evidence_records VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("synthetic-evidence", "synthetic-profile", "synthetic-attempt", "synthetic-topic", "synthetic-lesson", "synthetic-question", "{}", "2026-01-01T00:00:00+00:00"),
        )
    engine.dispose()
    return _snapshot_core_rows(database_path)


def _snapshot_core_rows(database_path: Path) -> dict[str, list[tuple]]:
    engine = create_engine(f"sqlite:///{database_path}")
    tables = ("studio_profiles", "studio_learning_sessions", "studio_lesson_progress", "studio_learning_attempts", "studio_evidence_records")
    with engine.connect() as connection:
        snapshot = {
            table: list(connection.exec_driver_sql(f'SELECT * FROM "{table}" ORDER BY 1'))
            for table in tables
        }
    engine.dispose()
    return snapshot


def test_upgrade_0004_to_0005_preserves_data_and_matches_models(tmp_path: Path):
    database_path = tmp_path / "migration.sqlite3"
    original_rows = _seed_0004(database_path)
    config = _alembic(database_path)

    command.upgrade(config, "0005_azure_interactive_learning")
    database = Database(f"sqlite:///{database_path}")
    inspector = inspect(database.engine)
    assert inspector.get_table_names() and {"studio_generated_lessons", "studio_tutor_interactions"} <= set(inspector.get_table_names())
    assert _snapshot_core_rows(database_path) == original_rows
    assert database.engine.dialect.name == "sqlite"

    for model in (StudentGeneratedLesson, StudentTutorInteraction):
        model_table = model.__table__
        actual_columns = {column["name"]: column for column in inspector.get_columns(model_table.name)}
        assert set(actual_columns) == set(model_table.columns.keys())
        for model_column in model_table.columns:
            actual = actual_columns[model_column.name]
            assert actual["nullable"] == model_column.nullable
            assert actual["type"]._type_affinity == model_column.type._type_affinity
            assert getattr(actual["type"], "length", None) == getattr(model_column.type, "length", None)
        actual_indexes = {item["name"]: tuple(item["column_names"]) for item in inspector.get_indexes(model_table.name)}
        expected_indexes = {index.name: tuple(column.name for column in index.columns) for index in model_table.indexes}
        assert actual_indexes == expected_indexes
        actual_uniques = {item["name"] for item in inspector.get_unique_constraints(model_table.name)}
        assert {constraint.name for constraint in model_table.constraints if constraint.__class__.__name__ == "UniqueConstraint"} <= actual_uniques
        actual_fks = {
            (tuple(item["constrained_columns"]), item["referred_table"], tuple(item["referred_columns"]))
            for item in inspector.get_foreign_keys(model_table.name)
        }
        model_fks = {
            (
                tuple(element.parent.name for element in constraint.elements),
                constraint.elements[0].column.table.name,
                tuple(element.column.name for element in constraint.elements),
            )
            for constraint in model_table.foreign_key_constraints
        }
        assert actual_fks == model_fks
        created_at = model_table.c.created_at
        assert created_at.default is not None and created_at.server_default is None

    with database.session_factory() as session:
        assert session.scalars(select(StudentGeneratedLesson)).all() == []
        assert session.scalars(select(StudentTutorInteraction)).all() == []
    database.dispose()


def test_0005_constraints_enforce_unique_request_turn_and_session_foreign_key(tmp_path: Path):
    database_path = tmp_path / "constraints.sqlite3"
    _seed_0004(database_path)
    command.upgrade(_alembic(database_path), "head")
    database = Database(f"sqlite:///{database_path}")
    try:
        with database.engine.connect() as connection:
            outer = connection.begin()
            lesson_values = ("validation-lesson", "validation-request", "h" * 64, "topic", "subject", "beginner", "v1", "{}", "[]", None, "2026-01-01T00:00:00+00:00")
            sql = "INSERT INTO studio_generated_lessons VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            connection.exec_driver_sql(sql, lesson_values)
            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.exec_driver_sql(sql, ("validation-lesson-2", *lesson_values[1:]))
            tutor_sql = "INSERT INTO studio_tutor_interactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
            tutor_values = ("interaction-1", "synthetic-session", "turn-1", "h" * 64, "synthetic-lesson", "user", "synthetic", None, "2026-01-01T00:00:00+00:00")
            connection.exec_driver_sql(tutor_sql, tutor_values)
            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.exec_driver_sql(tutor_sql, ("interaction-2", *tutor_values[1:]))
            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.exec_driver_sql(tutor_sql, ("interaction-3", "missing-session", "turn-2", "h" * 64, "synthetic-lesson", "user", "synthetic", None, "2026-01-01T00:00:00+00:00"))
            outer.rollback()
        with database.engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    finally:
        database.dispose()


def test_empty_0005_tables_can_downgrade_and_reupgrade(tmp_path: Path):
    database_path = tmp_path / "roundtrip.sqlite3"
    original_rows = _seed_0004(database_path)
    config = _alembic(database_path)
    command.upgrade(config, "head")
    command.downgrade(config, "0004_f10_1_learning_evidence")
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.connect() as connection:
        names = {row[0] for row in connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "studio_generated_lessons" not in names
        assert "studio_tutor_interactions" not in names
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "0004_f10_1_learning_evidence"
    engine.dispose()
    assert _snapshot_core_rows(database_path) == original_rows
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.connect() as connection:
        names = {row[0] for row in connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"studio_generated_lessons", "studio_tutor_interactions"} <= names
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "0005_azure_interactive_learning"
        assert connection.exec_driver_sql("PRAGMA quick_check").scalar_one() == "ok"
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    engine.dispose()
    assert _snapshot_core_rows(database_path) == original_rows


def _seed_http_fixture(database_path: Path) -> tuple[str, str]:
    from mcp_ri.api.learning_service import PROFILE_ID, curriculum
    from mcp_ri.api.persistence import (
        StudentLearningSession,
        StudentStudioProfile,
        StudentTutorInteraction,
        StudentGeneratedLesson,
        utc_now,
    )

    database = Database(f"sqlite:///{database_path}")
    source_lesson = curriculum().lessons[0]
    lesson_id = "http-test-generated-lesson"
    content_version = "http-test-content-v1"
    generated_lesson = source_lesson.model_copy(update={
        "lesson_id": lesson_id,
        "course_id": "http-test-generated-course",
        "content_version": content_version,
        "content_source": "azure_generated",
        "subject": "Synthetic HTTP fixture",
        "generation_source": "azure_openai",
    })
    source_question = next(item for item in curriculum().questions if item.lesson_id == source_lesson.lesson_id)
    generated_question = source_question.model_copy(update={
        "question_id": "http-test-generated-question",
        "lesson_id": lesson_id,
        "content_version": content_version,
    })
    session_id = "http-test-tutor-session"
    with database.session_factory.begin() as session:
        session.add(StudentStudioProfile(
            profile_id=PROFILE_ID, profile_type="local_demo", created_at=utc_now(),
        ))
        session.flush()
        session.add(StudentLearningSession(
            session_id=session_id,
            profile_id=PROFILE_ID,
            lesson_id=lesson_id,
            content_version=content_version,
            started_at="2026-11-20T10:00:00+00:00",
            last_activity_at="2026-11-20T10:00:00+00:00",
        ))
        session.add(StudentGeneratedLesson(
            lesson_id=lesson_id,
            request_id="http-test-generation-request",
            request_hash="a" * 64,
            topic_id=generated_lesson.topic_id,
            subject="Synthetic HTTP fixture",
            learning_level="beginner",
            content_version=content_version,
            lesson_data=generated_lesson.model_dump(mode="json"),
            questions_data=[generated_question.model_dump(mode="json")],
            usage_data=None,
            created_at=utc_now(),
        ))
        session.add_all([
            StudentTutorInteraction(
                interaction_id="http-test-tutor-user",
                session_id=session_id,
                turn_id="http-test-turn",
                request_hash="b" * 64,
                lesson_id=lesson_id,
                role="user",
                content="Synthetic learner question.",
                usage_data=None,
                created_at="2026-11-20T10:00:01+00:00",
            ),
            StudentTutorInteraction(
                interaction_id="http-test-tutor-assistant",
                session_id=session_id,
                turn_id="http-test-turn",
                request_hash="b" * 64,
                lesson_id=lesson_id,
                role="assistant",
                content="Synthetic tutor response.",
                usage_data=None,
                created_at="2026-11-20T10:00:02+00:00",
            ),
        ])
    database.dispose()
    return session_id, lesson_id


def test_0005_application_lifespan_openapi_and_http_routes(tmp_path: Path):
    import httpx

    database_path = tmp_path / "http.sqlite3"
    _seed_0004(database_path)
    command.upgrade(_alembic(database_path), "0005_azure_interactive_learning")
    session_id, lesson_id = _seed_http_fixture(database_path)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as available_port:
        available_port.bind(("127.0.0.1", 0))
        port = available_port.getsockname()[1]

    environment = {
        "PATH": f"{Path(sys.executable).parent}:/usr/bin:/bin",
        "PYTHONPATH": str(ROOT / "src"),
        "MCP_RI_DATABASE_URL": f"sqlite:///{database_path}",
        "MCP_RI_AUTO_MIGRATE": "false",
        "MCP_RI_CORS_ORIGINS": "http://localhost:3000",
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "mcp_ri.api.main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "error"],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=2) as client:
            deadline = time.monotonic() + 10
            openapi_response = None
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise AssertionError(f"isolated Uvicorn exited early with status {process.returncode}")
                try:
                    openapi_response = client.get("/api/v1/openapi.json")
                    break
                except (httpx.ConnectError, httpx.RemoteProtocolError, OSError):
                    time.sleep(0.05)
            assert openapi_response is not None, "isolated FastAPI process did not become ready"
            assert openapi_response.status_code == 200
            openapi = openapi_response.json()
            assert openapi["openapi"]
            assert {
                "/api/v1/studio/progress",
                "/api/v1/studio/history",
                "/api/v1/studio/lessons/{lesson_id}/tutor/history",
                "/api/v1/curriculum/lessons/{lesson_id}",
                "/api/v1/curriculum/lessons/{lesson_id}/practice",
            } <= set(openapi["paths"])

            progress_response = client.get("/api/v1/studio/progress")
            assert progress_response.status_code == 200
            progress = progress_response.json()
            assert progress["success"] is True
            assert {"profile", "summary", "courses", "recent_lesson_ids", "updated_at"} <= set(progress["data"])
            assert any(course["course_id"] == "http-test-generated-course" for course in progress["data"]["courses"])

            history_response = client.get("/api/v1/studio/history")
            assert history_response.status_code == 200
            history = history_response.json()
            assert history["success"] is True
            assert any(item["lesson_id"] == lesson_id for item in history["data"]["items"])

            lesson_response = client.get(f"/api/v1/curriculum/lessons/{lesson_id}")
            assert lesson_response.status_code == 200
            lesson = lesson_response.json()
            assert lesson["success"] is True
            assert lesson["data"]["lesson_id"] == lesson_id
            assert lesson["data"]["content_source"] == "azure_generated"

            practice_response = client.get(f"/api/v1/curriculum/lessons/{lesson_id}/practice")
            assert practice_response.status_code == 200
            practice = practice_response.json()
            assert practice["success"] is True
            assert practice["data"]["questions"][0]["question_id"] == "http-test-generated-question"
            assert "expected_answer" not in practice["data"]["questions"][0]
            assert "grading" not in practice["data"]["questions"][0]

            tutor_response = client.get(
                f"/api/v1/studio/lessons/{lesson_id}/tutor/history",
                params={"session_id": session_id},
            )
            assert tutor_response.status_code == 200
            tutor_history = tutor_response.json()
            assert tutor_history["success"] is True
            assert [item["role"] for item in tutor_history["data"]] == ["user", "assistant"]

            missing_response = client.get("/api/v1/curriculum/lessons/no-such-generated-lesson")
            assert missing_response.status_code == 404
            assert missing_response.json()["error"]["code"] == "LESSON_NOT_FOUND"

            mismatch_response = client.get(
                "/api/v1/studio/lessons/other-lesson/tutor/history",
                params={"session_id": session_id},
            )
            assert mismatch_response.status_code == 409
            assert mismatch_response.json()["error"]["code"] == "SESSION_MISMATCH"
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
            raise AssertionError("isolated FastAPI application did not shut down cleanly")
    assert process.returncode == 0

    engine = create_engine(f"sqlite:///{database_path}")
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "0005_azure_interactive_learning"
        assert connection.exec_driver_sql("PRAGMA quick_check").scalar_one() == "ok"
    engine.dispose()
