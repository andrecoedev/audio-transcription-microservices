"""Public HTTP → PG → Redis/RQ → FFmpeg → synthetic providers → durable review."""
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from redis import Redis
from rq import Queue, SimpleWorker

from src.config import settings
from src.database import get_db
from src.models import (BetaAccessGrant, Meeting, MeetingActionItem, MeetingIntelligence,
    PlatformProviderCall, Transcription, TranscriptionReservation, User)
from tests.homologation.doubles import audio_bytes, install, prepare_policy, RESULT

pytestmark = pytest.mark.postgres


@pytest.fixture
def journey(postgres_session_factory, monkeypatch, tmp_path):
    redis_url = os.getenv("P2A_TEST_REDIS_URL")
    if not redis_url:
        pytest.skip("P2A_TEST_REDIS_URL is required for the disposable journey")
    from src.main import app
    from src.routers import transcriptions, meeting_intelligence
    from src.utils import http_limits
    from src.workers import transcription_worker, meeting_intelligence_worker
    connection = Redis.from_url(redis_url)
    queue = Queue("beta-journey-" + uuid4().hex, connection=connection)
    assembly, intelligence = install(monkeypatch)
    for module in (transcription_worker, meeting_intelligence_worker, http_limits):
        monkeypatch.setattr(module, "SessionLocal", postgres_session_factory)
    for module in (transcriptions, meeting_intelligence):
        monkeypatch.setattr(module, "get_transcription_queue", lambda: queue)
    monkeypatch.setattr(settings, "AUDIO_UPLOAD_DIRECTORY", str(tmp_path / "audio"))
    monkeypatch.setattr(transcriptions, "_UPLOAD_DIRECTORY", tmp_path / "audio")
    with postgres_session_factory() as db:
        prepare_policy(db)
    def database():
        with postgres_session_factory() as db:
            try:
                yield db
            except Exception:
                db.rollback()
                raise
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        yield client, queue, assembly, intelligence
    app.dependency_overrides = previous
    for job_id in queue.get_job_ids():
        job = queue.fetch_job(job_id)
        if job:
            job.delete()
    queue.delete()


def headers(persona):
    return {"Authorization": f"Bearer beta-e2e-{persona}"}


def login(client, persona):
    response = client.post("/auth/firebase", headers=headers(persona))
    assert response.status_code == 200, response.text
    return response.json()["user"]["id"]


