"""UID provisioning race on real disposable PostgreSQL, no provider calls."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
import time
import pytest
from src.models import User, FirebaseIdentity
from src.services import firebase_identity

pytestmark = pytest.mark.postgres


def test_concurrent_first_google_logins_create_one_internal_user(postgres_session_factory, monkeypatch):
    identity = firebase_identity.VerifiedFirebaseIdentity('synthetic-project-123',
        'synthetic-concurrent-uid', 'concurrent@example.test', int(time.time()))
    real_find = firebase_identity.find_firebase_user
    barrier, lock = Barrier(2), Lock()
    initial_calls = 0
    def find(db, verified):
        nonlocal initial_calls
        result = real_find(db, verified)
        with lock:
            initial_calls += 1
            initial = initial_calls <= 2
        if initial:
            assert result is None
            barrier.wait(timeout=10)
        return result
    monkeypatch.setattr(firebase_identity, 'find_firebase_user', find)
    def login():
        db = postgres_session_factory()
        try:
            user, created = firebase_identity.resolve_firebase_user(db, identity)
            user_id = user.id
            db.commit()
            return user_id, created
        finally:
            db.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(login) for _ in range(2)]
        results = [future.result(timeout=20) for future in futures]
    assert results[0][0] == results[1][0]
    assert sum(created for _, created in results) == 1
    db = postgres_session_factory()
    try:
        assert db.query(User).count() == db.query(FirebaseIdentity).count() == 1
    finally:
        db.close()
