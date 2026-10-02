import sqlite3

import pytest

from scripts.backup_legacy_sqlite import backup
from scripts.inspect_legacy_sqlite import inventory


def test_legacy_inventory_reports_unowned_active_job_without_reading_content(tmp_path):
    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE users (id INTEGER PRIMARY KEY);
        CREATE TABLE transcriptions (id INTEGER PRIMARY KEY, private_text TEXT);
        CREATE TABLE transcription_owners (transcription_id INTEGER);
        CREATE TABLE transcription_jobs (
            id INTEGER PRIMARY KEY, transcription_id INTEGER, status TEXT
        );
        INSERT INTO transcriptions VALUES (1, 'do not expose this text');
        INSERT INTO transcription_jobs VALUES (1, 1, 'processing');
        """
    )
    connection.commit()
    connection.close()

    report = inventory(path)

    assert report["integrity_check"] == "ok"
    assert report["tables"] == {
        "transcription_jobs": 1,
        "transcription_owners": 0,
        "transcriptions": 1,
        "users": 0,
    }
    assert report["transcriptions_without_owner"] == 1
    assert report["job_status_counts"] == {"processing": 1}
    assert report["jobs_without_transcription"] == 0
    assert "do not expose" not in str(report)


def test_legacy_inventory_counts_available_input_files_without_printing_paths(tmp_path):
    backend = tmp_path / "backend"
    database = backend / "database"
    uploads = database / "uploads"
    uploads.mkdir(parents=True)
    (uploads / "present.wav").write_bytes(b"synthetic")
    path = database / "legacy.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE transcriptions (id INTEGER PRIMARY KEY);
        CREATE TABLE transcription_jobs (
            id INTEGER PRIMARY KEY, transcription_id INTEGER,
            status TEXT, input_path TEXT
        );
        INSERT INTO transcriptions VALUES (1), (2);
        INSERT INTO transcription_jobs VALUES
            (1, 1, 'processing', 'database/uploads/present.wav'),
            (2, 2, 'queued', 'database/uploads/missing.wav');
        """
    )
    connection.commit()
    connection.close()

    report = inventory(path)

    assert report["job_input_files_found_on_host"] == 1
    assert report["job_input_files_missing_on_host"] == 1
    assert "present.wav" not in str(report)


def test_byte_exact_legacy_backup_preserves_bytes_and_metadata(tmp_path):
    source = tmp_path / "legacy.db"
    connection = sqlite3.connect(source)
    connection.execute("CREATE TABLE transcriptions (id INTEGER PRIMARY KEY)")
    connection.execute("INSERT INTO transcriptions VALUES (1)")
    connection.commit()
    connection.close()
    destination = tmp_path / "backups" / "legacy-exact.db"

    metadata = backup(source, destination, byte_exact=True)

    assert metadata["copy_mode"] == "byte-exact"
    assert metadata["source_sha256"] == metadata["backup_sha256"]
    assert metadata["source_modified_ns"] == metadata["backup_modified_ns"]
    assert metadata["integrity_check"] == "ok"
    assert destination.read_bytes() == source.read_bytes()
    with pytest.raises(FileExistsError):
        backup(source, destination, byte_exact=True)
    destination.chmod(0o600)
    destination.with_suffix(".db.json").chmod(0o600)