def grant(client, user_id):
    response = client.post(f"/admin/accounts/{user_id}/beta", headers=headers("admin"), json={
        "capabilities": ["transcription.platform", "intelligence.platform"],
        "round_id": "test-round", "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    })
    assert response.status_code == 201, response.text
    return response.json()["id"]


def upload(client, *, payload=None):
    return client.post("/transcriptions/jobs", headers=headers("member"),
        files={"file": ("Reunião de integração – versão 2.wav", audio_bytes() if payload is None else payload, "audio/wav")},
        data={"transcription_model": "assemblyai", "credential_source": "platform", "use_diarization": "true"})


def work(queue):
    SimpleWorker([queue], connection=queue.connection).work(burst=True, logging_level="WARNING")


def test_invitee_full_journey_and_later_return_survive_rq_removal(journey, postgres_session_factory):
    client, queue, assembly, intelligence = journey
    owner_id = login(client, "member")
    other_id = login(client, "other")
    admin_id = login(client, "admin")
    with postgres_session_factory() as db:
        assert not db.get(User, owner_id).is_superuser
        assert db.get(User, owner_id).plan == "free"
        assert db.query(BetaAccessGrant).count() == 0
        db.get(User, admin_id).is_superuser = True
        db.commit()
    assert upload(client).status_code == 403
    grant_id = grant(client, owner_id)
    plan = client.get("/account/plan", headers=headers("member"))
    assert plan.status_code == 200
    assert "36000" in plan.text  # 600 minutes / 10 hours; no monthly renewal.
    denied_byok = client.post("/transcriptions/jobs", headers=headers("member"),
        files={"file": ("sample.wav", audio_bytes(), "audio/wav")},
        data={"transcription_model": "assemblyai", "credential_source": "user"})
    assert denied_byok.status_code == 503  # Own credential absent: no fallback.
    submitted = upload(client)
    assert submitted.status_code == 202, submitted.text
    tid = submitted.json()["transcription_id"]
    assert client.get(f"/transcriptions/jobs/{tid}/status", headers=headers("member")).json()["job_status"] == "queued"
    work(queue)
    transcription_job = queue.fetch_job(f"transcription_{tid}")
    assert transcription_job.get_status() == "finished"
    assert assembly.calls == 1
    assert client.get(f"/transcriptions/{tid}", headers=headers("member")).json()["status"] == "completed"
    assert client.get(f"/meetings/{tid}", headers=headers("member")).status_code == 200
    generation = client.post(f"/meetings/{tid}/intelligence", headers=headers("member"))
    assert generation.status_code == 202, generation.text
    duplicate = client.post(f"/meetings/{tid}/intelligence", headers=headers("member"))
    assert duplicate.json()["id"] == generation.json()["id"]
    work(queue)
    assert intelligence.calls == 1
    result = client.get(f"/meetings/{tid}/intelligence/result", headers=headers("member"))
    assert result.json()["content"] == RESULT
    accepted = client.post(f"/meetings/{tid}/actions/suggestions/1/0", headers=headers("member"), json={"due_date": "2026-10-20"})
    assert accepted.status_code == 201, accepted.text
    action_id = accepted.json()["id"]
    assert client.post(f"/meetings/{tid}/actions/suggestions/1/0", headers=headers("member"), json={}).json()["id"] == action_id
    updated = client.patch(f"/meetings/{tid}/actions/{action_id}", headers=headers("member"), json={"status": "done"})
    assert updated.status_code == 200
    for persona in ("other", "admin"):
        for path in (f"/transcriptions/{tid}", f"/meetings/{tid}", f"/meetings/{tid}/intelligence/result", f"/meetings/{tid}/actions", f"/meetings/{tid}/minutes.md"):
            assert client.get(path, headers=headers(persona)).status_code == 404
        assert client.post(f"/meetings/{tid}/intelligence", headers=headers(persona)).status_code == 404
        assert client.patch(f"/meetings/{tid}/actions/{action_id}", headers=headers(persona), json={"status": "open"}).status_code == 404
    transcription_job.delete()
    queue.fetch_job(f"meeting_intelligence_{generation.json()['id']}").delete()
    # Re-authentication resolves the same internal identity, not client state.
    assert login(client, "member") == owner_id
    assert client.get(f"/meetings/{tid}/intelligence/result", headers=headers("member")).json()["content"]["decisions"]
    assert client.get(f"/meetings/{tid}/actions", headers=headers("member")).json()["action_items"][0]["status"] == "done"
    export = client.get("/account/data", headers=headers("member"))
    assert export.status_code == 200
    assert "Revisar o guia" in export.text
    assert client.delete(f"/admin/accounts/{owner_id}/beta/{grant_id}", headers=headers("admin")).status_code == 200
    assert upload(client).status_code == 403
    assert client.get(f"/transcriptions/{tid}", headers=headers("member")).status_code == 200
    with postgres_session_factory() as db:
        assert db.query(Meeting).count() == 1
        assert db.query(MeetingIntelligence).count() == 1
        assert db.query(MeetingActionItem).count() == 1
        assert db.query(TranscriptionReservation).count() == 1
        assert db.query(PlatformProviderCall).count() == 1
        assert db.get(Transcription, tid).duration_seconds == 40
        assert owner_id != other_id


def test_invalid_upload_and_ambiguous_provider_failure_never_retry_paid_submission(journey, postgres_session_factory):
    client, queue, assembly, _ = journey
    owner_id = login(client, "member")
    admin_id = login(client, "admin")
    with postgres_session_factory() as db:
        db.get(User, admin_id).is_superuser = True
        db.commit()
    grant(client, owner_id)
    assert upload(client, payload=b"not audio").status_code == 415
    assert assembly.calls == 0
    assembly.failure = "timeout"
    submitted = upload(client)
    assert submitted.status_code == 202, submitted.text
    tid = submitted.json()["transcription_id"]
    work(queue)
    assert queue.fetch_job(f"transcription_{tid}").get_status() == "failed"
    assert client.get(f"/transcriptions/{tid}", headers=headers("member")).json()["status"] == "failed"
    from src.workers.transcription_worker import process_transcription_job_sync, recover_pending_jobs
    recover_pending_jobs(queue)
    with pytest.raises(RuntimeError):
        process_transcription_job_sync(tid)
    assert assembly.calls == 1
    with postgres_session_factory() as db:
        assert db.query(Meeting).count() == 0
        call = db.query(PlatformProviderCall).one()
        assert call.remote_transcript_id == "synthetic-e2e-remote"
        assert call.released_at is None
