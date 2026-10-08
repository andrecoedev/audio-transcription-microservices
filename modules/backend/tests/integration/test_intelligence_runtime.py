"""Real PG locks/JSONB/FKs and RQ; inference is deterministic."""
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import Request, Response
from redis import Redis
from rq import Queue, SimpleWorker

from src.models import Meeting, MeetingIntelligence, Transcription, TranscriptionOwnership, User
from src.routers import meeting_intelligence as router
from src.security import TokenData
from src.workers import meeting_intelligence_worker as worker

pytestmark = pytest.mark.postgres


def seed(factory):
    db = factory()
    try:
        user = User(username="p3b-fixture", email="p3b@example.invalid", hashed_password="synthetic")
        db.add(user)
        db.flush()
        transcription = Transcription(filename="fixture.wav", original_filename="fixture.wav", file_size_mb=0.1,
            duration_seconds=1, status="completed", transcription_model="whisper",
            segments=[{"start": 0, "end": 1, "speaker": "SPEAKER_00", "text": "Teste de análise."}])
        db.add(transcription)
        db.flush()
        db.add(Meeting(id=transcription.id, title="Fixture", language="pt"))
        db.add(TranscriptionOwnership(transcription_id=transcription.id, user_id=user.id, owner_sub=user.username))
        from tests.entitlement_helpers import grant_test_beta
        grant_test_beta(db, user.id)
        db.commit()
        return transcription.id, user.id
    finally:
        db.close()


def setup_requests(monkeypatch, queue):
    monkeypatch.setattr(router.settings, "GEMINI_API_KEY_CONFIGURED", True)
    monkeypatch.setattr(router, "get_transcription_queue", lambda: queue)
    monkeypatch.setattr(router, "enforce_rate_limit", lambda *_args: None)


def submit(factory, meeting_id, user_id):
    db = factory()
    try:
        request = Request({"type": "http", "method": "POST", "path": "/", "headers": []})
        return router.request_generation(meeting_id, request, Response(), db,
            TokenData(user_id=user_id, username="p3b-fixture"), regenerate=False)["id"]
    finally:
        db.close()


def test_concurrent_requests_create_one_revision(postgres_session_factory, monkeypatch):
    meeting_id, user_id = seed(postgres_session_factory)
    class FakeQueue:
        enqueued = []
        class Connection:
            def ping(self): return True
        connection = Connection()
        def enqueue(self, *_args, **_kwargs): self.enqueued.append(_args)
    queue = FakeQueue()
    setup_requests(monkeypatch, queue)
    with ThreadPoolExecutor(max_workers=3) as executor:
        ids = list(executor.map(lambda _: submit(postgres_session_factory, meeting_id, user_id), range(3)))
    assert len(set(ids)) == 1 and len(queue.enqueued) == 1
    db = postgres_session_factory()
    assert db.query(MeetingIntelligence).count() == 1
    db.close()


def test_real_rq_result_survives_job_deletion_and_meeting_cascades(postgres_session_factory, monkeypatch):
    if not os.getenv("REDIS_URL"):
        pytest.skip("REDIS_URL required")
    connection = Redis.from_url(os.environ["REDIS_URL"])
    queue = Queue("p3b-test-" + uuid.uuid4().hex, connection=connection)
    setup_requests(monkeypatch, queue)
    meeting_id, user_id = seed(postgres_session_factory)
    intelligence_id = submit(postgres_session_factory, meeting_id, user_id)
    monkeypatch.setattr(worker, "SessionLocal", postgres_session_factory)
    class FakeProvider:
        def generate(self, _context):
            return json.dumps({"schema_version": "1", "summary": "Teste de análise.", "topics": [],
                               "decisions": [], "action_items": [], "open_questions": []})
    monkeypatch.setattr(worker, "get_provider", FakeProvider)
    rq_job = queue.fetch_job(f"meeting_intelligence_{intelligence_id}")
    assert SimpleWorker([queue], connection=connection).work(burst=True, logging_level="WARNING")
    rq_job.refresh()
    assert rq_job.get_status() == "finished"
    assert "summary" not in rq_job.return_value()
    rq_job.delete()
    db = postgres_session_factory()
    try:
        result = router.result(meeting_id, revision=None, db=db, user=TokenData(user_id=user_id, username="p3b-fixture"))
        assert result["content"]["summary"] == "Teste de análise."
        assert db.get(MeetingIntelligence, intelligence_id).status == "completed"
        db.delete(db.get(Meeting, meeting_id))
        db.commit()
        db.expire_all()
        assert db.get(MeetingIntelligence, intelligence_id) is None
    finally:
        db.close()
