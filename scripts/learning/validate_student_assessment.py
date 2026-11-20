#!/usr/bin/env python3
"""Emit a reproducible, aggregate-only Student Studio assessment audit."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from mcp_ri.api.learning_service import curriculum  # noqa: E402
from mcp_ri.learning.assessment_validation import (  # noqa: E402
    analyze_student_studio_attempts,
    audit_question_quality,
    read_student_studio_attempts_read_only,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        help="Optional SQLite path. Opened in read-only/query-only mode; only Student Studio attempt rows are read.",
    )
    args = parser.parse_args()

    catalog = curriculum().model_dump(mode="json")
    quality = audit_question_quality(catalog)
    if args.database is None:
        validation = analyze_student_studio_attempts(question_quality=quality, attempts=[])
        validation["status"] = "catalog_only_no_database_supplied"
        validation["data_source"] = "no learner data read"
    else:
        try:
            loaded = read_student_studio_attempts_read_only(args.database)
        except (OSError, ValueError, sqlite3.Error) as exc:
            parser.error(f"could not open the specified database read-only: {exc}")
        if not loaded["available"]:
            validation = analyze_student_studio_attempts(question_quality=quality, attempts=[])
            validation["status"] = "student_studio_data_unavailable"
            validation["data_source"] = loaded["reason"]
        else:
            validation = analyze_student_studio_attempts(
                question_quality=quality,
                attempts=loaded["attempts"],
            )
            validation["data_source"] = loaded["reason"]

    print(json.dumps({"question_quality": quality, "response_validation": validation}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
