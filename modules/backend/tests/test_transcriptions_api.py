from pathlib import Path

import pytest

from src.config import settings
from src.models import AuditEvent, Transcription, TranscriptionJob, TranscriptionOwnership
from src.routers import transcriptions


def _seed_job(session_factory, *, owner="alice", status="queued"):
    db = session_factory()
    try:
        transcription = Transcription(
            filename="stored.wav",
            original_filename="meeting.wav",
            file_size_mb=0.01,
            duration_seconds=0.0,
            transcription_model="whisper",
            use_diarization=False,
            segments=[],
            status=status,
        )
        db.add(transcription)
        db.flush()
        db.add(
            TranscriptionJob(
                transcription_id=transcription.id,
                input_path="stored.wav",
                use_diarization=False,
                transcription_model="whisper",
                status=status,
            )
        )
        db.add(
            TranscriptionOwnership(
                transcription_id=transcription.id,
                owner_sub=owner,
            )
        )
        db.commit()
        return transcription.id
    finally:
        db.close()


def test_valid_upload_is_accepted(db_context, auth_headers, wav_bytes):
    response = db_context["client"].post(
        "/transcriptions/jobs",
        files={"file": ("meeting.wav", wav_bytes, "audio/wav")},
        headers=auth_headers(),
    )

    assert response.status_code == 202
    assert response.json()["id"] == response.json()["transcription_id"]


def test_invalid_format_is_rejected(db_context, auth_headers):
    response = db_context["client"].post(
        "/transcriptions/jobs",
        files={"file": ("notes.txt", b"not audio", "text/plain")},
        headers=auth_headers(),
    )

    assert response.status_code == 415


def test_extension_with_fake_audio_content_is_rejected(db_context, auth_headers):
    response = db_context["client"].post(
        "/transcriptions/jobs",
        files={"file": ("fake.mp3", b"plain text", "audio/mpeg")},
        headers=auth_headers(),
    )

    assert response.status_code == 415


def test_empty_file_is_rejected(db_context, auth_headers):
    response = db_context["client"].post(
        "/transcriptions/jobs",
        files={"file": ("empty.wav", b"", "audio/wav")},
        headers=auth_headers(),
    )

    assert response.status_code == 400


def test_file_above_limit_is_rejected(
    db_context, auth_headers, wav_bytes, monkeypatch
):
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 0)
    response = db_context["client"].post(
        "/transcriptions/jobs",
        files={"file": ("large.wav", wav_bytes, "audio/wav")},
        headers=auth_headers(),
    )

    assert response.status_code == 413


def test_job_creation_persists_and_enqueues(db_context, auth_headers, wav_bytes):
    response = db_context["client"].post(
        "/transcriptions/jobs",
        files={"file": ("../Reunião da equipe.wav", wav_bytes, "audio/wav")},
        headers=auth_headers(),
    )

    assert response.status_code == 202
    transcription_id = response.json()["id"]
    db = db_context["session_factory"]()
    try:
        transcription = db.get(Transcription, transcription_id)
        job = (
            db.query(TranscriptionJob)
            .filter(TranscriptionJob.transcription_id == transcription_id)
            .one()
        )
        ownership = db.query(TranscriptionOwnership).filter_by(
            transcription_id=transcription_id
        ).one()
        assert transcription.status == "queued"
        assert transcription.original_filename == "Reunião da equipe.wav"
        assert job.input_path == ""
        assert job.input_object_key == transcription.filename
        assert (db_context["tmp_path"] / "uploads" / job.input_object_key).read_bytes() == wav_bytes
        assert str(db_context["tmp_path"]) not in str(response.json())
        assert db_context["queue"].enqueued[0][1] == transcription_id
        assert db_context["queue"].enqueued[0][2]["job_id"] == (
            f"transcription_{transcription_id}"
        )
        assert ownership.user_id == 1
        assert ownership.owner_sub == "alice"
        assert db.query(AuditEvent).filter_by(event="transcription.created").count() == 1
    finally:
        db.close()


