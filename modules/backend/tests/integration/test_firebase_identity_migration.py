"""Exercise the migration in a disposable PostgreSQL schema."""
from uuid import uuid4

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import inspect, text


pytestmark = pytest.mark.postgres


def test_firebase_identity_migration_preserves_users_and_guards_downgrade(
    postgres_engine, monkeypatch
):
    schema = f"firebase_migration_{uuid4().hex}"
    revision = ScriptDirectory.from_config(Config("alembic.ini")).get_revision(
        "20261003_0010"
    ).module

    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET search_path TO "{schema}"'))
            connection.execute(
                text(
                    "CREATE TABLE users (id integer PRIMARY KEY, hashed_password varchar(255) NOT NULL)"
                )
            )
            connection.execute(
                text("INSERT INTO users (id, hashed_password) VALUES (1, 'existing-hash')")
            )
            monkeypatch.setattr(
                revision, "op", Operations(MigrationContext.configure(connection))
            )

            revision.upgrade()
            assert connection.execute(
                text("SELECT hashed_password FROM users WHERE id = 1")
            ).scalar() == "existing-hash"

            connection.execute(
                text(
                    "INSERT INTO users (id, hashed_password) VALUES (2, NULL)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO firebase_identities (project_id, uid, user_id) "
                    "VALUES ('project', 'uid', 2)"
                )
            )
            with pytest.raises(RuntimeError, match="Firebase identity bindings"):
                revision.downgrade()
            assert connection.execute(text("SELECT count(*) FROM firebase_identities")).scalar() == 1

            connection.execute(text("DELETE FROM firebase_identities"))
            with pytest.raises(RuntimeError, match="Preserve passwordless users"):
                revision.downgrade()
            assert connection.execute(
                text("SELECT count(*) FROM users WHERE hashed_password IS NULL")
            ).scalar() == 1

            connection.execute(
                text("UPDATE users SET hashed_password = 'restored-hash' WHERE id = 2")
            )
            revision.downgrade()
            assert "firebase_identities" not in inspect(connection).get_table_names()
            assert connection.execute(
                text("SELECT hashed_password FROM users WHERE id = 1")
            ).scalar() == "existing-hash"
        finally:
            connection.execute(text("SET search_path TO public"))
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            transaction.commit()
