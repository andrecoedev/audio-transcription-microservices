from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from rq.exceptions import NoSuchJobError
from rq import Queue, SimpleWorker
from redis import Redis
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import JSONB

from src.authorization import enforce_transcription_access
from src.database import get_db
from src.models import Base, Meeting, MeetingSpeaker, Transcription, TranscriptionJob, TranscriptionOwnership, User
from src.routers import transcriptions as transcriptions_router
from scripts.migrate_sqlite_to_postgres import migrate
from src.security import TokenData
from src.services.transcription_processing_service import ProcessingResult
from src.workers import transcription_worker

pytestmark = pytest.mark.postgres


def _seed_job(factory, *, status="queued", owner="alice", input_path="input.wav"):
    db = factory()
    try:
        transcription = Transcription(
            filename="stored.wav",
            original_filename="reunião.wav",
            file_size_mb=0.01,
            duration_seconds=0,
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
                input_path=input_path,
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


def test_migration_created_expected_schema_and_jsonb(postgres_engine):
    inspector = inspect(postgres_engine)
    assert {
        "alembic_version",
        "transcriptions",
        "transcription_jobs",
        "transcription_owners",
        "users",
        "audit_events",
        "meetings",
        "meeting_speakers",
    }.issubset(inspector.get_table_names())
    segments = next(
        column
        for column in inspector.get_columns("transcriptions")
        if column["name"] == "segments"
    )
    assert isinstance(segments["type"], JSONB)


def test_user_email_and_username_are_unique(postgres_session_factory):
    db = postgres_session_factory()
    try:
        db.add(User(username="alice", email="alice@example.com", hashed_password="hash"))
        db.commit()
        db.add(User(username="alice-2", email="alice@example.com", hashed_password="hash"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        assert db.query(User).count() == 1
    finally:
        db.close()


def test_jsonb_round_trip_constraints_and_cascade(postgres_session_factory):
    transcription_id = _seed_job(postgres_session_factory)
    db = postgres_session_factory()
    try:
        transcription = db.get(Transcription, transcription_id)
        transcription.segments = [
            {"speaker": "João", "start": 0.0, "end": 1.25, "text": "ação e café"},
            {"metadata": {"language": "pt-BR"}},
        ]
        db.commit()
        db.expire_all()
        assert db.get(Transcription, transcription_id).segments[0]["speaker"] == "João"

        transcription.duration_seconds = -1
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        db.delete(db.get(Transcription, transcription_id))
        db.commit()
        assert db.query(TranscriptionJob).count() == 0
        assert db.query(TranscriptionOwnership).count() == 0
    finally:
        db.close()


def test_cross_user_access_is_denied(postgres_session_factory):
    transcription_id = _seed_job(postgres_session_factory, owner="alice")
    db = postgres_session_factory()
    try:
        with pytest.raises(HTTPException) as exc_info:
            enforce_transcription_access(
                db,
                transcription_id,
                TokenData(user_id=2, username="bob", roles=[], scopes=["read_transcriptions"]),
            )
        assert exc_info.value.status_code == 404
    finally:
        db.close()


def test_worker_completed_and_failed_are_atomic(
    postgres_session_factory, monkeypatch, tmp_path
):
    monkeypatch.setattr(transcription_worker, "SessionLocal", postgres_session_factory)

    successful_input = tmp_path / "successful.wav"
    successful_input.write_bytes(b"audio")
    successful_id = _seed_job(
        postgres_session_factory, input_path=str(successful_input)
    )

    class SuccessfulService:
        def process_transcription(self, **_kwargs):
            return ProcessingResult(
                segments=[{"speaker": "SPEAKER_00", "text": "olá", "start": 0, "end": 1}],
                duration_seconds=1,
                num_speakers=1,
                word_count=1,
            )

    monkeypatch.setattr(
        transcription_worker, "get_processing_service", lambda: SuccessfulService()
    )
    assert transcription_worker.process_transcription_job_sync(successful_id)["status"] == "completed"

    db = postgres_session_factory()
    try:
        completed = db.get(Transcription, successful_id)
        completed_job = completed.job
        assert completed.status == completed_job.status == "completed"
        assert completed.segments and completed_job.completed_at is not None
        meeting = db.get(Meeting, successful_id)
        assert meeting is not None
        assert meeting.title == completed.original_filename
        assert [speaker.speaker_id for speaker in meeting.speakers] == ["SPEAKER_00"]
        assert db.query(MeetingSpeaker).filter_by(meeting_id=successful_id).count() == 1
    finally:
        db.close()

    failed_input = tmp_path / "failed.wav"
    failed_input.write_bytes(b"audio")
    failed_id = _seed_job(postgres_session_factory, input_path=str(failed_input))

    class FailingService:
        def process_transcription(self, **_kwargs):
            raise RuntimeError("private internal detail")

    monkeypatch.setattr(
        transcription_worker, "get_processing_service", lambda: FailingService()
    )
    with pytest.raises(RuntimeError, match="Transcription processing failed"):
        transcription_worker.process_transcription_job_sync(failed_id)
    db = postgres_session_factory()
    try:
        failed = db.get(Transcription, failed_id)
        assert failed.status == failed.job.status == "failed"
        assert db.get(Meeting, failed_id) is None
        assert failed.job.failed_at is not None
        assert "private internal detail" not in failed.error_message
    finally:
        db.close()


def test_only_one_concurrent_worker_claims_job(postgres_session_factory, monkeypatch):
    transcription_id = _seed_job(postgres_session_factory)
    monkeypatch.setattr(transcription_worker, "SessionLocal", postgres_session_factory)
    barrier = Barrier(2)

    def claim():
        barrier.wait()
        return transcription_worker._claim_transcription_job(transcription_id)["claim_status"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(claim) for _ in range(2)]
        statuses = sorted(future.result() for future in futures)

    assert statuses == ["already_processing", "claimed"]


def test_transaction_rollback_does_not_leave_partial_record(postgres_session_factory):
    db = postgres_session_factory()
    try:
        with pytest.raises(RuntimeError):
            with db.begin():
                db.add(
                    User(
                        username="rollback-user",
                        email="rollback@example.com",
                        hashed_password="hash",
                    )
                )
                db.flush()
                raise RuntimeError("abort")
    finally:
        db.close()

    verification = postgres_session_factory()
    try:
        assert verification.query(User).filter_by(username="rollback-user").count() == 0
    finally:
        verification.close()


def test_recovery_requeues_only_orphan_processing_job(
    postgres_session_factory, monkeypatch
):
    transcription_id = _seed_job(postgres_session_factory, status="processing")
    active_id = _seed_job(postgres_session_factory, status="queued", owner="bob")
    failed_id = _seed_job(postgres_session_factory, status="failed", owner="carol")
    completed_id = _seed_job(postgres_session_factory, status="completed", owner="dora")
    monkeypatch.setattr(transcription_worker, "SessionLocal", postgres_session_factory)

    class Registry:
        def cleanup(self):
            return None

    class Connection:
        pass

    class Queue:
        started_job_registry = Registry()
        connection = Connection()

        def __init__(self):
            self.enqueued = []

        def enqueue(self, function, job_id_value, **kwargs):
            self.enqueued.append((function, job_id_value, kwargs))

    class ActiveJob:
        def get_status(self, refresh=False):
            return "started"

    def lookup(job_id, **_kwargs):
        if job_id == f"transcription_{active_id}":
            return ActiveJob()
        raise NoSuchJobError

    monkeypatch.setattr(transcription_worker.Job, "fetch", lookup)
    queue = Queue()
    assert transcription_worker.recover_pending_jobs(queue) == 1
    assert queue.enqueued[0][1] == transcription_id

    db = postgres_session_factory()
    try:
        assert db.get(Transcription, transcription_id).status == "queued"
        assert db.get(Transcription, transcription_id).job.status == "queued"
        assert db.get(Transcription, active_id).status == "queued"
        assert db.get(Transcription, failed_id).status == "failed"
        assert db.get(Transcription, completed_id).status == "completed"
    finally:
        db.close()


@pytest.mark.parametrize("storage_kind", ["legacy", "object"])
def test_real_rq_worker_persists_result_in_postgresql(
    postgres_session_factory, monkeypatch, tmp_path, storage_kind
):
    import os

    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        pytest.skip("REDIS_URL is required for the real RQ integration test")

    input_path = tmp_path / "rq-input.wav"
    input_path.write_bytes(b"audio")
    transcription_id = _seed_job(
        postgres_session_factory, input_path=str(input_path)
    )
    if storage_kind == "object":
        from io import BytesIO
        from uuid import uuid4
        from src.config import settings
        from src.services.audio_storage import get_audio_storage
        monkeypatch.setattr(settings, "AUDIO_UPLOAD_DIRECTORY", str(tmp_path / "objects"))
        storage = get_audio_storage()
        object_key = uuid4().hex + ".wav"
        storage.put(object_key, BytesIO(b"audio"))
        db = postgres_session_factory()
        job = db.get(Transcription, transcription_id).job
        job.input_path = ""
        job.input_object_key = object_key
        db.commit()
        db.close()
    monkeypatch.setattr(transcription_worker, "SessionLocal", postgres_session_factory)

    class SuccessfulService:
        def process_transcription(self, **_kwargs):
            from pathlib import Path
            assert Path(_kwargs["file_path"]).read_bytes() == b"audio"
            return ProcessingResult(
                segments=[{"speaker": "SPEAKER_00", "text": "via RQ", "start": 0, "end": 2}],
                duration_seconds=2,
                num_speakers=1,
                word_count=2,
            )

    monkeypatch.setattr(
        transcription_worker, "get_processing_service", lambda: SuccessfulService()
    )
    connection = Redis.from_url(redis_url)
    queue = Queue("p2a-integration", connection=connection)
    queue.empty()
    rq_job = queue.enqueue(
        transcription_worker.process_transcription_job_sync,
        transcription_id,
        job_id=f"p2a-integration-{transcription_id}",
    )
    worker = SimpleWorker([queue], connection=connection)
    assert worker.work(burst=True, logging_level="WARNING") is True
    rq_job.refresh()
    assert rq_job.get_status() == "finished"
    rq_job.delete()  # PostgreSQL results must not depend on the RQ record.

    db = postgres_session_factory()
    try:
        transcription = db.get(Transcription, transcription_id)
        assert transcription.status == transcription.job.status == "completed"
        assert transcription.segments[0]["text"] == "via RQ"
        assert db.get(Meeting, transcription_id) is not None
        from src.models import ObjectDeletion
        assert db.query(ObjectDeletion).count() == 0
        if storage_kind == "object":
            assert not storage.exists(object_key)
        else:
            assert not input_path.exists()
    finally:
        db.close()


def test_real_rq_failure_matches_postgresql_status(
    postgres_session_factory, monkeypatch, tmp_path
):
    import os
    import uuid

    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        pytest.skip("REDIS_URL is required for the real RQ integration test")

    input_path = tmp_path / "rq-failing.wav"
    input_path.write_bytes(b"audio")
    transcription_id = _seed_job(postgres_session_factory, input_path=str(input_path))
    monkeypatch.setattr(transcription_worker, "SessionLocal", postgres_session_factory)

    class FailingService:
        def process_transcription(self, **_kwargs):
            raise RuntimeError("private processing detail")

    monkeypatch.setattr(
        transcription_worker, "get_processing_service", lambda: FailingService()
    )
    connection = Redis.from_url(redis_url)
    queue = Queue("p2a-integration-failure", connection=connection)
    queue.empty()
    rq_job = queue.enqueue(
        transcription_worker.process_transcription_job_sync,
        transcription_id,
        job_id=f"p2a-integration-failure-{uuid.uuid4().hex}",
    )
    worker = SimpleWorker([queue], connection=connection)
    assert worker.work(burst=True, logging_level="WARNING") is True
    rq_job.refresh()
    assert rq_job.get_status() == "failed"
    assert "private processing detail" not in (rq_job.exc_info or "")

    db = postgres_session_factory()
    try:
        transcription = db.get(Transcription, transcription_id)
        assert transcription.status == transcription.job.status == "failed"
        assert transcription.error_message == "Transcription processing failed"
    finally:
        db.close()


def test_legacy_sqlite_import_preserves_ids_and_relationships(
    postgres_engine, postgres_session_factory, tmp_path
):
    sqlite_path = tmp_path / "legacy.db"
    sqlite_engine = create_engine(f"sqlite:///{sqlite_path.as_posix()}")
    Base.metadata.create_all(sqlite_engine)
    sqlite_factory = sessionmaker(bind=sqlite_engine)
    source = sqlite_factory()
    try:
        source.add(User(id=11, username="legacy", email="legacy@example.com", hashed_password="hash"))
        source.add(
            Transcription(
                id=21,
                filename="legacy.wav",
                original_filename="reunião-legada.wav",
                file_size_mb=1,
                duration_seconds=3,
                transcription_model="whisper",
                segments=[{"text": "conteúdo preservado"}],
                status="completed",
            )
        )
        source.add(
            TranscriptionJob(
                id=31,
                transcription_id=21,
                input_path="legacy.wav",
                transcription_model="whisper",
                status="completed",
            )
        )
        source.add(
            TranscriptionOwnership(id=41, transcription_id=21, owner_sub="legacy")
        )
        source.commit()
    finally:
        source.close()
        sqlite_engine.dispose()

    counts = migrate(
        str(sqlite_path), postgres_engine.url.render_as_string(hide_password=False)
    )
    assert counts == {
        "users": 1,
        "transcriptions": 1,
        "transcription_owners": 1,
        "transcription_jobs": 1,
    }
    target = postgres_session_factory()
    try:
        imported = target.get(Transcription, 21)
        assert imported.original_filename == "reunião-legada.wav"
        assert imported.segments == [{"text": "conteúdo preservado"}]
        assert imported.job.id == 31
        assert imported.ownership.id == 41
    finally:
        target.close()


def test_api_worker_status_flow_uses_same_postgresql_records(
    postgres_session_factory, monkeypatch, tmp_path, auth_headers, wav_bytes
):
    seed = postgres_session_factory()
    seed.add(User(id=1, username="alice", email="alice@example.test", hashed_password="unused"))
    seed.commit()
    seed.close()
    class RedisConnection:
        def ping(self):
            return True

    class Queue:
        connection = RedisConnection()

        def __init__(self):
            self.enqueued = []

        def enqueue(self, function, transcription_id, **kwargs):
            self.enqueued.append((function, transcription_id, kwargs))

        def __len__(self):
            return len(self.enqueued)

    queue = Queue()
    app = FastAPI()
    app.include_router(transcriptions_router.router)

    def override_get_db():
        db = postgres_session_factory()
        try:
            yield db
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(transcriptions_router, "get_transcription_queue", lambda: queue)
    monkeypatch.setattr(transcriptions_router, "_UPLOAD_DIRECTORY", tmp_path / "uploads")
    from src.config import settings
    monkeypatch.setattr(settings, "AUDIO_UPLOAD_DIRECTORY", str(tmp_path / "uploads"))
    monkeypatch.setattr(transcription_worker, "SessionLocal", postgres_session_factory)

    class SuccessfulService:
        def process_transcription(self, **_kwargs):
            return ProcessingResult(
                segments=[{"speaker": "SPEAKER_00", "text": "fluxo completo", "start": 0, "end": 1}],
                duration_seconds=1,
                num_speakers=1,
                word_count=2,
            )

    monkeypatch.setattr(
        transcription_worker, "get_processing_service", lambda: SuccessfulService()
    )

    with TestClient(app) as client:
        created = client.post(
            "/transcriptions/jobs",
            files={"file": ("meeting.wav", wav_bytes, "audio/wav")},
            headers=auth_headers(),
        )
        assert created.status_code == 202
        transcription_id = created.json()["transcription_id"]

        queued = client.get(
            f"/transcriptions/jobs/{transcription_id}/status",
            headers=auth_headers(),
        )
        assert queued.json()["job_status"] == "queued"

        processed = transcription_worker.process_transcription_job_sync(transcription_id)
        assert processed["status"] == "completed"

        completed = client.get(
            f"/transcriptions/jobs/{transcription_id}/status",
            headers=auth_headers(),
        )
        assert completed.json()["job_status"] == "completed"
        assert completed.json()["transcription_status"] == "completed"
        result = client.get(
            f"/transcriptions/{transcription_id}", headers=auth_headers()
        )
        assert result.json()["segments"][0]["text"] == "fluxo completo"
