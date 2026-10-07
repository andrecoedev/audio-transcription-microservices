"""Worker usage lifecycle tests use fake providers and never call remote APIs."""

import pytest
from cryptography.fernet import Fernet

from src.config import settings
from src.models import (
    Meeting,
    MeetingIntelligence,
    MeetingSpeaker,
    PlatformProviderBudget,
    PlatformProviderCall,
    Transcription,
    TranscriptionJob,
    TranscriptionOwnership,
    UsageEvent,
    UserProviderCredential,
)
from src.services.meeting_intelligence import fingerprint
from src.services.meeting_projection import ordered_segments
from src.services.provider_credentials import encrypt_credential
from src.services.transcription_processing_service import ProcessingResult
from src.workers import meeting_intelligence_worker, transcription_worker


def _seed_local_job(factory, path):
    db = factory()
    try:
        transcription = Transcription(
            filename="usage.wav", original_filename="usage.wav", file_size_mb=0.01,
            duration_seconds=0, transcription_model="whisper", segments=[], status="queued",
        )
        db.add(transcription)
        db.flush()
        db.add(TranscriptionJob(
            transcription_id=transcription.id, input_path=str(path), use_diarization=False,
            transcription_model="whisper", status="queued",
        ))
        db.add(TranscriptionOwnership(
            transcription_id=transcription.id, owner_sub="alice", user_id=1,
        ))
        db.commit()
        return transcription.id
    finally:
        db.close()


class _FakeProcessingService:
    def __init__(self, result=None):
        self.result = result or ProcessingResult(
            segments=[{"start": 0, "end": 12.5, "speaker": "SPEAKER_00", "text": "hello"}],
            duration_seconds=12.5, num_speakers=1, word_count=1,
        )

    def process_transcription(self, **_kwargs):
        return self.result


def test_transcription_measurement_survives_completed_persistence_failure(db_context, monkeypatch, tmp_path):
    input_path = tmp_path / "persist-failure.wav"
    input_path.write_bytes(b"fixture audio")
    transcription_id = _seed_local_job(db_context["session_factory"], input_path)
    monkeypatch.setattr(transcription_worker, "SessionLocal", db_context["session_factory"])
    monkeypatch.setattr(transcription_worker, "get_processing_service", _FakeProcessingService)
    monkeypatch.setattr(
        transcription_worker, "_persist_completed_job",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("simulated persistence outage")),
    )

    with pytest.raises(RuntimeError, match="Transcription processing failed"):
        transcription_worker.process_transcription_job_sync(transcription_id)

    db = db_context["session_factory"]()
    try:
        job = db.query(TranscriptionJob).one()
        assert job.status == "failed"
        events = db.query(UsageEvent).filter_by(operation_id=job.usage_attempt_id).all()
        assert any(event.metric == "audio_seconds" and float(event.quantity) == 12.5 for event in events)
        assert any(event.metric == "attempt_status" and event.status == "failed" for event in events)
    finally:
        db.close()


def test_duplicate_completed_job_does_not_create_a_second_attempt(db_context, monkeypatch, tmp_path):
    path = tmp_path / "duplicate.wav"
    path.write_bytes(b"fixture audio")
    transcription_id = _seed_local_job(db_context["session_factory"], path)
    monkeypatch.setattr(transcription_worker, "SessionLocal", db_context["session_factory"])
    monkeypatch.setattr(transcription_worker, "get_processing_service", _FakeProcessingService)

    assert transcription_worker.process_transcription_job_sync(transcription_id)["status"] == "completed"
    assert transcription_worker.process_transcription_job_sync(transcription_id)["status"] == "already_done"

    db = db_context["session_factory"]()
    try:
        job = db.query(TranscriptionJob).one()
        events = db.query(UsageEvent).filter_by(metric="attempt", resource_id=str(transcription_id)).all()
        assert len(events) == 1
        assert events[0].operation_id == job.usage_attempt_id
    finally:
        db.close()


def test_manually_requeued_local_job_gets_a_new_usage_attempt_id(db_context, monkeypatch, tmp_path):
    path = tmp_path / "reprocess.wav"
    path.write_bytes(b"fixture audio")
    transcription_id = _seed_local_job(db_context["session_factory"], path)
    monkeypatch.setattr(transcription_worker, "SessionLocal", db_context["session_factory"])
    monkeypatch.setattr(transcription_worker, "get_processing_service", _FakeProcessingService)

    transcription_worker.process_transcription_job_sync(transcription_id)
    db = db_context["session_factory"]()
    try:
        job = db.query(TranscriptionJob).one()
        first_attempt = job.usage_attempt_id
        job.status = "queued"
        db.get(Transcription, transcription_id).status = "queued"
        db.commit()
    finally:
        db.close()
    path.write_bytes(b"fixture audio")

    assert transcription_worker.process_transcription_job_sync(transcription_id)["status"] == "completed"
    db = db_context["session_factory"]()
    try:
        job = db.query(TranscriptionJob).one()
        assert job.usage_attempt_id != first_attempt
        attempts = db.query(UsageEvent).filter_by(metric="attempt", resource_id=str(transcription_id)).all()
        assert {event.operation_id for event in attempts} == {first_attempt, job.usage_attempt_id}
    finally:
        db.close()


