"""ML-free snapshots and representations shared with HTTP and Worker."""

import hashlib
import json

from ..models import MeetingIntelligence
from .meeting_projection import ordered_segments


def snapshot(meeting) -> tuple[dict, list[dict]]:
    metadata = {
        "title": meeting.title,
        "language": meeting.language,
        "speakers": [{"id": item.speaker_id, "display_name": item.display_name}
                     for item in sorted(meeting.speakers, key=lambda item: item.speaker_id)],
    }
    return metadata, ordered_segments(meeting.transcription.segments)


def fingerprint(metadata: dict, segments: list[dict]) -> str:
    content = json.dumps({"metadata": metadata, "segments": segments}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()


def metadata_view(row: MeetingIntelligence) -> dict:
    return {key: getattr(row, key) for key in (
        "id", "meeting_id", "revision", "schema_version", "provider", "model", "status",
        "error_message", "created_at", "updated_at", "started_at", "completed_at", "input_fingerprint",
    )}


def latest_revision(db, meeting_id):
    return db.query(MeetingIntelligence).filter_by(meeting_id=meeting_id).order_by(MeetingIntelligence.revision.desc()).first()
