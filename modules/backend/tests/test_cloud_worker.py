import pytest

from src.config import settings
from src.models import Transcription, TranscriptionJob, PlatformProviderCall
from src.services.assemblyai_engine import AssemblyAIProcessingError
from src.services.platform_budget import reserve_platform_call
from src.services.transcription_processing_service import ProcessingResult
from src.workers import transcription_worker


@pytest.mark.parametrize("failure", [None, "quota", "timeout"])
def test_cloud_worker_preserves_native_result_and_never_repeats_attempt(db_context, monkeypatch, tmp_path, failure):
    factory = db_context["session_factory"]
    monkeypatch.setattr(settings, "AAI_PLATFORM_ENABLED", True)
    monkeypatch.setattr(settings, "AAI_GUEST_ENABLED", True)
    monkeypatch.setattr(settings, "AAI_PLATFORM_BUDGET_CENTS", 200)
    monkeypatch.setattr(transcription_worker, "SessionLocal", factory)
    source = tmp_path / "cloud.wav"
    source.write_bytes(b"synthetic audio")
    db = factory()
    row = Transcription(filename="cloud.wav", original_filename="cloud.wav", file_size_mb=1,
        duration_seconds=0, transcription_model="assemblyai", use_diarization=True, segments=[], status="queued")
    db.add(row)
    db.flush()
    tid = row.id
    db.add(TranscriptionJob(transcription_id=tid, input_path=str(source), use_diarization=True,
        transcription_model="assemblyai", max_duration_seconds=600, status="queued"))
    reserve_platform_call(db, tid, "guest")
    db.commit()
    calls = []

    class CloudService:
        def process_transcription(self, **kwargs):
            calls.append(kwargs)
            if failure:
                raise AssemblyAIProcessingError(failure)
            return ProcessingResult(segments=[
                {"start": 0, "end": 1, "speaker": "SPEAKER_00", "text": "Olá"},
                {"start": 1, "end": 2, "speaker": "SPEAKER_01", "text": "Bom dia"},
            ], duration_seconds=2, num_speakers=2, word_count=3,
                engine_metadata={"engine": "assemblyai", "language": "pt"})

    monkeypatch.setattr(transcription_worker, "get_cloud_processing_service", lambda: CloudService())
    monkeypatch.setattr(transcription_worker, "get_processing_service", lambda: pytest.fail("Cloud used local engines"))
    if failure:
        with pytest.raises(RuntimeError, match="AssemblyAI"):
            transcription_worker.process_transcription_job_sync(tid)
    else:
        assert transcription_worker.process_transcription_job_sync(tid)["status"] == "completed"
    db.expire_all()
    assert row.status == row.job.status == ("failed" if failure else "completed")
    assert db.query(PlatformProviderCall).one().state == "attempted"
    if not failure:
        assert row.num_speakers == 2 and len(row.meeting.speakers) == 2
    # Simulate recovery resetting only RQ/DB state after an ambiguous crash.
    row.job.status = row.status = "queued"
    db.commit()
    source.write_bytes(b"synthetic retry")
    with pytest.raises(RuntimeError, match="Transcription processing failed"):
        transcription_worker.process_transcription_job_sync(tid)
    assert len(calls) == 1
    db.close()
