"""Ensure the configured platform key cannot enter the BYOK SDK path."""

from uuid import uuid4

from cryptography.fernet import Fernet
import pytest

from src.config import settings
from src.models import (
    BetaAccessGrant,
    Transcription,
    TranscriptionJob,
    TranscriptionOwnership,
    UserProviderCredential,
)
from src.services.provider_credentials import encrypt_credential
from src.services.transcription_entitlements import CAPABILITIES, now_utc
from tests.entitlement_helpers import reserve_test_job


@pytest.fixture
def credential_cipher(monkeypatch):
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(settings, "PROVIDER_CREDENTIAL_ENCRYPTION_KEY", key)
    return key


@pytest.fixture
def beta_provider_accounts(db_context, monkeypatch):
    from tests.entitlement_helpers import enable_test_policy, grant_test_beta

    enable_test_policy(monkeypatch)
    with db_context["session_factory"]() as db:
        for user_id in (1, 2):
            active = db.query(BetaAccessGrant).filter(
                BetaAccessGrant.user_id == user_id,
                BetaAccessGrant.revoked_at.is_(None),
                BetaAccessGrant.expires_at > now_utc(),
            ).first()
            if active is None:
                grant_test_beta(db, user_id)
        db.commit()


def test_exact_platform_key_saved_as_byok_fails_before_sdk_construction(
    db_context, monkeypatch, tmp_path, credential_cipher, beta_provider_accounts,
):
    from src.services import assemblyai_engine
    from src.workers import transcription_worker

    platform_key = "synthetic-platform-key-for-regression-test"
    monkeypatch.setattr(settings, "AAI_API_KEY", platform_key)
    monkeypatch.setattr(settings, "AAI_API_KEY_CONFIGURED", True)
    input_path = tmp_path / "synthetic-byok.wav"
    input_path.write_bytes(b"synthetic audio")
    credential_id = str(uuid4())

    with db_context["session_factory"]() as db:
        credential = UserProviderCredential(
            id=credential_id, user_id=1, provider="assemblyai",
            ciphertext=encrypt_credential(1, "assemblyai", platform_key),
        )
        transcription = Transcription(
            filename=input_path.name, original_filename=input_path.name,
            file_size_mb=0.001, duration_seconds=0, transcription_model="assemblyai",
            status="queued",
        )
        db.add_all([credential, transcription])
        db.flush()
        job = TranscriptionJob(
            transcription_id=transcription.id, input_path=str(input_path),
            transcription_model="assemblyai", credential_source="user",
            credential_id=credential_id, credential_user_id=1, status="queued",
        )
        db.add(job)
        db.add(TranscriptionOwnership(
            transcription_id=transcription.id, owner_sub="user:1", user_id=1,
        ))
        reserve_test_job(db, job, user_id=1)
        transcription_id = transcription.id
        db.commit()

    def sdk_must_not_initialize(*_args, **_kwargs):
        pytest.fail("BYOK platform-key rejection must happen before SDK construction")

    monkeypatch.setattr(assemblyai_engine, "AssemblyAIEngine", sdk_must_not_initialize)
    monkeypatch.setattr(transcription_worker, "SessionLocal", db_context["session_factory"])
    monkeypatch.setattr(
        transcription_worker, "get_cloud_processing_service", sdk_must_not_initialize,
    )

    with pytest.raises(RuntimeError, match="Transcription processing failed"):
        transcription_worker.process_transcription_job_sync(transcription_id)

    with db_context["session_factory"]() as db:
        job = db.query(TranscriptionJob).filter_by(transcription_id=transcription_id).one()
        assert job.status == "failed"
        assert job.provider_attempted_at is None
        assert db.get(Transcription, transcription_id).status == "failed"
        assert "synthetic-platform-key" not in (job.error_message or "")
