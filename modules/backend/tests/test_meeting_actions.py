import pytest

from src.models import AuditEvent, MeetingActionItem, MeetingIntelligence
from tests.test_meetings_api import _seed_meeting
from src.models import User
from src.services.privacy import erase_user_data, export_user_data


def test_manual_action_lifecycle_and_explicit_nulls(db_context, auth_headers):
    meeting_id = _seed_meeting(db_context["session_factory"])
    client, headers = db_context["client"], auth_headers()
    path = f"/meetings/{meeting_id}/actions"
    created = client.post(path, json={"description": "  Enviar relatório  "}, headers=headers)
    assert created.status_code == 201
    item = created.json()
    assert item["source"] == "manual" and item["status"] == "open"
    assert item["description"] == "Enviar relatório"
    assert item["assignee"] is None and item["due_date"] is None
    assert item["created_at"] and item["updated_at"]
    url = f"{path}/{item['id']}"
    updated = client.patch(url, json={"assignee": " Bruno ", "due_date": "2026-10-05"}, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["assignee"] == "Bruno"
    assert updated.json()["due_date"] == "2026-10-05"
    assert updated.json()["description"] == item["description"]
    cleared = client.patch(url, json={"assignee": None, "due_date": None, "description": "Enviar versão final"}, headers=headers)
    assert cleared.status_code == 200
    for status in ("done", "open", "dismissed", "open"):
        assert client.patch(url, json={"status": status}, headers=headers).status_code == 200
        persisted = client.get(path, headers=headers).json()["action_items"][0]
        assert persisted["status"] == status
        assert persisted["assignee"] is None and persisted["due_date"] is None
        assert persisted["description"] == "Enviar versão final"
    db = db_context["session_factory"]()
    try:
        assert db.query(MeetingIntelligence).count() == 0
        events = db.query(AuditEvent).filter(AuditEvent.event.like("meeting_action.%")).all()
        assert events and all(event.event_metadata == {"meeting_id": meeting_id} for event in events)
    finally:
        db.close()
    assert client.delete(url, headers=headers).status_code == 204
    assert client.get(path, headers=headers).json()["action_items"] == []
    assert client.delete(url, headers=headers).status_code == 404


@pytest.mark.parametrize("changes", [
    {"description": "   "}, {"description": None}, {"description": "x" * 4001},
    {"assignee": "x" * 256}, {"due_date": "2026-02-30"},
    {"status": "pending"}, {"status": None}, {"meeting_id": 99}, {},
])
def test_invalid_updates_do_not_change_state(db_context, auth_headers, changes):
    meeting_id = _seed_meeting(db_context["session_factory"])
    client, headers = db_context["client"], auth_headers()
    path = f"/meetings/{meeting_id}/actions"
    original = client.post(path, json={"description": "Original"}, headers=headers).json()
    assert client.patch(f"{path}/{original['id']}", json=changes, headers=headers).status_code == 422
    assert client.get(path, headers=headers).json()["action_items"] == [original]


def test_actions_require_ownership_scopes_and_matching_meeting(db_context, auth_headers):
    factory, client = db_context["session_factory"], db_context["client"]
    alice_id = _seed_meeting(factory)
    bob_id = _seed_meeting(factory, user_id=2, username="bob")
    another_alice_id = _seed_meeting(factory)
    path = f"/meetings/{alice_id}/actions"
    alice, bob = auth_headers(), auth_headers("bob")
    item = client.post(path, json={"description": "Privada"}, headers=alice).json()
    assert client.get(path).status_code == 401
    assert client.get(path, headers=bob).status_code == 404
    assert client.post(path, json={"description": "Invasão"}, headers=bob).status_code == 404
    assert client.patch(f"{path}/{item['id']}", json={"status": "done"}, headers=bob).status_code == 404
    assert client.delete(f"{path}/{item['id']}", headers=bob).status_code == 404
    for other_id, headers in ((bob_id, bob), (another_alice_id, alice)):
        wrong_url = f"/meetings/{other_id}/actions/{item['id']}"
        assert client.patch(wrong_url, json={"description": "Wrong meeting"}, headers=headers).status_code == 404
        assert client.delete(wrong_url, headers=headers).status_code == 404
    read_only = auth_headers(scopes=["read_transcriptions"])
    assert client.post(path, json={"description": "Denied"}, headers=read_only).status_code == 403
    assert client.patch(f"{path}/{item['id']}", json={"status": "done"}, headers=read_only).status_code == 403
    assert client.delete(f"{path}/{item['id']}", headers=read_only).status_code == 403
    assert client.get("/meetings/999999/actions", headers=alice).status_code == 404


@pytest.mark.parametrize("resource", ["meetings", "transcriptions"])
def test_meeting_or_transcription_deletion_cascades_actions(db_context, auth_headers, resource):
    meeting_id = _seed_meeting(db_context["session_factory"])
    client, headers = db_context["client"], auth_headers()
    path = f"/meetings/{meeting_id}/actions"
    assert client.post(path, json={"description": "Descartar junto"}, headers=headers).status_code == 201
    assert client.delete(f"/{resource}/{meeting_id}", headers=headers).status_code == 200
    assert client.get(path, headers=headers).status_code == 404
    db = db_context["session_factory"]()
    try:
        assert db.query(MeetingActionItem).count() == 0
    finally:
        db.close()


def test_editing_actions_preserves_completed_ai_revision(db_context, auth_headers):
    factory = db_context["session_factory"]
    meeting_id = _seed_meeting(factory)
    original = {"schema_version": "1", "summary": "Original", "topics": [], "decisions": [], "action_items": [], "open_questions": []}
    db = factory()
    db.add(MeetingIntelligence(meeting_id=meeting_id, revision=1, schema_version="1", provider="fixture",
                               model="fixture", status="completed", result=original, source_metadata={}, input_fingerprint="0" * 64))
    db.commit()
    db.close()
    client, headers = db_context["client"], auth_headers()
    path = f"/meetings/{meeting_id}/actions"
    item = client.post(path, json={"description": "Manual"}, headers=headers).json()
    client.patch(f"{path}/{item['id']}", json={"description": "Human edit", "status": "done"}, headers=headers)
    db = factory()
    try:
        assert db.query(MeetingIntelligence).one().result == original
        assert db.query(MeetingActionItem).one().description == "Human edit"
    finally:
        db.close()


def test_privacy_export_and_erasure_include_owned_actions(db_context, auth_headers):
    factory = db_context["session_factory"]
    meeting_id = _seed_meeting(factory)
    bob_meeting = _seed_meeting(factory, user_id=2, username="bob")
    db = factory()
    try:
        db.add_all([MeetingActionItem(meeting_id=meeting_id, description="Owned"),
                    MeetingActionItem(meeting_id=bob_meeting, description="Private to Bob")])
        db.commit()
        user = db.get(User, 1)
        exported = export_user_data(db, user)
        assert len(exported["transcriptions"]) == 1
        assert exported["transcriptions"][0]["meeting"]["action_items"][0]["description"] == "Owned"
        erase_user_data(db, user)
        assert [item.description for item in db.query(MeetingActionItem).all()] == ["Private to Bob"]
    finally:
        db.close()
