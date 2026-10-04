import pytest

from src.models import (
    ObjectDeletion,
    Transcription,
    TranscriptionJob,
    TranscriptionOwnership,
    User,
)
from src.services.audio_storage import retry_audio_cleanup, schedule_audio_cleanup
from src.services.privacy import erase_user_data, export_user_data
from src.services.transcription_deletion import (
    ActiveTranscriptionError,
    delete_transcription_data,
)


def _seed_transcription(db, *, status="completed", input_path="", input_object_key=None, user_id=None):
    transcription = Transcription(
        filename="opaque.wav",
        original_filename="meeting.wav",
        file_size_mb=1,
        duration_seconds=3,
        transcription_model="whisper",
        segments=[{"text": "private transcript"}],
        status=status,
    )
    db.add(transcription)
    db.flush()
    job = TranscriptionJob(
        transcription_id=transcription.id,
        input_path=input_path,
        input_object_key=input_object_key,
        transcription_model="whisper",
        status=status,
    )
    db.add(job)
    if user_id is not None:
        db.add(
            TranscriptionOwnership(
                transcription_id=transcription.id,
                user_id=user_id,
                owner_sub="alice",
            )
        )
    db.commit()
    return transcription.id


def test_cleanup_intent_is_durable_and_unique_when_scheduled_repeatedly(db_context):
    db = db_context["session_factory"]()
    try:
        schedule_audio_cleanup(db, "object:opaque-key")
        schedule_audio_cleanup(db, "object:opaque-key")
        db.commit()

        rows = db.query(ObjectDeletion).all()
        assert len(rows) == 1
        assert rows[0].reference == "object:opaque-key"
        assert rows[0].attempts == 0
    finally:
        db.close()


def test_cleanup_dry_run_does_not_delete_or_increment_attempts(db_context):
    class Storage:
        def delete(self, _key):
            raise AssertionError("dry run must not call storage")
    db = db_context["session_factory"]()
    try:
        schedule_audio_cleanup(db, "object:dry-run-key")
        db.commit()
        report = retry_audio_cleanup(db, storage=Storage())
        assert report["pending"] == 1
        assert report["dry_run"] is True
        assert db.query(ObjectDeletion).one().attempts == 0
        assert db.query(ObjectDeletion).one().last_attempt_at is None
    finally:
        db.close()


def test_orphan_reconciliation_protects_opaque_active_input(db_context):
    import os
    from datetime import datetime, timedelta, timezone
    from src.services.storage_lifecycle import reconcile_orphaned_uploads
    db = db_context["session_factory"]()
    root = db_context["tmp_path"] / "uploads"
    root.mkdir()
    key = "0" * 32 + ".wav"
    path = root / key
    path.write_bytes(b"synthetic audio")
    old = (datetime.now(timezone.utc) - timedelta(hours=48)).timestamp()
    os.utime(path, (old, old))
    try:
        _seed_transcription(db, status="processing", input_object_key=key)
        report = reconcile_orphaned_uploads(db, directory=root, apply=True)
        assert report["candidates"] == report["deleted"] == 0
        assert path.exists()
        assert db.query(ObjectDeletion).count() == 0
    finally:
        db.close()


def test_failed_cleanup_increments_attempt_and_retains_intent_for_retry(db_context):
    class Storage:
        def delete(self, _key):
            raise OSError("temporary storage failure")

    db = db_context["session_factory"]()
    try:
        schedule_audio_cleanup(db, "object:retry-key")
        db.commit()

        result = retry_audio_cleanup(
            db, reference="object:retry-key", apply=True, storage=Storage()
        )

        row = db.query(ObjectDeletion).one()
        assert result["failed"] == 1
        assert row.attempts == 1
        assert row.last_attempt_at is not None

        class RecoveredStorage:
            def delete(self, _key):
                return None

        recovered = retry_audio_cleanup(
            db, reference="object:retry-key", apply=True, storage=RecoveredStorage()
        )
        assert recovered["deleted"] == 1
        assert db.query(ObjectDeletion).count() == 0
    finally:
        db.close()


