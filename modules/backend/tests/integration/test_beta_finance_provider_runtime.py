"""End-to-end finance coverage with PostgreSQL/RQ and a simulated provider."""

from datetime import timedelta
from decimal import Decimal
import os
from uuid import uuid4

import pytest

from src.config import settings
from src.models import (
    BetaAccessGrant,
    PlatformProviderBudget,
    PlatformProviderCall,
    Transcription,
    TranscriptionJob,
    TranscriptionOwnership,
    UsageEvent,
    UsagePrice,
    User,
)
from src.services.platform_budget import reserve_platform_call
from src.services.transcription_entitlements import (
    CAPABILITIES,
    now_utc,
    reserve_transcription,
)
from tests.platform_helpers import configure_platform, confirm_test_balance

pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def _explicit_test_limits(monkeypatch):
    from tests.entitlement_helpers import enable_test_policy
    enable_test_policy(monkeypatch)


def _seed_platform_job(factory, input_path, *, label):
    with factory() as db:
        user = User(
            username=f"beta-{label}-{uuid4().hex}",
            email=f"beta-finance-{uuid4().hex}@example.invalid",
            hashed_password="synthetic-fixture",
        )
        db.add(user)
        db.flush()
        db.add(BetaAccessGrant(
            id=str(uuid4()), user_id=user.id, capabilities=sorted(CAPABILITIES),
            round_id="test-round", expires_at=now_utc() + timedelta(hours=1),
        ))
        transcription = Transcription(
            filename=f"{label}.wav", original_filename=f"{label}.wav",
            file_size_mb=0.001, duration_seconds=0, transcription_model="assemblyai",
            use_diarization=True, status="queued",
        )
        db.add(transcription)
        db.flush()
        job = TranscriptionJob(
            transcription_id=transcription.id, input_path=str(input_path),
            transcription_model="assemblyai", use_diarization=True,
            credential_source="platform", status="queued",
        )
        db.add(job)
        db.add(TranscriptionOwnership(
            transcription_id=transcription.id, owner_sub=f"user:{user.id}", user_id=user.id,
        ))
        confirm_test_balance(db)
        reserve_transcription(
            db, user.id, transcription.id,
            {"provider": "assemblyai", "credential_source": "platform"},
            1, str(input_path),
        )
        reserve_platform_call(db, transcription.id, "local")
        db.commit()
        return transcription.id


class _SimulatedEngine:
    def __init__(self):
        self.model = "universal-3-5-pro"
        self.execution_observer = None
        self.usage_observer = None

    def set_execution_observer(self, callback):
        self.execution_observer = callback

    def set_usage_observer(self, callback):
        self.usage_observer = callback


class _SimulatedCloudService:
    def __init__(self, engine, factory, transcription_id, calls, *, fail_after_submission=False):
        self.engine = engine
        self.factory = factory
        self.transcription_id = transcription_id
        self.calls = calls
        self.fail_after_submission = fail_after_submission

    def _get_engine(self, _provider):
        return self.engine

    def process_transcription(self, **kwargs):
        from src.services.transcription_processing_service import ProcessingResult

        kwargs["before_inference"](60)
        self.calls.append("provider-submit")
        queued = {
            "phase": "accepted", "status": "queued", "provider_id": "synthetic-remote-42",
            "model": self.engine.model, "use_diarization": True,
        }
        self.engine.execution_observer(queued)
        # The observer must commit the remote identifier before polling continues.
        with self.factory() as db:
            call = db.query(PlatformProviderCall).filter_by(
                transcription_id=self.transcription_id,
            ).one()
            assert call.remote_transcript_id == "synthetic-remote-42"
            assert call.provider_status == "queued"
        if self.fail_after_submission:
            unknown = {**queued, "phase": "polled", "status": "unknown"}
            self.engine.usage_observer(unknown)
            self.engine.execution_observer(unknown)
            raise RuntimeError("simulated polling timeout")

        completed = {
            "phase": "polled", "status": "completed", "provider_id": "synthetic-remote-42",
            "audio_duration_seconds": 60, "model": self.engine.model,
            "use_diarization": True,
        }
        self.engine.usage_observer(completed)
        self.engine.execution_observer(completed)
        return ProcessingResult(
            segments=[{"speaker": "SPEAKER_00", "text": "synthetic result", "start": 0, "end": 1}],
            duration_seconds=60, num_speakers=1, word_count=2,
        )


def _run_real_rq(factory, monkeypatch, transcription_id, *, fail_after_submission=False, before_inference=None):
    from redis import Redis
    from rq import Queue, SimpleWorker
    from src.workers import transcription_worker

    engine = _SimulatedEngine()
    calls = []
    service = _SimulatedCloudService(
        engine, factory, transcription_id, calls,
        fail_after_submission=fail_after_submission,
    )
    if before_inference:
        original_process = service.process_transcription

        def process_with_policy_change(**kwargs):
            before_inference()
            return original_process(**kwargs)

        service.process_transcription = process_with_policy_change

    def service_factory():
        return service

    monkeypatch.setattr(transcription_worker, "SessionLocal", factory)
    monkeypatch.setattr(transcription_worker, "get_cloud_processing_service", service_factory)

    # Keep the simulated service behind the same materialization boundary as the SDK.
    connection = Redis.from_url(os.environ["P2A_TEST_REDIS_URL"])
    queue = Queue("beta-finance-" + uuid4().hex, connection=connection)
    job = queue.enqueue(transcription_worker.process_transcription_job_sync, transcription_id)
    assert SimpleWorker([queue], connection=connection).work(burst=True, logging_level="WARNING")
    job.refresh()
    return job, queue, connection, calls