def test_gemini_counters_are_recorded_before_invalid_schema_failure(db_context, monkeypatch):
    from src.config import settings as app_settings

    factory = db_context["session_factory"]
    db = factory()
    try:
        transcription = Transcription(
            filename="minutes.wav", original_filename="minutes.wav", file_size_mb=0.01,
            duration_seconds=1, transcription_model="whisper", segments=[
                {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00", "text": "Decisão tomada."}
            ], status="completed",
        )
        db.add(transcription)
        db.flush()
        db.add(Meeting(id=transcription.id, title="Usage fixture", language="pt"))
        db.add(MeetingSpeaker(meeting_id=transcription.id, speaker_id="SPEAKER_00"))
        db.add(TranscriptionOwnership(transcription_id=transcription.id, owner_sub="alice", user_id=1))
        segments = ordered_segments(transcription.segments)
        metadata = {"title": "Usage fixture", "language": "pt", "speakers": [{"id": "SPEAKER_00", "display_name": None}]}
        intelligence = MeetingIntelligence(
            meeting_id=transcription.id, revision=1, schema_version="1", provider="gemini",
            model=app_settings.GEMINI_MODEL, credential_source="platform", status="pending",
            source_metadata=metadata, input_fingerprint=fingerprint(metadata, segments),
        )
        db.add(intelligence)
        db.commit()
        intelligence_id = intelligence.id
    finally:
        db.close()

    monkeypatch.setattr(meeting_intelligence_worker, "SessionLocal", factory)
    observed = []

    class FakeProvider:
        def set_usage_observer(self, callback):
            self.observer = callback
            observed.append(("set", callback is not None))

        def generate(self, _context):
            self.observer({
                "status": "response", "model": app_settings.GEMINI_MODEL,
                "elapsed_seconds": 0.25, "prompt_tokens": 42, "candidates_tokens": 8,
                "total_tokens": 50, "thoughts_tokens": 0, "cached_tokens": 3,
                "tool_use_prompt_tokens": 2,
            })
            return "not valid json"

    provider = FakeProvider()
    monkeypatch.setattr(meeting_intelligence_worker, "get_provider", lambda **_kwargs: provider)
    with pytest.raises(RuntimeError, match="Meeting analysis failed"):
        meeting_intelligence_worker.process_intelligence_job(intelligence_id)

    db = factory()
    try:
        row = db.get(MeetingIntelligence, intelligence_id)
        assert row.status == "failed"
        events = db.query(UsageEvent).filter_by(operation_id=row.usage_attempt_id).all()
        quantities = {event.metric: event.quantity for event in events}
        assert float(quantities["input_tokens"]) == 42
        assert float(quantities["output_tokens"]) == 8
        assert float(quantities["total_tokens"]) == 50
        assert float(quantities["thinking_tokens"]) == 0
        assert float(quantities["cache_read_tokens"]) == 3
        assert float(quantities["tool_tokens"]) == 2
        assert any(event.metric == "attempt_status" and event.status == "failed" for event in events)
    finally:
        db.close()


def test_assemblyai_byok_records_usage_without_platform_budget_debit(db_context, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "PROVIDER_CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    path = tmp_path / "aai-byok-usage.wav"
    path.write_bytes(b"fixture audio")
    factory = db_context["session_factory"]
    db = factory()
    try:
        credential = UserProviderCredential(
            id="usage-aai-key", user_id=1, provider="assemblyai",
            ciphertext=encrypt_credential(1, "assemblyai", "synthetic-provider-key"),
        )
        transcription = Transcription(
            filename="aai.wav", original_filename="aai.wav", file_size_mb=0.01,
            duration_seconds=0, transcription_model="assemblyai", segments=[], status="queued",
        )
        db.add_all([credential, transcription])
        db.flush()
        db.add(TranscriptionJob(
            transcription_id=transcription.id, input_path=str(path), use_diarization=False,
            transcription_model="assemblyai", status="queued", credential_source="user",
            credential_id=credential.id, credential_user_id=1,
        ))
        db.add(TranscriptionOwnership(transcription_id=transcription.id, owner_sub="alice", user_id=1))
        db.commit()
        transcription_id = transcription.id
    finally:
        db.close()

    monkeypatch.setattr(transcription_worker, "SessionLocal", factory)
    constructed_keys = []

    class FakeEngine:
        def __init__(self, api_key, **_kwargs):
            constructed_keys.append(api_key)

    class FakeService:
        def __init__(self, cloud_engine=None):
            self.cloud_engine = cloud_engine

        def process_transcription(self, **_kwargs):
            return ProcessingResult(segments=[], duration_seconds=10, num_speakers=0, word_count=0)

        def _get_engine(self, _provider):
            return self.cloud_engine

    from src.services import assemblyai_engine
    monkeypatch.setattr(assemblyai_engine, "AssemblyAIEngine", FakeEngine)
    monkeypatch.setattr(transcription_worker, "TranscriptionProcessingService", FakeService)
    monkeypatch.setattr(transcription_worker, "get_cloud_processing_service", lambda: pytest.fail("BYOK must not use the platform engine"))

    assert transcription_worker.process_transcription_job_sync(transcription_id)["status"] == "completed"
    db = factory()
    try:
        assert constructed_keys == ["synthetic-provider-key"]
        assert db.query(PlatformProviderBudget).count() == 0
        assert db.query(PlatformProviderCall).count() == 0
        job = db.query(TranscriptionJob).one()
        assert db.query(UsageEvent).filter_by(operation_id=job.usage_attempt_id, credential_source="user").count() > 0
    finally:
        db.close()
