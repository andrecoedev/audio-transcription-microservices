import json
from pathlib import Path

import pytest

from src.models import Meeting, ObjectDeletion, Transcription, TranscriptionJob
from src.routers import transcriptions
from src.services import audio_storage
from src.services.object_storage import LocalObjectStorage, StorageError
from src.services.transcription_processing_service import ProcessingResult
from src.workers import transcription_worker


@pytest.fixture(autouse=True)
def worker_database(db_context, monkeypatch):
    monkeypatch.setattr(transcription_worker, "SessionLocal", db_context["session_factory"])


def _post_upload(db_context, auth_headers, wav_bytes, filename="meeting.wav"):
    return db_context["client"].post(
        "/transcriptions/jobs",
        files={"file": (filename, wav_bytes, "audio/wav")},
        headers=auth_headers(),
    )


def _stored_job(db_context, transcription_id):
    db = db_context["session_factory"]()
    try:
        transcription = db.get(Transcription, transcription_id)
        job = db.query(TranscriptionJob).filter_by(
            transcription_id=transcription_id
        ).one()
        return transcription, job
    finally:
        db.close()


def _mock_successful_processing(monkeypatch, observed=None):
    class SuccessfulService:
        def process_transcription(self, *, file_path, **_kwargs):
            audio = Path(file_path).read_bytes()
            if observed is not None:
                observed.append(audio)
            return ProcessingResult(
                segments=[{
                    "start": 0.0,
                    "end": 1.25,
                    "speaker": "SPEAKER_00",
                    "text": "stored audio result",
                }],
                duration_seconds=1.25,
                num_speakers=1,
                word_count=3,
                engine_metadata={"language": "en"},
            )

    monkeypatch.setattr(
        transcription_worker, "get_processing_service", SuccessfulService
    )


def test_http_upload_worker_completion_cleanup_and_result_survive_queue_loss(
    db_context, auth_headers, wav_bytes, monkeypatch
):
    observed_audio = []
    _mock_successful_processing(monkeypatch, observed_audio)
    response = _post_upload(
        db_context, auth_headers, wav_bytes, filename="../../private meeting?.wav"
    )

    assert response.status_code == 202
    transcription_id = response.json()["transcription_id"]
    transcription, job = _stored_job(db_context, transcription_id)
    assert job.input_object_key
    assert job.input_path == ""
    assert job.input_object_key == transcription.filename
    assert job.input_object_key.endswith(".wav")
    assert len(job.input_object_key.split(".")[0]) == 32
    assert transcription.original_filename == "private meeting_.wav"

    result = transcription_worker.process_transcription_job_sync(transcription_id)
    assert result["status"] == "completed"
    assert observed_audio == [wav_bytes]
    assert not (Path(db_context["tmp_path"]) / "uploads" / job.input_object_key).exists()

    db_context["queue"].enqueued.clear()
    api_result = db_context["client"].get(
        f"/transcriptions/{transcription_id}", headers=auth_headers()
    )
    assert api_result.status_code == 200
    assert api_result.json()["status"] == "completed"
    assert api_result.json()["segments"][0]["text"] == "stored audio result"
    serialized_result = json.dumps(api_result.json())
    assert str(db_context["tmp_path"]) not in serialized_result
    assert "private meeting_.wav" in serialized_result

    db = db_context["session_factory"]()
    try:
        assert db.get(Meeting, transcription_id).title == "private meeting_.wav"
        assert db.query(ObjectDeletion).filter_by(
            reference="object:" + job.input_object_key
        ).count() == 0
    finally:
        db.close()


def test_cross_user_get_and_delete_return_not_found(
    db_context, auth_headers, wav_bytes
):
    response = _post_upload(db_context, auth_headers, wav_bytes)
    transcription_id = response.json()["transcription_id"]

    get_response = db_context["client"].get(
        f"/transcriptions/{transcription_id}", headers=auth_headers("bob")
    )
    delete_response = db_context["client"].delete(
        f"/transcriptions/{transcription_id}", headers=auth_headers("bob")
    )

    assert response.status_code == 202
    assert get_response.status_code == 404
    assert delete_response.status_code == 404


