"""Actual PostgreSQL persistence, constraints and cascade for manual actions."""

from datetime import date
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from src.database import get_db
from src.models import MeetingActionItem, MeetingActionSuggestionReview, MeetingIntelligence, User
from src.routers import meeting_actions, meetings
from tests.test_meetings_api import _seed_meeting

pytestmark = pytest.mark.postgres


def test_actions_http_persist_dates_and_cascade_in_postgresql(postgres_session_factory, auth_headers):
    factory = postgres_session_factory
    db = factory()
    db.add_all([User(id=1, username="alice", email="alice@example.test", hashed_password="unused"),
                User(id=2, username="bob", email="bob@example.test", hashed_password="unused")])
    db.commit()
    db.close()
    meeting_id = _seed_meeting(factory)
    app = FastAPI()
    app.include_router(meeting_actions.router)
    app.include_router(meetings.router)

    def database():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        path = f"/meetings/{meeting_id}/actions"
        headers = auth_headers()
        created = client.post(path, json={"description": "Manual", "due_date": "2026-10-05"}, headers=headers)
        assert created.status_code == 201
        action_id = created.json()["id"]
        assert client.patch(f"{path}/{action_id}", json={"status": "done"}, headers=headers).status_code == 200
        assert client.get(path, headers=auth_headers("bob")).status_code == 404
        assert client.get(path, headers=headers).json()["action_items"][0]["status"] == "done"
        db = factory()
        item = db.get(MeetingActionItem, action_id)
        assert item.due_date == date(2026, 10, 5)
        assert item.created_at.tzinfo and item.updated_at.tzinfo
        db.close()
        assert client.delete(f"/meetings/{meeting_id}", headers=headers).status_code == 200
        db = factory()
        assert db.get(MeetingActionItem, action_id) is None
        db.close()


@pytest.mark.parametrize("description,status", [("", "open"), ("   ", "open"), ("Valid", "invalid")])
def test_postgresql_enforces_action_constraints(postgres_session_factory, description, status):
    meeting_id = _seed_meeting(postgres_session_factory, user_id=None)
    db = postgres_session_factory()
    try:
        db.add(MeetingActionItem(meeting_id=meeting_id, description=description, status=status))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        assert db.query(MeetingActionItem).count() == 0
    finally:
        db.close()


def test_concurrent_accept_of_one_suggestion_is_idempotent(postgres_session_factory, auth_headers):
    factory = postgres_session_factory
    db = factory()
    db.add_all([User(id=1, username="alice", email="alice@example.test", hashed_password="unused")])
    db.commit()
    db.close()
    meeting_id = _seed_meeting(factory)
    db = factory()
    db.add(MeetingIntelligence(
        meeting_id=meeting_id, revision=1, schema_version="1", provider="fixture", model="fixture",
        status="completed", result={"schema_version": "1", "summary": "fixture", "topics": [],
                                     "decisions": [], "open_questions": [], "action_items": [
                                         {"description": "Send slides", "assignee": None,
                                          "due_date": None, "evidence": []}]},
        source_metadata={}, input_fingerprint="a" * 64,
    ))
    db.commit()
    db.close()
    app = FastAPI()
    app.include_router(meeting_actions.router)
    app.include_router(meetings.router)

    def database():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = database
    headers = auth_headers()
    path = f"/meetings/{meeting_id}/actions/suggestions/1/0"
    with TestClient(app) as client:
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: client.post(path, headers=headers), range(2)))
    assert all(response.status_code in (200, 201) for response in responses)
    assert responses[0].json()["id"] == responses[1].json()["id"]
    db = factory()
    try:
        assert db.query(MeetingActionItem).filter_by(meeting_id=meeting_id).count() == 1
        assert db.query(MeetingActionSuggestionReview).filter_by(meeting_id=meeting_id).count() == 1
    finally:
        db.close()
