from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from decimal import Decimal

from fastapi import HTTPException

from src.models import PlatformProviderBudget, PlatformProviderCall, Transcription
from src.services.platform_budget import reserve_platform_call, begin_platform_call
from tests.platform_helpers import configure_platform, confirm_test_balance


def test_concurrent_workers_respect_single_external_slot(postgres_session_factory, monkeypatch):
    configure_platform(monkeypatch)
    with postgres_session_factory() as db:
        confirm_test_balance(db)
        ids = []
        for index in range(2):
            row = Transcription(filename=f"synthetic-{index}.wav", original_filename="synthetic.wav",
                file_size_mb=0.1, duration_seconds=0, transcription_model="assemblyai", status="queued")
            db.add(row)
            db.flush()
            ids.append(row.id)
            reserve_platform_call(db, row.id, "local")
        db.commit()
    barrier = Barrier(2)

    def attempt(tid):
        with postgres_session_factory() as db:
            barrier.wait(timeout=10)
            try:
                begin_platform_call(db, tid, duration_seconds=60)
                return "attempted"
            except HTTPException as exc:
                db.rollback()
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, ids))
    assert sorted(results, key=str) == sorted(["attempted", 429], key=str)
    with postgres_session_factory() as db:
        assert db.query(PlatformProviderCall).filter_by(state="attempted").count() == 1
        assert db.get(PlatformProviderBudget, "assemblyai").reserved_cents == Decimal("4.21666668")
