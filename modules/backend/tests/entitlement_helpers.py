"""Explicit synthetic beta/policies for positive legacy regression fixtures.

No permission bypass: production policy and reservation code still execute.
New negative-policy tests deliberately remove these grants/disable readiness.
"""
import json
from datetime import timedelta
from uuid import uuid4

from src.config import settings
from src.models import BetaAccessGrant
from src.services.transcription_entitlements import CAPABILITIES, now_utc, reserve_transcription


def enable_test_policy(monkeypatch):
    policy = {"monthly_usagi_seconds": 36000, "max_audio_seconds": 600,
              "max_stored_bytes": 1024 * 1024 * 1024, "max_queued_jobs": 100, "max_processing_jobs": 10}
    monkeypatch.setattr(settings, "PLAN_POLICIES_JSON", json.dumps({k: policy for k in ("free", "starter", "business", "beta")}))
    monkeypatch.setattr(settings, "LOCAL_TRANSCRIPTION_ENABLED", True)
    monkeypatch.setattr(settings, "LOCAL_TRANSCRIPTION_HOMOLOGATED", True)


def grant_test_beta(db, user_id):
    db.add(BetaAccessGrant(id=str(uuid4()), user_id=user_id, capabilities=sorted(CAPABILITIES),
        expires_at=now_utc() + timedelta(hours=1)))
    db.flush()


def reserve_test_job(db, job, user_id=1):
    return reserve_transcription(db, user_id, job.transcription_id,
        {"provider": job.transcription_model, "credential_source": job.credential_source or "platform"},
        0, "object:" + job.input_object_key if job.input_object_key else job.input_path)


def authorize_mock(kwargs, duration_seconds=1):
    """Make worker fakes cross the same inference-admission boundary as engines."""
    callback = kwargs.get("before_inference")
    if callback is not None:
        callback(duration_seconds)


def start_test_reservation(db, transcription_id, duration_seconds=1):
    from src.services.transcription_entitlements import (
        authorize_inference,
        claim_reservation,
        reservation_for,
    )

    row = reservation_for(db, transcription_id)
    if row is not None and row.state == "queued":
        claim_reservation(db, transcription_id)
        db.flush()
    authorize_inference(db, transcription_id, duration_seconds)
