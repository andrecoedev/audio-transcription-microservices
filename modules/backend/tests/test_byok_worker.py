"""Worker-side BYOK tests use fake engines and never call provider APIs."""

import json

from cryptography.fernet import Fernet
import pytest
from rq.exceptions import NoSuchJobError

from src.config import settings
from src.models import (
    Meeting, MeetingIntelligence, MeetingSpeaker, Transcription, TranscriptionJob,
    TranscriptionOwnership, TranscriptionReservation, UserProviderCredential,
)
from src.services.provider_credentials import encrypt_credential
from src.services.transcription_processing_service import ProcessingResult
from src.workers import meeting_intelligence_worker, transcription_worker


@pytest.fixture
def byok_cipher(monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))


def _seed_aai_job(factory, path, secret):
    db = factory()
    try:
        credential = UserProviderCredential(
            id="byok-aai-1", user_id=1, provider="assemblyai",
            ciphertext=encrypt_credential(1, "assemblyai", secret),
        )
        transcription = Transcription(
            filename="fixture.wav", original_filename="fixture.wav", file_size_mb=0.01,
            duration_seconds=0, transcription_model="assemblyai", use_diarization=False,
            segments=[], status="queued",
        )
        db.add_all([credential, transcription])
        db.flush()
        job = TranscriptionJob(
            transcription_id=transcription.id, input_path=str(path), use_diarization=False,
            transcription_model="assemblyai", status="queued", credential_source="user",
            credential_id=credential.id, credential_user_id=1,
        )
        db.add(job)
        db.add(TranscriptionOwnership(transcription_id=transcription.id, owner_sub="alice", user_id=1))
        from .entitlement_helpers import reserve_test_job
        db.flush()
        reserve_test_job(db, job)
        db.commit()
        return transcription.id
    finally:
        db.close()


def test_assemblyai_byok_worker_uses_per_job_secret_without_platform_engine(
    db_context, byok_cipher, monkeypatch, tmp_path
):
    secret = "synthetic-aai-worker-secret"
    input_path = tmp_path / "byok.wav"
    input_path.write_bytes(b"synthetic audio")
    transcription_id = _seed_aai_job(db_context["session_factory"], input_path, secret)
    monkeypatch.setattr(transcription_worker, "SessionLocal", db_context["session_factory"])

    constructed = []
    class FakeAssemblyAIEngine:
        def __init__(self, api_key, **_kwargs):
            constructed.append(api_key)
    class FakeProcessingService:
        def __init__(self, cloud_engine=None):
            assert cloud_engine is not None
        def process_transcription(self, **kwargs):
            kwargs["before_inference"](1)
            # A separate session represents the provider call process: both
            # quota admission and the no-repeat marker must already be durable.
            observer = db_context["session_factory"]()
            try:
                assert observer.query(TranscriptionReservation).one().state == "started"
                assert observer.query(TranscriptionJob).one().provider_attempted_at is not None
            finally:
                observer.close()
            return ProcessingResult(segments=[], duration_seconds=1, num_speakers=0, word_count=0)

    from src.services import assemblyai_engine
    monkeypatch.setattr(assemblyai_engine, "AssemblyAIEngine", FakeAssemblyAIEngine)
    monkeypatch.setattr(transcription_worker, "TranscriptionProcessingService", FakeProcessingService)
    monkeypatch.setattr(transcription_worker, "get_cloud_processing_service", lambda: pytest.fail("platform engine used"))
    monkeypatch.setattr(transcription_worker, "get_processing_service", lambda: pytest.fail("local engine used"))

    result = transcription_worker.process_transcription_job_sync(transcription_id)
    assert result["status"] == "completed"
    assert constructed == [secret]
    db = db_context["session_factory"]()
    try:
        assert db.query(TranscriptionJob).one().credential_source == "user"
        assert db.query(TranscriptionJob).one().credential_id == "byok-aai-1"
        assert db.query(TranscriptionJob).one().provider_attempted_at is not None
    finally:
        db.close()

    # A stale queue replay after durable provider-attempt admission must fail
    # before reconstructing an engine or making a second paid provider call.
    db = db_context["session_factory"]()
    try:
        db.query(TranscriptionJob).one().status = "queued"
        db.query(Transcription).one().status = "queued"
        db.commit()
    finally:
        db.close()
    monkeypatch.setattr(transcription_worker.Job, "fetch", lambda *_args, **_kwargs: _raise_missing_rq_job())
    assert transcription_worker.recover_pending_jobs(db_context["queue"]) == 0
    assert db_context["queue"].enqueued == []
    assert constructed == [secret]
    db = db_context["session_factory"]()
    try:
        job = db.query(TranscriptionJob).one()
        assert job.status == "failed"
        assert job.provider_attempted_at is not None
    finally:
        db.close()


def _raise_missing_rq_job(*_args, **_kwargs):
    raise NoSuchJobError


