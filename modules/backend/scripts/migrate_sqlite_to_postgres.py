"""Copy a legacy SQLite database into an already migrated PostgreSQL database.

This command is intentionally explicit and refuses a non-empty target. Run
``alembic upgrade head`` first and keep a backup of the SQLite file.
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import MetaData, create_engine, func, inspect, select, text

from src.config import settings
from src.models import Base

TABLE_ORDER = ("users", "transcriptions", "transcription_owners", "transcription_jobs")


def _sqlite_url(path_or_url: str) -> str:
    if path_or_url.startswith("sqlite:"):
        return path_or_url
    path = Path(path_or_url).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"SQLite file not found: {path}")
    return f"sqlite:///{path.as_posix()}"


def _normalize_row(table_name: str, row: dict) -> dict:
    now = datetime.now(timezone.utc)
    if row.get("created_at") is None:
        row["created_at"] = now
    if table_name in {"users", "transcriptions", "transcription_jobs"}:
        row["updated_at"] = row.get("updated_at") or row["created_at"]
    if table_name in {"transcriptions", "transcription_jobs"}:
        if row.get("status") == "done":
            row["status"] = "completed"
    return row


def migrate(sqlite_source: str, postgres_url: str) -> dict[str, int]:
    source_engine = create_engine(_sqlite_url(sqlite_source))
    target_engine = create_engine(postgres_url, pool_pre_ping=True)
    if source_engine.dialect.name != "sqlite":
        raise ValueError("Source must be SQLite")
    if target_engine.dialect.name != "postgresql":
        raise ValueError("Target must be PostgreSQL")

    source_metadata = MetaData()
    source_metadata.reflect(bind=source_engine)
    target_tables = Base.metadata.tables
    expected = set(TABLE_ORDER)
    present_target = set(inspect(target_engine).get_table_names())
    if not expected.issubset(present_target):
        raise RuntimeError("Target schema is incomplete; run `alembic upgrade head` first")

    counts: dict[str, int] = {}
    with target_engine.begin() as target, source_engine.connect() as source:
        nonempty = {
            name: target.execute(select(func.count()).select_from(target_tables[name])).scalar_one()
            for name in TABLE_ORDER
        }
        if any(nonempty.values()):
            raise RuntimeError(f"Target database is not empty: {nonempty}")

        for name in TABLE_ORDER:
            if name not in source_metadata.tables:
                counts[name] = 0
                continue
            target_columns = set(target_tables[name].columns.keys())
            rows = []
            for raw in source.execute(select(source_metadata.tables[name])).mappings():
                row = {key: value for key, value in raw.items() if key in target_columns}
                rows.append(_normalize_row(name, row))
            if rows:
                target.execute(target_tables[name].insert(), rows)
            counts[name] = len(rows)

        # Resolve only exact username matches after all users/ownership rows
        # exist. Unmatched legacy subjects deliberately remain NULL.
        target.execute(
            text(
                "UPDATE transcription_owners AS ownership "
                "SET user_id = users.id FROM users "
                "WHERE ownership.user_id IS NULL "
                "AND ownership.owner_sub = users.username"
            )
        )

        for name in TABLE_ORDER:
            target.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{name}', 'id'), "
                    f"COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM {name}"
                )
            )

    source_engine.dispose()
    target_engine.dispose()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sqlite_source", help="SQLite file path or sqlite:/// URL")
    parser.add_argument(
        "--postgres-url",
        default=settings.DATABASE_URL,
        help="Migrated, empty PostgreSQL target (defaults to DATABASE_URL)",
    )
    args = parser.parse_args()
    counts = migrate(args.sqlite_source, args.postgres_url)
    print("SQLite import completed:", counts)


if __name__ == "__main__":
    main()
