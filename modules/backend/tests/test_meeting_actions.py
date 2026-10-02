import pytest

from src.models import AuditEvent, MeetingActionItem, MeetingActionSuggestionReview, MeetingIntelligence
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


def _seed_intelligence(factory, meeting_id, revision=1, suggestions=None):
    result = {"schema_version": "1", "summary": "Original", "topics": [], "decisions": [],
              "action_items": suggestions if suggestions is not None else [
                  {"description": "Enviar slides", "assignee": "Bruno", "due_date": "na próxima semana",
                   "evidence": [{"segment_order": 10, "quote": "Enviar slides na próxima semana"}]}
              ], "open_questions": []}
    db = factory()
    try:
        row = MeetingIntelligence(meeting_id=meeting_id, revision=revision, schema_version="1",
                                  provider="fixture", model="fixture", status="completed", result=result,
                                  source_metadata={}, input_fingerprint=str(revision) * 64)
        db.add(row)
        db.commit()
    finally:
        db.close()


def test_ai_suggestion_accept_preserves_provenance_and_is_idempotent(db_context, auth_headers):
    factory = db_context["session_factory"]
    meeting_id = _seed_meeting(factory)
    _seed_intelligence(factory, meeting_id)
    client, headers = db_context["client"], auth_headers()
    path = f"/meetings/{meeting_id}/actions/suggestions/1/0"
    accepted = client.post(path, json={"description": "Enviar slides finais", "due_date": "2026-10-05"}, headers=headers)
    assert accepted.status_code == 201
    item = accepted.json()
    assert item["description"] == "Enviar slides finais" and item["assignee"] == "Bruno"
    assert item["due_date"] == "2026-10-05"
    assert item["source"] == "ai_reviewed" and item["source_revision"] == 1 and item["source_index"] == 0
    assert item["original_description"] == "Enviar slides"
    assert item["original_due_date"] == "na próxima semana"
    assert item["evidence"] == [{"segment_order": 10, "quote": "Enviar slides na próxima semana"}]
    again = client.post(path, json={"description": "different retry"}, headers=headers)
    assert again.status_code == 200 and again.json()["id"] == item["id"]
    db = factory()
    try:
        assert db.query(MeetingActionItem).count() == 1
        assert db.query(MeetingActionSuggestionReview).one().status == "accepted"
        assert db.query(MeetingIntelligence).one().result["action_items"][0]["description"] == "Enviar slides"
    finally:
        db.close()


def test_suggestion_dismissal_persists_and_cannot_be_reaccepted(db_context, auth_headers):
    factory = db_context["session_factory"]
    meeting_id = _seed_meeting(factory)
    _seed_intelligence(factory, meeting_id)
    client, headers = db_context["client"], auth_headers()
    path = f"/meetings/{meeting_id}/actions/suggestions/1/0"
    dismissed = client.post(path + "/dismiss", headers=headers)
    assert dismissed.status_code == 200 and dismissed.json()["status"] == "dismissed"
    assert client.post(path + "/dismiss", headers=headers).json() == dismissed.json()
    assert client.post(path, headers=headers).status_code == 409
    listing = client.get(f"/meetings/{meeting_id}/actions", headers=headers).json()
    assert listing["action_items"] == []
    assert listing["suggestion_reviews"] == [{"source_revision": 1, "source_index": 0, "status": "dismissed"}]


def test_ai_action_delete_is_physical_but_review_tombstone_prevents_duplicate(db_context, auth_headers):
    factory = db_context["session_factory"]
    meeting_id = _seed_meeting(factory)
    _seed_intelligence(factory, meeting_id)
    client, headers = db_context["client"], auth_headers()
    suggestion_path = f"/meetings/{meeting_id}/actions/suggestions/1/0"
    item = client.post(suggestion_path, headers=headers).json()
    assert client.delete(f"/meetings/{meeting_id}/actions/{item['id']}", headers=headers).status_code == 204
    assert client.post(suggestion_path, headers=headers).status_code == 409
    listing = client.get(f"/meetings/{meeting_id}/actions", headers=headers).json()
    assert listing["action_items"] == []
    assert listing["suggestion_reviews"][0]["status"] == "deleted"
    db = factory()
    try:
        assert db.query(MeetingActionItem).count() == 0
    finally:
        db.close()


def test_suggestion_provenance_is_server_derived_and_revision_scoped(db_context, auth_headers):
    factory = db_context["session_factory"]
    meeting_id = _seed_meeting(factory)
    _seed_intelligence(factory, meeting_id, revision=1)
    _seed_intelligence(factory, meeting_id, revision=2, suggestions=[
        {"description": "Reformulated", "assignee": None, "due_date": None, "evidence": []}
    ])
    client, headers = db_context["client"], auth_headers()
    path = f"/meetings/{meeting_id}/actions/suggestions"
    assert client.post(f"{path}/999/0", headers=headers).status_code == 404
    assert client.post(f"{path}/2/1", headers=headers).status_code == 404
    assert client.post(f"{path}/2/0", headers=headers, json={"source_revision": 1}).status_code == 422
    old = client.post(f"{path}/1/0", headers=headers).json()
    client.post(f"{path}/2/0", headers=headers)
    listing = client.get(f"/meetings/{meeting_id}/actions", headers=headers).json()
    by_revision = {item["source_revision"]: item for item in listing["action_items"]}
    assert by_revision[1]["description"] == "Enviar slides"
    assert by_revision[1]["original_description"] == "Enviar slides"
    assert by_revision[2]["description"] == "Reformulated"
    assert by_revision[1]["id"] == old["id"]


def test_other_owner_cannot_accept_or_dismiss_suggestion(db_context, auth_headers):
    factory, client = db_context["session_factory"], db_context["client"]
    meeting_id = _seed_meeting(factory)
    _seed_intelligence(factory, meeting_id)
    path = f"/meetings/{meeting_id}/actions/suggestions/1/0"
    assert client.post(path, headers=auth_headers("bob")).status_code == 404
    assert client.post(path + "/dismiss", headers=auth_headers("bob")).status_code == 404
    assert client.post(path, headers=auth_headers()).status_code == 201


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