def test_missing_stored_object_persists_failure_and_raises_safe_rq_error(
    db_context, auth_headers, wav_bytes, monkeypatch
):
    response = _post_upload(db_context, auth_headers, wav_bytes)
    transcription_id = response.json()["transcription_id"]
    _transcription, job = _stored_job(db_context, transcription_id)
    audio_storage.get_audio_storage().delete(job.input_object_key)
    class MustNotProcess:
        def process_transcription(self, **_kwargs):
            pytest.fail("processing engine must not run for a missing object")

    monkeypatch.setattr(
        transcription_worker, "get_processing_service", MustNotProcess
    )

    with pytest.raises(RuntimeError, match="Transcription processing failed") as error:
        transcription_worker.process_transcription_job_sync(transcription_id)

    assert str(error.value) == "Transcription processing failed"
    transcription, job = _stored_job(db_context, transcription_id)
    assert transcription.status == job.status == "failed"
    assert str(db_context["tmp_path"]) not in (transcription.error_message or "")
    assert "Object not found" not in (transcription.error_message or "")


def test_storage_put_failure_returns_sanitized_503_without_database_row(
    db_context, auth_headers, wav_bytes, monkeypatch
):
    class FailingStorage:
        def put(self, _key, _source):
            raise StorageError("C:/private/location secret detail")

    monkeypatch.setattr(transcriptions, "get_audio_storage", lambda _directory: FailingStorage())
    response = _post_upload(db_context, auth_headers, wav_bytes)

    assert response.status_code == 503
    assert "private" not in response.text and "secret" not in response.text
    db = db_context["session_factory"]()
    try:
        assert db.query(Transcription).count() == 0
        assert db.query(TranscriptionJob).count() == 0
    finally:
        db.close()


def test_completed_and_failed_persistence_outages_keep_processing_audio_for_recovery(
    db_context, auth_headers, wav_bytes, monkeypatch
):
    response = _post_upload(db_context, auth_headers, wav_bytes)
    transcription_id = response.json()["transcription_id"]
    _transcription, job = _stored_job(db_context, transcription_id)
    input_path = Path(db_context["tmp_path"]) / "uploads" / job.input_object_key
    _mock_successful_processing(monkeypatch)

    def fail_completion(*_args, **_kwargs):
        raise RuntimeError("private completed database failure")

    def fail_failure(*_args, **_kwargs):
        raise RuntimeError("private failed database failure")

    monkeypatch.setattr(transcription_worker, "_persist_completed_job", fail_completion)
    monkeypatch.setattr(transcription_worker, "_persist_failed_job", fail_failure)
    with pytest.raises(RuntimeError, match="Transcription processing failed"):
        transcription_worker.process_transcription_job_sync(transcription_id)

    transcription, job = _stored_job(db_context, transcription_id)
    assert transcription.status == job.status == "processing"
    assert input_path.exists()
    assert db_context["client"].get(
        f"/transcriptions/{transcription_id}", headers=auth_headers()
    ).status_code == 200


def test_failed_state_persistence_outage_keeps_processing_audio_for_recovery(
    db_context, auth_headers, wav_bytes, monkeypatch
):
    response = _post_upload(db_context, auth_headers, wav_bytes)
    transcription_id = response.json()["transcription_id"]
    _transcription, job = _stored_job(db_context, transcription_id)
    input_path = Path(db_context["tmp_path"]) / "uploads" / job.input_object_key

    class FailedProcessingService:
        def process_transcription(self, **_kwargs):
            raise RuntimeError("processing failed")

    monkeypatch.setattr(
        transcription_worker, "get_processing_service", FailedProcessingService
    )
    monkeypatch.setattr(
        transcription_worker,
        "_persist_failed_job",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("db unavailable")),
    )
    with pytest.raises(RuntimeError, match="Transcription processing failed"):
        transcription_worker.process_transcription_job_sync(transcription_id)

    transcription, job = _stored_job(db_context, transcription_id)
    assert transcription.status == job.status == "processing"
    assert input_path.exists()