def test_successful_and_missing_object_deletion_are_idempotent(db_context):
    class Storage:
        def __init__(self):
            self.deleted = []

        def delete(self, key):
            self.deleted.append(key)
            # A missing object is reported as success by the storage adapter.

    storage = Storage()
    db = db_context["session_factory"]()
    try:
        schedule_audio_cleanup(db, "object:present-key")
        schedule_audio_cleanup(db, "object:already-missing-key")
        db.commit()

        result = retry_audio_cleanup(db, apply=True, storage=storage)

        assert result["deleted"] == 2
        assert storage.deleted == ["present-key", "already-missing-key"]
        assert db.query(ObjectDeletion).count() == 0
        assert retry_audio_cleanup(db, apply=True, storage=storage)["deleted"] == 0
    finally:
        db.close()


def test_active_object_key_is_preserved_from_cleanup(db_context):
    class Storage:
        def delete(self, _key):
            raise AssertionError("active input must not be deleted")

    db = db_context["session_factory"]()
    try:
        _seed_transcription(
            db,
            status="processing",
            input_path="",
            input_object_key="active-key",
        )
        schedule_audio_cleanup(db, "object:active-key")
        db.commit()

        result = retry_audio_cleanup(
            db, reference="object:active-key", apply=True, storage=Storage()
        )

        row = db.query(ObjectDeletion).one()
        assert result["active_preserved"] == 1
        assert row.attempts == 0
    finally:
        db.close()


def test_transcription_delete_cascades_but_cleanup_intent_survives_failure(
    db_context, monkeypatch
):
    class Storage:
        def delete(self, _key):
            raise OSError("storage unavailable")

    monkeypatch.setattr(
        "src.services.audio_storage.get_audio_storage", lambda: Storage()
    )
    db = db_context["session_factory"]()
    try:
        transcription_id = _seed_transcription(
            db, input_path="", input_object_key="delete-key"
        )

        delete_transcription_data(db, db.get(Transcription, transcription_id), None)

        assert db.get(Transcription, transcription_id) is None
        assert db.query(TranscriptionJob).count() == 0
        intent = db.query(ObjectDeletion).one()
        assert intent.reference == "object:delete-key"
        assert intent.attempts == 1
    finally:
        db.close()


def test_user_erasure_rejects_active_job_without_removing_owner_or_data(db_context):
    db = db_context["session_factory"]()
    try:
        transcription_id = _seed_transcription(
            db,
            status="queued",
            input_path="",
            input_object_key="active-user-key",
            user_id=1,
        )

        with pytest.raises(ActiveTranscriptionError, match="Active transcription jobs"):
            erase_user_data(db, db.get(User, 1))

        assert db.get(User, 1) is not None
        assert db.get(Transcription, transcription_id) is not None
        assert db.query(TranscriptionOwnership).filter_by(
            transcription_id=transcription_id
        ).count() == 1
        assert db.query(ObjectDeletion).count() == 0
    finally:
        db.close()


def test_domain_rollback_does_not_commit_cleanup_intent(db_context, monkeypatch):
    db = db_context["session_factory"]()
    try:
        transcription_id = _seed_transcription(
            db, input_path="", input_object_key="rollback-key"
        )
        monkeypatch.setattr(
            db,
            "commit",
            lambda: (_ for _ in ()).throw(RuntimeError("simulated commit failure")),
        )

        with pytest.raises(RuntimeError, match="simulated commit failure"):
            delete_transcription_data(db, db.get(Transcription, transcription_id), None)

        assert db.get(Transcription, transcription_id) is not None
        assert db.query(ObjectDeletion).count() == 0
    finally:
        db.close()


def test_export_does_not_expose_ownership_or_audio_references(db_context):
    db = db_context["session_factory"]()
    try:
        _seed_transcription(
            db,
            input_path="C:/trusted/private/audio.wav",
            input_object_key="opaque-object-key",
            user_id=1,
        )

        payload = export_user_data(db, db.get(User, 1))
        serialized = str(payload)
        item = payload["transcriptions"][0]

        assert item["segments"][0]["text"] == "private transcript"
        assert "ownership" not in item
        assert "C:/trusted/private/audio.wav" not in serialized
        assert "opaque-object-key" not in serialized
    finally:
        db.close()