def test_real_rq_revalidates_new_admin_policy_before_provider_submission(postgres_session_factory, monkeypatch, tmp_path):
    from src.services.beta_settings import read_policy, update_policy
    configure_platform(monkeypatch)
    path = tmp_path / "synthetic-paused.wav"
    path.write_bytes(b"synthetic audio")
    transcription_id = _seed_platform_job(postgres_session_factory, path, label="paused")

    def pause_round():
        with postgres_session_factory() as db:
            row, _ = read_policy(db)
            update_policy(db, section="beta", changes={"beta.enabled": False},
                version=row.configuration_version, confirmed=True, actor_user_id=None)
            db.commit()

    job, _, _, calls = _run_real_rq(postgres_session_factory, monkeypatch, transcription_id, before_inference=pause_round)
    assert job.get_status() == "failed"
    assert calls == []
    with postgres_session_factory() as db:
        assert db.get(Transcription, transcription_id).status == "failed"
        call = db.query(PlatformProviderCall).filter_by(transcription_id=transcription_id).one()
        assert call.state == "reserved" and call.released_at is not None
        assert db.get(PlatformProviderBudget, "assemblyai").reserved_cents == 0


def test_real_rq_persists_platform_result_and_usage_after_rq_record_is_deleted(
    postgres_session_factory, monkeypatch, tmp_path,
):
    if not os.getenv("P2A_TEST_REDIS_URL"):
        pytest.skip("P2A_TEST_REDIS_URL is required for the isolated real RQ integration test")
    configure_platform(monkeypatch)
    monkeypatch.setattr(settings, "AAI_PLATFORM_MODEL", "universal-3-5-pro")
    input_path = tmp_path / "synthetic-platform.wav"
    input_path.write_bytes(b"synthetic audio")
    transcription_id = _seed_platform_job(postgres_session_factory, input_path, label="success")

    job, _queue, _connection, calls = _run_real_rq(
        postgres_session_factory, monkeypatch, transcription_id,
    )
    assert job.get_status() == "finished"
    assert calls == ["provider-submit"]
    job.delete()

    with postgres_session_factory() as db:
        transcription = db.get(Transcription, transcription_id)
        call = db.query(PlatformProviderCall).filter_by(transcription_id=transcription_id).one()
        assert transcription.status == transcription.job.status == "completed"
        assert transcription.segments[0]["text"] == "synthetic result"
        assert transcription.meeting is not None
        assert call.remote_transcript_id == "synthetic-remote-42"
        assert call.provider_status == "completed"
        assert call.model == "universal-3-5-pro"
        assert call.provider_audio_seconds == Decimal("60.000")
        price = db.query(UsagePrice).filter_by(
            model="universal-3-5-pro+speakers", provider="assemblyai",
            metric="provider_audio_seconds",
        ).one()
        events = db.query(UsageEvent).filter_by(resource_id=str(transcription_id)).all()
        provider_audio = next(event for event in events if event.metric == "provider_audio_seconds")
        assert provider_audio.quantity == Decimal("60.000000000")
        assert provider_audio.use_diarization is True
        assert provider_audio.price_id == price.id
        assert not input_path.exists()


def test_rq_timeout_keeps_remote_authorization_and_never_resubmits(
    postgres_session_factory, monkeypatch, tmp_path,
):
    if not os.getenv("P2A_TEST_REDIS_URL"):
        pytest.skip("P2A_TEST_REDIS_URL is required for the isolated real RQ integration test")
    configure_platform(monkeypatch)
    monkeypatch.setattr(settings, "AAI_PLATFORM_MODEL", "universal-3-5-pro")
    input_path = tmp_path / "synthetic-timeout.wav"
    input_path.write_bytes(b"synthetic audio")
    transcription_id = _seed_platform_job(postgres_session_factory, input_path, label="timeout")

    job, _queue, _connection, calls = _run_real_rq(
        postgres_session_factory, monkeypatch, transcription_id, fail_after_submission=True,
    )
    assert job.get_status() == "failed"
    job.delete()

    with postgres_session_factory() as db:
        call = db.query(PlatformProviderCall).filter_by(transcription_id=transcription_id).one()
        assert call.remote_transcript_id == "synthetic-remote-42"
        assert call.provider_status == "unknown"
        assert call.settled_at is None
        assert call.released_at is None
        assert db.get(Transcription, transcription_id).status == "failed"
        assert db.get(Transcription, transcription_id).job.status == "failed"
        assert db.get(PlatformProviderBudget, "assemblyai").reserved_cents == call.reserved_cents

    from src.workers import transcription_worker
    with pytest.raises(RuntimeError, match="Transcription processing failed"):
        transcription_worker.process_transcription_job_sync(transcription_id)
    assert calls == ["provider-submit"]
    with postgres_session_factory() as db:
        call = db.query(PlatformProviderCall).filter_by(transcription_id=transcription_id).one()
        assert call.remote_transcript_id == "synthetic-remote-42"
        assert call.provider_status == "unknown"
