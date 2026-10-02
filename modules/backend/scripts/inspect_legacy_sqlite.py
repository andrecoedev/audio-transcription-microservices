"""Print a non-sensitive, read-only inventory of a legacy SQLite database."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def inventory(path: Path) -> dict:
    database = path.resolve(strict=True)
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    try:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = ? AND name NOT LIKE ? ORDER BY name",
                ("table", "sqlite_%"),
            )
        ]
        counts = {}
        for table in tables:
            quoted = '"' + table.replace('"', '""') + '"'
            counts[table] = connection.execute(
                f"SELECT COUNT(*) FROM {quoted}"
            ).fetchone()[0]
        result = {
            "path": str(database),
            "integrity_check": connection.execute("PRAGMA integrity_check").fetchone()[0],
            "tables": counts,
        }
        if "transcriptions" in tables and "transcription_owners" in tables:
            result["transcriptions_without_owner"] = connection.execute(
                "SELECT COUNT(*) FROM transcriptions AS t "
                "LEFT JOIN transcription_owners AS o ON o.transcription_id = t.id "
                "WHERE o.transcription_id IS NULL"
            ).fetchone()[0]
        if "transcription_jobs" in tables:
            result["job_status_counts"] = dict(
                connection.execute(
                    "SELECT status, COUNT(*) FROM transcription_jobs GROUP BY status"
                )
            )
            result["jobs_without_transcription"] = connection.execute(
                "SELECT COUNT(*) FROM transcription_jobs AS j "
                "LEFT JOIN transcriptions AS t ON t.id = j.transcription_id "
                "WHERE t.id IS NULL"
            ).fetchone()[0]
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(transcription_jobs)")
            }
            if "input_path" in columns:
                paths = [
                    Path(value) for (value,) in connection.execute(
                        "SELECT input_path FROM transcription_jobs WHERE input_path IS NOT NULL"
                    )
                ]
                result["job_input_files_found_on_host"] = sum(
                    (path if path.is_absolute() else database.parent.parent / path).is_file()
                    for path in paths
                )
                result["job_input_files_missing_on_host"] = len(paths) - result[
                    "job_input_files_found_on_host"
                ]
        return result
    finally:
        connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    arguments = parser.parse_args()
    print(json.dumps(inventory(arguments.path), ensure_ascii=False, indent=2))
