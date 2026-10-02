import os
from datetime import datetime, timedelta, timezone

from src.models import AuditEvent, Meeting, MeetingSpeaker, Transcription, TranscriptionJob, TranscriptionOwnership, User
from src.config import settings
from src.services.privacy import erase_user_data, export_user_data
from src.services.storage_lifecycle import (
    apply_database_retention,
    delete_file_idempotently,
    reconcile_orphaned_uploads,
)


def _seed_owned_data(factory, input_path, user_id=1, username="alice"):
    db = factory()
    transcription = Transcription(
        filename="opaque.wav",
        original_filename="private-meeting.wav",
        file_size_mb=1,
        duration_seconds=3,
        transcription_model="whisper",
        segments=[{"speaker": "SPEAKER_00", "text": "private transcript"}],
        status="completed",
    )
    db.add(transcription)
    db.flush()
    db.add(TranscriptionOwnership(
        transcription_id=transcription.id,
        user_id=user_id,
        owner_sub=username,
    ))
    db.add(TranscriptionJob(
        transcription_id=transcription.id,
        input_path=str(input_path),
        use_diarization=False,
        transcription_model="whisper",
        status="completed",
    ))
    db.commit()
    transcription_id = transcription.id
    db.close()
    return transcription_id


def test_export_contains_only_product_data_and_no_secrets_or_paths(db_context, tmp_path):
    input_path = tmp_path / "private-audio.wav"
    input_path.write_bytes(b"audio")
    _seed_owned_data(db_context["session_factory"], input_path)
    db = db_context["session_factory"]()
    transcription = db.query(Transcription).one()
    db.add(Meeting(id=transcription.id, title="Reunião privada", language="pt"))
    db.add(MeetingSpeaker(meeting_id=transcription.id, speaker_id="SPEAKER_00", display_name="Maria"))
    db.commit()
    user = db.get(User, 1)
    payload = export_user_data(db, user)
    serialized = str(payload)
    assert payload["format"] == "usagi-user-export-v1"
    assert payload["transcriptions"][0]["segments"][0]["text"] == "private transcript"
    assert payload["transcriptions"][0]["meeting"]["title"] == "Reunião privada"
    assert payload["transcriptions"][0]["meeting"]["speakers"][0]["display_name"] == "Maria"
    assert "hashed_password" not in serialized
    assert str(input_path) not in serialized
    assert db.query(AuditEvent).filter_by(event="user.data_exported").count() == 1
    db.close()


def test_user_erasure_cascades_db_and_cleans_file_idempotently(db_context, tmp_path):
    input_path = tmp_path / "private-audio.wav"
    input_path.write_bytes(b"audio")
    transcription_id = _seed_owned_data(db_context["session_factory"], input_path)
    db = db_context["session_factory"]()
    result = erase_user_data(db, db.get(User, 1))
    assert result.transcriptions_deleted == 1
    assert result.files_cleaned == 1
    assert not input_path.exists()
    assert db.get(User, 1) is None
    assert db.get(Transcription, transcription_id) is None
    event = db.query(AuditEvent).filter_by(event="user.data_deleted").one()
    assert event.actor_user_id is None
    assert delete_file_idempotently(input_path) is False
    db.close()


def test_orphan_reconciliation_is_dry_run_first_and_protects_active_jobs(db_context, tmp_path):
    old_orphan = tmp_path / "orphan.wav"
    active = tmp_path / "active.wav"
    recent = tmp_path / "recent.wav"
    for path in (old_orphan, active, recent):
        path.write_bytes(b"audio")
    old_timestamp = (datetime.now(timezone.utc) - timedelta(hours=48)).timestamp()
    os.utime(old_orphan, (old_timestamp, old_timestamp))
    os.utime(active, (old_timestamp, old_timestamp))

    db = db_context["session_factory"]()
    transcription = Transcription(
        filename="active.wav",
        original_filename="active.wav",
        file_size_mb=1,
        duration_seconds=0,
        transcription_model="whisper",
        segments=[],
        status="queued",
    )
    db.add(transcription)
    db.flush()
    db.add(TranscriptionJob(
        transcription_id=transcription.id,
        input_path=str(active),
        use_diarization=False,
        transcription_model="whisper",
        status="queued",
    ))
    db.commit()

    dry_run = reconcile_orphaned_uploads(db, directory=tmp_path, older_than_hours=24)
    assert dry_run == {"scanned": 3, "candidates": 1, "deleted": 0, "failed": 0, "dry_run": True}
    assert old_orphan.exists()
    applied = reconcile_orphaned_uploads(db, directory=tmp_path, older_than_hours=24, apply=True)
    assert applied["deleted"] == 1
    assert not old_orphan.exists()
    assert active.exists() and recent.exists()
    db.close()


