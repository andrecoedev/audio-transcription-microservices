from src.models import Meeting, MeetingActionItem, MeetingIntelligence
from src.services.reviewed_meeting_minutes import render_markdown, reviewed_minutes
from tests.test_meetings_api import _seed_meeting


def test_minutes_use_latest_completed_intelligence_and_reviewed_actions_only(db_context):
    factory = db_context["session_factory"]
    meeting_id = _seed_meeting(factory, title="Roadmap <img src=x> & <script>")
    original = {
        "schema_version": "1", "summary": "AI summary",
        "topics": [{"description": "Planning", "evidence": []}],
        "decisions": [{"description": "Ship in May", "evidence": []}],
        "action_items": [{"description": "AI suggestion", "assignee": None, "due_date": None, "evidence": []}],
        "open_questions": [{"description": "Who owns QA?", "evidence": []}],
    }
    db = factory()
    try:
        first = MeetingIntelligence(meeting_id=meeting_id, revision=1, schema_version="1", provider="fixture",
                                    model="fixture", status="completed", result=original, source_metadata={},
                                    input_fingerprint="1" * 64)
        db.add(first)
        db.flush()
        db.add_all([
            MeetingIntelligence(meeting_id=meeting_id, revision=2, schema_version="1", provider="fixture",
                                model="fixture", status="failed", result={"summary": "partial"},
                                source_metadata={}, input_fingerprint="2" * 64),
            MeetingActionItem(meeting_id=meeting_id, description="Edited action [click](javascript:alert(1))\n## Injected\n- [ ] Attack",
                              status="open", source_revision=1, source_index=0, original_description="AI suggestion",
                              source_intelligence_id=first.id, evidence=[{"segment_order": 0, "quote": "AI suggestion"}]),
            MeetingActionItem(meeting_id=meeting_id, description="Done action", status="done"),
            MeetingActionItem(meeting_id=meeting_id, description="Dismissed task", status="dismissed"),
        ])
        db.commit()
        data = reviewed_minutes(db, db.get(Meeting, meeting_id))
        assert data["summary"] == "AI summary"
        assert data["topics"][0]["description"] == "Planning"
        assert [item["description"] for item in data["action_items"]] == [
            "Edited action [click](javascript:alert(1))\n## Injected\n- [ ] Attack", "Done action"
        ]
        assert data["action_items"][0]["source"] == "ai_reviewed"
        assert data["action_items"][0]["source_revision"] == 1
        markdown = render_markdown(data)
        assert "AI suggestion" not in markdown and "Dismissed task" not in markdown
        assert "javascript:alert" in markdown and r"\[click\]" in markdown
        assert "## Injected" not in markdown and "- [ ] Attack" not in markdown
        assert "- [x] Done action" in markdown
        assert "<img" not in markdown
        assert "&lt;img src=x&gt;" in markdown
        assert "&lt;script&gt;" in markdown
    finally:
        db.close()


def test_minutes_without_intelligence_have_empty_sections_and_download(db_context, auth_headers):
    meeting_id = _seed_meeting(db_context["session_factory"], title="Manual")
    client, headers = db_context["client"], auth_headers()
    assert client.post(f"/meetings/{meeting_id}/actions", json={"description": "Manual task"}, headers=headers).status_code == 201
    response = client.get(f"/meetings/{meeting_id}/minutes", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["summary"] == ""
    assert data["topics"] == data["decisions"] == data["open_questions"] == []
    assert data["action_items"][0]["description"] == "Manual task"
    download = client.get(f"/meetings/{meeting_id}/minutes.md", headers=headers)
    assert download.status_code == 200
    assert download.headers["content-disposition"] == f'attachment; filename="meeting-{meeting_id}-minutes.md"'
    assert "# Manual" in download.text and "Manual task" in download.text


def test_minutes_endpoints_preserve_auth_scope_and_ownership(db_context, auth_headers):
    factory, client = db_context["session_factory"], db_context["client"]
    alice_id = _seed_meeting(factory)
    bob_id = _seed_meeting(factory, user_id=2, username="bob")
    assert client.get(f"/meetings/{alice_id}/minutes").status_code == 401
    assert client.get(f"/meetings/{bob_id}/minutes", headers=auth_headers()).status_code == 404
    assert client.get(f"/meetings/{bob_id}/minutes.md", headers=auth_headers()).status_code == 404
    assert client.get(f"/meetings/{alice_id}/minutes", headers=auth_headers(scopes=["transcribe"])).status_code == 403
