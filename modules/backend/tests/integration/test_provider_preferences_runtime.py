"""PostgreSQL credential replacement, account isolation and migration guard."""
from uuid import uuid4

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from cryptography.fernet import Fernet
import pytest
from sqlalchemy import text

from src.config import settings
from src.models import User, UserProviderCredential, UserProviderPreferences, Transcription, TranscriptionJob
from src.services.provider_credentials import encrypt_credential, decrypt_credential


def test_postgresql_revocation_preserves_user_origin_and_blocks_decryption(postgres_session_factory, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    db = postgres_session_factory()
    try:
        user = User(username="byok", email="byok@example.test", hashed_password="unused", registration_source="public")
        db.add(user)
        db.flush()
        credential = UserProviderCredential(id=str(uuid4()), user_id=user.id, provider="assemblyai",
            ciphertext=encrypt_credential(user.id, "assemblyai", "synthetic-own-secret"))
        transcription = Transcription(filename="fixture.wav", original_filename="fixture.wav", file_size_mb=1,
            duration_seconds=0, transcription_model="assemblyai", status="queued")
        db.add_all([credential, transcription])
        db.flush()
        job = TranscriptionJob(transcription_id=transcription.id, input_path="synthetic.wav", transcription_model="assemblyai",
            credential_source="user", credential_id=credential.id, credential_user_id=user.id)
        db.add(job)
        db.commit()
        assert decrypt_credential(db, job.credential_id, user.id, "assemblyai") == "synthetic-own-secret"
        db.delete(credential)
        db.commit()
        db.refresh(job)
        assert job.credential_id is None and job.credential_source == "user"
        with pytest.raises(RuntimeError, match="unavailable"):
            decrypt_credential(db, job.credential_id, user.id, "assemblyai")
    finally:
        db.close()


def test_preferences_migration_refuses_populated_downgrade(postgres_engine, postgres_session_factory, monkeypatch):
    db = postgres_session_factory()
    try:
        user = User(username="prefs", email="prefs@example.test", hashed_password="unused")
        db.add(user)
        db.flush()
        db.add(UserProviderPreferences(user_id=user.id, transcription_provider="whisper"))
        db.commit()
    finally:
        db.close()
    revision = ScriptDirectory.from_config(Config("alembic.ini")).get_revision("20261002_0009").module
    with postgres_engine.begin() as connection:
        monkeypatch.setattr(revision, "op", Operations(MigrationContext.configure(connection)))
        with pytest.raises(RuntimeError, match="Preserve provider credentials and preferences"):
            revision.downgrade()
        assert connection.execute(text("SELECT count(*) FROM user_provider_preferences")).scalar() == 1
