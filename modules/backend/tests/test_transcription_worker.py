import pytest
from rq.exceptions import NoSuchJobError

from sqlalchemy import event

from src.models import AuditEvent, Meeting, MeetingSpeaker, Transcription, TranscriptionJob
from src.services.transcription_processing_service import ProcessingResult
from src.workers import transcription_worker


def _seed_worker_job(session_factory, input_path):
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
            status="queued",
        )
        db.add(transcription)
        db.flush()
        db.add(
            TranscriptionJob(
                transcription_id=transcription.id,
                input_path=str(input_path),
                use_diarization=False,
                transcription_model="whisper",
                status="queued",
            )
        )
        db.commit()
        return transcription.id
    finally:
        db.close()


class RecordingSession:
    def __init__(self, session, snapshots):
        self._session = session
        self._snapshots = snapshots

    def __getattr__(self, name):
        return getattr(self._session, name)

    def commit(self):
        self._session.flush()
        job = self._session.query(TranscriptionJob).one()
        transcription = self._session.query(Transcription).one()
        self._snapshots.append((job.status, transcription.status))
        self._session.commit()


def _recording_factory(session_factory, snapshots):
    return lambda: RecordingSession(session_factory(), snapshots)


def test_legacy_guest_job_never_loads_local_or_paid_engines(db_context, monkeypatch, tmp_path):
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4
    from src.models import GuestSession, TranscriptionOwnership

    input_path = tmp_path / "legacy-guest.wav"
    input_path.write_bytes(b"synthetic audio")
    tid = _seed_worker_job(db_context["session_factory"], input_path)
    db = db_context["session_factory"]()
    guest = GuestSession(id=str(uuid4()), expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    db.add(guest)
    db.flush()
    db.add(TranscriptionOwnership(transcription_id=tid, owner_sub=f"guest:{guest.id}", guest_session_id=guest.id))
    db.commit()
    monkeypatch.setattr(transcription_worker, "SessionLocal", db_context["session_factory"])
    def forbidden_engine_loading():
        pytest.fail("Guest cannot load any processing engines before P4-04 admission")
    monkeypatch.setattr(transcription_worker, "get_processing_service", forbidden_engine_loading)
    with pytest.raises(RuntimeError, match="Transcription processing failed"):
        transcription_worker.process_transcription_job_sync(tid)
    db.expire_all()
    assert db.get(Transcription, tid).job.status == db.get(Transcription, tid).status == "failed"
    assert not input_path.exists()
    db.close()


def test_worker_persists_queued_processing_completed(
    db_context, monkeypatch, tmp_path
):
    input_path = tmp_path / "input.wav"
    input_path.write_bytes(b"audio")
    transcription_id = _seed_worker_job(
        db_context["session_factory"], input_path
    )
    snapshots = [("queued", "queued")]

    monkeypatch.setattr(
        transcription_worker,
        "SessionLocal",
        _recording_factory(db_context["session_factory"], snapshots),
    )
    class SuccessfulProcessingService:
        def process_transcription(self, **_kwargs):
            return ProcessingResult(
                segments=[
                    {
                        "start": 0.0,
                        "end": 12.5,
                        "speaker": "SPEAKER_00",
                        "text": "hello world",
                    }
                ],
                duration_seconds=12.5,
                num_speakers=1,
                word_count=2,
            )

    monkeypatch.setattr(
        transcription_worker,
        "get_processing_service",
        lambda: SuccessfulProcessingService(),
    )

    result = transcription_worker.process_transcription_job_sync(transcription_id)

    assert result["status"] == "completed"
    assert snapshots == [
        ("queued", "queued"),
        ("processing", "processing"),
        ("completed", "completed"),
    ]
    db = db_context["session_factory"]()
    try:
        job = db.query(TranscriptionJob).one()
        transcription = db.query(Transcription).one()
        assert job.error_message is None
        assert transcription.word_count == 2
        meeting = db.get(Meeting, transcription_id)
        assert meeting is not None
        assert meeting.title == "meeting.wav"
        assert [speaker.speaker_id for speaker in meeting.speakers] == ["SPEAKER_00"]
        assert transcription.segments[0]["order"] == 0
        assert db.query(AuditEvent).filter_by(event="transcription.completed").count() == 1
    finally:
        db.close()


def test_worker_persists_queued_processing_failed(
    db_context, monkeypatch, tmp_path
):
    input_path = tmp_path / "input.wav"
    input_path.write_bytes(b"audio")
    transcription_id = _seed_worker_job(
        db_context["session_factory"], input_path
    )
    snapshots = [("queued", "queued")]

    monkeypatch.setattr(
        transcription_worker,
        "SessionLocal",
        _recording_factory(db_context["session_factory"], snapshots),
    )
    class FailingProcessingService:
        def process_transcription(self, **_kwargs):
            raise RuntimeError("internal detail")

    monkeypatch.setattr(
        transcription_worker,
        "get_processing_service",
        lambda: FailingProcessingService(),
    )

    with pytest.raises(RuntimeError, match="Transcription processing failed") as failure:
        transcription_worker.process_transcription_job_sync(transcription_id)
    assert "internal detail" not in str(failure.value)
    assert snapshots == [
        ("queued", "queued"),
        ("processing", "processing"),
        ("failed", "failed"),
    ]
    db = db_context["session_factory"]()
    try:
        job = db.query(TranscriptionJob).one()
        transcription = db.query(Transcription).one()
        assert job.error_message == "Transcription processing failed"
        assert transcription.error_message == "Transcription processing failed"
        assert "internal detail" not in job.error_message
        assert db.get(Meeting, transcription_id) is None
        assert db.query(AuditEvent).filter_by(event="transcription.failed").count() == 1
    finally:
        db.close()


def test_meeting_persistence_rolls_back_with_completed_status(
    db_context, monkeypatch, tmp_path
):
    input_path = tmp_path / "input.wav"
    input_path.write_bytes(b"audio")
    transcription_id = _seed_worker_job(db_context["session_factory"], input_path)
    monkeypatch.setattr(
        transcription_worker, "SessionLocal", db_context["session_factory"]
    )

    class SuccessfulService:
        def process_transcription(self, **_kwargs):
            return ProcessingResult(
                segments=[{"start": 0, "end": 1, "speaker": "SPEAKER_00", "text": "olá"}],
                duration_seconds=1,
                num_speakers=1,
                word_count=1,
            )

    monkeypatch.setattr(transcription_worker, "get_processing_service", lambda: SuccessfulService())

    def reject_speaker(_mapper, _connection, _target):
        raise RuntimeError("private persistence detail")

    event.listen(MeetingSpeaker, "before_insert", reject_speaker)
    try:
        with pytest.raises(RuntimeError, match="Transcription processing failed"):
            transcription_worker.process_transcription_job_sync(transcription_id)
    finally:
        event.remove(MeetingSpeaker, "before_insert", reject_speaker)

    db = db_context["session_factory"]()
    try:
        transcription = db.get(Transcription, transcription_id)
        assert transcription.status == transcription.job.status == "failed"
        assert transcription.segments == []
        assert db.get(Meeting, transcription_id) is None
        assert db.query(MeetingSpeaker).count() == 0
    finally:
        db.close()


def test_worker_keeps_rq_failure_public_when_failure_persistence_breaks(
    db_context, monkeypatch, tmp_path
):
    input_path = tmp_path / "input.wav"
    input_path.write_bytes(b"audio")
    transcription_id = _seed_worker_job(db_context["session_factory"], input_path)
    monkeypatch.setattr(
        transcription_worker, "SessionLocal", db_context["session_factory"]
    )

    class FailingProcessingService:
        def process_transcription(self, **_kwargs):
            raise RuntimeError("private processing detail")

    monkeypatch.setattr(
        transcription_worker,
        "get_processing_service",
        lambda: FailingProcessingService(),
    )

    def failed_persistence(*_args):
        raise RuntimeError("private database detail")

    monkeypatch.setattr(
        transcription_worker, "_persist_failed_job", failed_persistence
    )
    with pytest.raises(RuntimeError, match="Transcription processing failed") as failure:
        transcription_worker.process_transcription_job_sync(transcription_id)
    assert "private" not in str(failure.value)


def test_worker_requeues_stale_processing_job(db_context, monkeypatch, tmp_path):
    input_path = tmp_path / "input.wav"
    input_path.write_bytes(b"audio")
    transcription_id = _seed_worker_job(
        db_context["session_factory"], input_path
    )
    db = db_context["session_factory"]()
    try:
        db.query(TranscriptionJob).one().status = "processing"
        db.query(Transcription).one().status = "processing"
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(
        transcription_worker,
        "SessionLocal",
        db_context["session_factory"],
    )

    def missing_job(*_args, **_kwargs):
        raise NoSuchJobError

    monkeypatch.setattr(transcription_worker.Job, "fetch", missing_job)

    recovered = transcription_worker.recover_pending_jobs(db_context["queue"])

    assert recovered == 1
    assert len(db_context["queue"].enqueued) == 1
    assert db_context["queue"].enqueued[0][1] == transcription_id
    db = db_context["session_factory"]()
    try:
        assert db.query(TranscriptionJob).one().status == "queued"
        assert db.query(Transcription).one().status == "queued"
    finally:
        db.close()


def test_worker_does_not_duplicate_active_rq_job(
    db_context, monkeypatch, tmp_path
):
    input_path = tmp_path / "input.wav"
    input_path.write_bytes(b"audio")
    _seed_worker_job(db_context["session_factory"], input_path)

    class ActiveJob:
        def get_status(self, refresh=False):
            return "started"

    monkeypatch.setattr(
        transcription_worker,
        "SessionLocal",
        db_context["session_factory"],
    )
    monkeypatch.setattr(
        transcription_worker.Job,
        "fetch",
        lambda *_args, **_kwargs: ActiveJob(),
    )

    recovered = transcription_worker.recover_pending_jobs(db_context["queue"])

    assert recovered == 0
    assert db_context["queue"].enqueued == []
