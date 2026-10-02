"""Make and verify an immutable, metadata-preserving SQLite legacy backup."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from scripts.inspect_legacy_sqlite import inventory


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup(source: Path, destination: Path, *, byte_exact: bool = False) -> dict:
    source = source.resolve(strict=True)
    destination = destination.resolve()
    if destination.exists() or destination.with_suffix(destination.suffix + ".json").exists():
        raise FileExistsError("Backup or metadata destination already exists")
    if destination == source:
        raise ValueError("Backup destination must differ from source")
    destination.parent.mkdir(parents=True, exist_ok=True)

    before = source.stat()
    source_inventory = inventory(source)
    if byte_exact:
        if any(source.with_name(source.name + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
            raise RuntimeError("Byte-exact copy requires an offline SQLite database without sidecar files")
        shutil.copy2(source, destination)
    else:
        source_connection = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
        backup_connection = sqlite3.connect(destination)
        try:
            source_connection.backup(backup_connection)
        finally:
            backup_connection.close()
            source_connection.close()

    shutil.copystat(source, destination)
    after = source.stat()
    backup_inventory = inventory(destination)
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError("SQLite source changed during backup; inspect snapshot before use")
    if source_inventory["integrity_check"] != "ok" or backup_inventory["integrity_check"] != "ok":
        raise RuntimeError("SQLite integrity check failed")
    if source_inventory["tables"] != backup_inventory["tables"]:
        raise RuntimeError("SQLite table counts differ after backup")
    source_hash = _sha256(source)
    backup_hash = _sha256(destination)
    if byte_exact and source_hash != backup_hash:
        raise RuntimeError("Byte-exact SQLite backup hash differs from source")

    metadata = {
        "copy_mode": "byte-exact" if byte_exact else "sqlite-online-backup",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": str(source),
        "backup": str(destination),
        "source_size_bytes": before.st_size,
        "source_modified_ns": before.st_mtime_ns,
        "source_created_ns": before.st_ctime_ns,
        "source_sha256": source_hash,
        "backup_size_bytes": destination.stat().st_size,
        "backup_modified_ns": destination.stat().st_mtime_ns,
        "backup_sha256": backup_hash,
        "table_counts": backup_inventory["tables"],
        "integrity_check": "ok",
    }
    metadata_path = destination.with_suffix(destination.suffix + ".json")
    with metadata_path.open("x", encoding="utf-8") as stream:
        json.dump(metadata, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    os.chmod(destination, 0o400)
    os.chmod(metadata_path, 0o400)
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--byte-exact", action="store_true")
    args = parser.parse_args()
    result = backup(args.source, args.destination, byte_exact=args.byte_exact)
    print(
        json.dumps(
            {
                "backup": result["backup"],
                "size_bytes": result["backup_size_bytes"],
                "table_counts": result["table_counts"],
                "integrity_check": result["integrity_check"],
            },
            ensure_ascii=False,
        )
    )