def test_aai_byok_provider_failure_is_sanitized_and_never_falls_back(
    db_context, byok_cipher, monkeypatch, tmp_path
):
    from src.services.assemblyai_engine import AssemblyAIProcessingError
    from src.services import assemblyai_engine

    secret = "synthetic-aai-failure-secret"
    input_path = tmp_path / "byok-error.wav"
    input_path.write_bytes(b"synthetic audio")
    transcription_id = _seed_aai_job(db_context["session_factory"], input_path, secret)
    monkeypatch.setattr(transcription_worker, "SessionLocal", db_context["session_factory"])
    constructed = []
    class FakeAssemblyAIEngine:
        def __init__(self, api_key, **_kwargs):
            constructed.append(api_key)
    class FailingService:
        def __init__(self, cloud_engine=None):
            assert cloud_engine is not None
        def process_transcription(self, **kwargs):
            from .entitlement_helpers import authorize_mock
            authorize_mock(kwargs, 1)
            raise AssemblyAIProcessingError("quota")

    monkeypatch.setattr(assemblyai_engine, "AssemblyAIEngine", FakeAssemblyAIEngine)
    monkeypatch.setattr(transcription_worker, "TranscriptionProcessingService", FailingService)
    monkeypatch.setattr(transcription_worker, "get_cloud_processing_service", lambda: pytest.fail("platform engine fallback"))
    monkeypatch.setattr(transcription_worker, "begin_platform_call", lambda *_args, **_kwargs: pytest.fail("platform ledger fallback"))

    with pytest.raises(RuntimeError, match="AssemblyAI quota exceeded") as error:
        transcription_worker.process_transcription_job_sync(transcription_id)
    assert secret not in str(error.value)
    assert constructed == [secret]
    db = db_context["session_factory"]()
    try:
        job = db.query(TranscriptionJob).one()
        assert job.status == "failed"
        assert job.error_message == "AssemblyAI quota exceeded"
        assert job.provider_attempted_at is not None
    finally:
        db.close()


@pytest.mark.parametrize("failure", ["missing-key", "wrong-key", "revoked-reference"])
def test_revoked_or_unreadable_byok_credential_fails_before_engine_creation(
    db_context, byok_cipher, monkeypatch, tmp_path, failure
):
    secret = "synthetic-aai-read-secret"
    input_path = tmp_path / "byok-unreadable.wav"
    input_path.write_bytes(b"synthetic audio")
    transcription_id = _seed_aai_job(db_context["session_factory"], input_path, secret)
    monkeypatch.setattr(transcription_worker, "SessionLocal", db_context["session_factory"])
    from src.services import assemblyai_engine
    monkeypatch.setattr(assemblyai_engine, "AssemblyAIEngine", lambda *_args, **_kwargs: pytest.fail("engine must not be constructed"))
    monkeypatch.setattr(transcription_worker, "get_cloud_processing_service", lambda: pytest.fail("platform engine fallback"))

    if failure == "missing-key":
        monkeypatch.setattr(settings, "PROVIDER_CREDENTIAL_ENCRYPTION_KEY", None)
    elif failure == "wrong-key":
        # Fernet accepts the format but cannot authenticate ciphertext made by
        # the independent fixture key.
        monkeypatch.setattr(settings, "PROVIDER_CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    else:
        db = db_context["session_factory"]()
        try:
            credential = db.get(UserProviderCredential, "byok-aai-1")
            db.delete(credential)
            db.commit()
        finally:
            db.close()
    with pytest.raises(RuntimeError, match="Transcription processing failed"):
        transcription_worker.process_transcription_job_sync(transcription_id)
    db = db_context["session_factory"]()
    try:
        job = db.query(TranscriptionJob).one()
        assert job.status == "failed"
        assert job.provider_attempted_at is None
        if failure == "revoked-reference":
            assert job.credential_id is None
        else:
            assert job.credential_id == "byok-aai-1"
    finally:
        db.close()


def _seed_meeting(factory):
    db = factory()
    try:
        transcription = Transcription(
            filename="fixture.wav", original_filename="fixture.wav", file_size_mb=0.01,
            duration_seconds=2, transcription_model="whisper", status="completed",
            segments=[{"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00", "text": "We agreed to publish the report."}],
        )
        db.add(transcription)
        db.flush()
        db.add(TranscriptionOwnership(transcription_id=transcription.id, owner_sub="alice", user_id=1))
        db.add(Meeting(id=transcription.id, title="Synthetic", language="en"))
        db.add(MeetingSpeaker(meeting_id=transcription.id, speaker_id="SPEAKER_00", display_name="Alex"))
        db.commit()
        return transcription.id
    finally:
        db.close()


def test_gemini_byok_intelligence_worker_passes_own_key_when_platform_is_unset(
    db_context, auth_headers, byok_cipher, monkeypatch
):
    from src.routers import meeting_intelligence

    secret = "synthetic-gemini-worker-secret"
    client = db_context["client"]
    assert client.post(
        "/settings/providers/gemini/credential", json={"secret": secret}, headers=auth_headers()
    ).status_code == 200
    meeting_id = _seed_meeting(db_context["session_factory"])
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(settings, "GEMINI_API_KEY_CONFIGURED", False)
    monkeypatch.setattr(meeting_intelligence_worker, "SessionLocal", db_context["session_factory"])

    request = client.post(f"/meetings/{meeting_id}/intelligence", headers=auth_headers(scopes=["meeting_minutes", "read_transcriptions"]))
    assert request.status_code == 202
    intelligence_id = request.json()["id"]
    calls = []
    result = {"schema_version": "1", "summary": "The report was agreed.", "topics": [],
              "decisions": [{"description": "Publish the report", "evidence": [{"segment_order": 0, "quote": "We agreed to publish the report."}]}],
              "action_items": [], "open_questions": []}

    class FakeProvider:
        def generate(self, _context):
            return json.dumps(result)
    def fake_get_provider(*, api_key=None):
        calls.append(api_key)
        assert api_key == secret
        return FakeProvider()
    monkeypatch.setattr(meeting_intelligence_worker, "get_provider", fake_get_provider)

    processed = meeting_intelligence_worker.process_intelligence_job(intelligence_id)
    assert processed["status"] == "completed"
    assert calls == [secret]
    db = db_context["session_factory"]()
    try:
        row = db.get(MeetingIntelligence, intelligence_id)
        assert row.credential_source == "user"
        assert row.credential_user_id == 1
        assert row.credential_id is not None
    finally:
        db.close()
