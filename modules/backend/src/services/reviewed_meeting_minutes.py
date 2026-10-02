"""Deterministic projection and Markdown rendering for reviewed meeting minutes."""

from __future__ import annotations

from html import escape as escape_html
import re

from ..models import Meeting, MeetingActionItem, MeetingIntelligence


def reviewed_minutes(db, meeting: Meeting) -> dict:
    """Combine immutable latest AI content with operational, non-dismissed actions."""
    intelligence = (
        db.query(MeetingIntelligence)
        .filter_by(meeting_id=meeting.id, status="completed")
        .order_by(MeetingIntelligence.revision.desc())
        .first()
    )
    content = intelligence.result if intelligence and isinstance(intelligence.result, dict) else {}
    raw_actions = (
        db.query(MeetingActionItem)
        .filter(
            MeetingActionItem.meeting_id == meeting.id,
            MeetingActionItem.status.in_(("open", "done")),
        )
        .order_by(MeetingActionItem.id)
        .all()
    )
    return {
        "meeting_id": meeting.id,
        "title": meeting.title,
        "created_at": meeting.created_at.isoformat() if meeting.created_at else None,
        "summary": content.get("summary", "") or "",
        "topics": content.get("topics", []) or [],
        "decisions": content.get("decisions", []) or [],
        "action_items": [
            {
                "id": item.id,
                "description": item.description,
                "assignee": item.assignee,
                "due_date": item.due_date.isoformat() if item.due_date else None,
                "status": item.status,
                "source": "ai_reviewed" if item.source_intelligence_id is not None else "manual",
                "source_intelligence_id": item.source_intelligence_id,
                "source_revision": item.source_revision,
                "source_index": item.source_index,
            }
            for item in raw_actions
        ],
        "open_questions": content.get("open_questions", []) or [],
    }


def _plain_markdown_text(value) -> str:
    """Render untrusted text as inert inline Markdown and keep it on one line."""
    # Markdown backslashes do not neutralize raw HTML tags, so encode HTML
    # delimiters/entities first, then escape Markdown's inline syntax.
    text = escape_html(" ".join(str(value).split()), quote=False)
    return re.sub(r"([\\`*_{}\[\]<>()#+.!|~-])", r"\\\1", text)


def _section_items(lines: list[str], values) -> None:
    if not isinstance(values, list):
        values = []
    for value in values:
        if isinstance(value, dict):
            value = value.get("description")
        if value is not None:
            lines.append(f"- {_plain_markdown_text(value)}")
    if not values:
        lines.append("- None")


def render_markdown(minutes: dict) -> str:
    """Produce Markdown from the exact reviewed projection returned by the API."""
    lines = [f"# {_plain_markdown_text(minutes['title'])}", ""]
    if minutes.get("created_at"):
        lines.extend([f"Date: {_plain_markdown_text(minutes['created_at'])}", ""])
    lines.extend(["## Summary", "", _plain_markdown_text(minutes.get("summary", "")) or "None", ""])
    lines.extend(["## Topics", ""])
    _section_items(lines, minutes.get("topics"))
    lines.extend(["", "## Decisions", ""])
    _section_items(lines, minutes.get("decisions"))
    lines.extend(["", "## Action Items", ""])
    actions = minutes.get("action_items") or []
    for action in actions:
        marker = "x" if action["status"] == "done" else " "
        details = [_plain_markdown_text(action["description"])]
        if action.get("assignee"):
            details.append(_plain_markdown_text(action["assignee"]))
        if action.get("due_date"):
            details.append(_plain_markdown_text(action["due_date"]))
        lines.append(f"- [{marker}] " + " — ".join(details))
    if not actions:
        lines.append("- None")
    lines.extend(["", "## Open Questions", ""])
    _section_items(lines, minutes.get("open_questions"))
    return "\n".join(lines).rstrip() + "\n"
