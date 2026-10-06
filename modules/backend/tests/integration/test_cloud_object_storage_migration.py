"""Exercise cloud object storage schema changes in an isolated PostgreSQL schema."""
from uuid import uuid4

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import inspect, text


pytestmark = pytest.mark.postgres


def test_cloud_object_storage_migration_and_downgrade_guards(postgres_engine, monkeypatch):
    schema = f"object_storage_migration_{uuid4().hex}"
    revision = ScriptDirectory.from_config(Config("alembic.ini")).get_revision(
        "20261004_0011"
    ).module

    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET search_path TO "{schema}"'))
            connection.execute(
                text("CREATE TABLE transcription_jobs (id integer PRIMARY KEY, input_path varchar(500) NOT NULL)")
            )
            monkeypatch.setattr(
                revision, "op", Operations(MigrationContext.configure(connection))
            )

            revision.upgrade()
            columns = {column["name"]: column for column in inspect(connection).get_columns("transcription_jobs")}
            assert columns["input_object_key"]["nullable"] is True
            assert columns["input_object_key"]["type"].length == 128
            assert "object_deletions" in inspect(connection).get_table_names()

            connection.execute(
                text("INSERT INTO transcription_jobs (id, input_path, input_object_key) VALUES (1, 'legacy.wav', 'opaque-key')")
            )
            with pytest.raises(RuntimeError, match="Preserve object storage keys"):
                revision.downgrade()
            connection.execute(text("DELETE FROM transcription_jobs"))

            connection.execute(
                text("INSERT INTO object_deletions (reference) VALUES ('legacy.wav')")
            )
            with pytest.raises(RuntimeError, match="Preserve pending object deletions"):
                revision.downgrade()
            connection.execute(text("DELETE FROM object_deletions"))

            revision.downgrade()
            assert "input_object_key" not in {
                column["name"] for column in inspect(connection).get_columns("transcription_jobs")
            }
            assert "object_deletions" not in inspect(connection).get_table_names()
        finally:
            connection.execute(text("SET search_path TO public"))
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            transaction.commit()