@pytest.mark.parametrize(
    "path_template",
    [
        "/transcriptions/{id}/status",
        "/transcriptions/jobs/{id}/status",
    ],
)
def test_job_status_can_be_queried(
    db_context, auth_headers, path_template
):
    transcription_id = _seed_job(db_context["session_factory"])
    response = db_context["client"].get(
        path_template.format(id=transcription_id),
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert response.json()["transcription_status"] == "queued"
    assert response.json()["job_status"] == "queued"


def test_missing_job_returns_404(db_context, auth_headers):
    response = db_context["client"].get(
        "/transcriptions/999/status",
        headers=auth_headers(),
    )

    assert response.status_code == 404


def test_protected_endpoint_rejects_unauthenticated_access(db_context, wav_bytes):
    response = db_context["client"].post(
        "/transcriptions/jobs",
        files={"file": ("meeting.wav", wav_bytes, "audio/wav")},
    )

    assert response.status_code == 401


def test_redis_unavailable_returns_503(
    db_context, auth_headers, wav_bytes, monkeypatch
):
    monkeypatch.setattr(transcriptions, "is_redis_available", lambda _connection: False)
    response = db_context["client"].post(
        "/transcriptions/jobs",
        files={"file": ("meeting.wav", wav_bytes, "audio/wav")},
        headers=auth_headers(),
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Job queue is temporarily unavailable"


def test_enqueue_failure_is_persisted_and_audited(
    db_context, auth_headers, wav_bytes, monkeypatch
):
    def fail_enqueue(*_args, **_kwargs):
        raise RuntimeError("redis connection detail must stay internal")

    monkeypatch.setattr(db_context["queue"], "enqueue", fail_enqueue)
    response = db_context["client"].post(
        "/transcriptions/jobs",
        files={"file": ("meeting.wav", wav_bytes, "audio/wav")},
        headers=auth_headers(),
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Job queue is temporarily unavailable"
    db = db_context["session_factory"]()
    try:
        transcription = db.query(Transcription).one()
        assert transcription.status == "failed"
        event = db.query(AuditEvent).filter_by(event="transcription.failed").one()
        assert event.event_metadata == {"stage": "enqueue"}
    finally:
        db.close()


def test_strict_mode_denies_access_to_another_users_job(
    db_context, auth_headers
):
    transcription_id = _seed_job(db_context["session_factory"], owner="alice")
    response = db_context["client"].get(
        f"/transcriptions/{transcription_id}",
        headers=auth_headers(username="bob"),
    )

    assert response.status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "/transcriptions/{id}",
        "/transcriptions/{id}/status",
        "/transcriptions/jobs/{id}/status",
    ],
)
def test_cross_user_reads_do_not_disclose_resource(db_context, auth_headers, path):
    transcription_id = _seed_job(db_context["session_factory"], owner="alice")
    response = db_context["client"].get(
        path.format(id=transcription_id), headers=auth_headers(username="bob")
    )
    assert response.status_code == 404
    assert response.json()["detail"] in {"Transcription not found", "Transcription job not found"}


def test_cross_user_cannot_delete_and_owner_data_remains(db_context, auth_headers):
    transcription_id = _seed_job(db_context["session_factory"], owner="alice")
    response = db_context["client"].delete(
        f"/transcriptions/{transcription_id}", headers=auth_headers(username="bob")
    )
    assert response.status_code == 404
    db = db_context["session_factory"]()
    assert db.get(Transcription, transcription_id) is not None
    db.close()


def test_owner_cannot_delete_active_job(db_context, auth_headers):
    transcription_id = _seed_job(db_context["session_factory"], status="queued")
    response = db_context["client"].delete(
        f"/transcriptions/{transcription_id}", headers=auth_headers()
    )
    assert response.status_code == 409
    db = db_context["session_factory"]()
    assert db.get(Transcription, transcription_id) is not None
    db.close()


def test_cross_user_cannot_generate_meeting_minutes(
    db_context, auth_headers, monkeypatch
):
    transcription_id = _seed_job(
        db_context["session_factory"], owner="alice", status="completed"
    )
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "configured-for-test")
    response = db_context["client"].post(
        "/meeting-minutes/generate",
        json={"transcription_id": transcription_id, "title": "Private"},
        headers=auth_headers(
            username="bob",
            scopes=["meeting_minutes", "read_transcriptions"],
        ),
    )
    assert response.status_code == 404


def test_list_and_stats_are_scoped_to_current_user(db_context, auth_headers):
    _seed_job(db_context["session_factory"], owner="alice", status="completed")
    _seed_job(db_context["session_factory"], owner="bob", status="failed")
    listed = db_context["client"].get("/transcriptions", headers=auth_headers())
    stats = db_context["client"].get("/stats", headers=auth_headers())
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert stats.json() == {
        "total_transcriptions": 1,
        "completed": 1,
        "failed": 0,
        "processing": 0,
    }


def test_only_one_job_creation_route_is_registered(db_context):
    operation = db_context["client"].app.openapi()["paths"]["/transcriptions/jobs"]
    assert set(operation) == {"post"}