def test_database_retention_is_separate_and_dry_run_first(
    db_context, tmp_path, monkeypatch
):
    input_path = tmp_path / "expired.wav"
    input_path.write_bytes(b"audio")
    transcription_id = _seed_owned_data(db_context["session_factory"], input_path)
    old = datetime.now(timezone.utc) - timedelta(days=400)
    db = db_context["session_factory"]()
    db.get(Transcription, transcription_id).created_at = old
    db.add(AuditEvent(
        timestamp=old,
        actor_type="system",
        event="transcription.failed",
        resource_type="transcription",
        resource_id="old",
        event_metadata={},
    ))
    db.commit()
    monkeypatch.setattr(settings, "TRANSCRIPTION_RETENTION_DAYS", 30)
    monkeypatch.setattr(settings, "AUDIT_RETENTION_DAYS", 365)

    preview = apply_database_retention(db)
    assert preview["transcription_candidates"] == 1
    assert preview["audit_candidates"] == 1
    assert db.get(Transcription, transcription_id) is not None

    applied = apply_database_retention(db, apply=True)
    assert applied["transcriptions_deleted"] == 1
    assert applied["audit_events_deleted"] == 1
    assert applied["files_cleaned"] == 1
    assert db.get(Transcription, transcription_id) is None
    assert db.query(AuditEvent).filter_by(event="transcription.deleted").count() == 1
    db.close()


def test_retention_never_deletes_active_job_even_when_old(db_context, tmp_path, monkeypatch):
    input_path = tmp_path / "active.wav"
    input_path.write_bytes(b"audio")
    transcription_id = _seed_owned_data(db_context["session_factory"], input_path)
    db = db_context["session_factory"]()
    transcription = db.get(Transcription, transcription_id)
    transcription.created_at = datetime.now(timezone.utc) - timedelta(days=400)
    transcription.status = "processing"
    transcription.job.status = "processing"
    db.commit()
    monkeypatch.setattr(settings, "TRANSCRIPTION_RETENTION_DAYS", 30)
    assert apply_database_retention(db, apply=True)["transcription_candidates"] == 0
    assert db.get(Transcription, transcription_id) is not None
    assert input_path.exists()
    db.close()


def test_retention_and_reconciliation_repeat_safely(db_context, tmp_path, monkeypatch):
    old_file = tmp_path / "old.wav"
    old_file.write_bytes(b"audio")
    old_timestamp = (datetime.now(timezone.utc) - timedelta(hours=48)).timestamp()
    os.utime(old_file, (old_timestamp, old_timestamp))
    db = db_context["session_factory"]()
    original = delete_file_idempotently
    monkeypatch.setattr(
        "src.services.storage_lifecycle.delete_file_idempotently", lambda _path: False
    )
    failed = reconcile_orphaned_uploads(
        db, directory=tmp_path, older_than_hours=24, apply=True
    )
    assert failed["failed"] == 1
    assert old_file.exists()
    monkeypatch.setattr(
        "src.services.storage_lifecycle.delete_file_idempotently", original
    )
    assert reconcile_orphaned_uploads(
        db, directory=tmp_path, older_than_hours=24, apply=True
    )["deleted"] == 1
    assert reconcile_orphaned_uploads(
        db, directory=tmp_path, older_than_hours=24, apply=True
    )["deleted"] == 0
    db.close()
