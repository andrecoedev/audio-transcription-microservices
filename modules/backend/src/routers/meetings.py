"""Owner-scoped meeting views over the durable transcription result."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..authorization import enforce_transcription_access, is_admin, ownership_filter
from ..database import get_db
from ..models import Meeting, MeetingSpeaker, TranscriptionOwnership
from ..security import TokenData, require_scope
from ..services.audit import append_audit_event
from ..services.meeting_projection import ordered_segments
from ..services.transcription_deletion import ActiveTranscriptionError, delete_transcription_data

router = APIRouter(prefix="/meetings", tags=["meetings"])


class MeetingTitleUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class SpeakerNameUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)


def _get_owned_meeting(db: Session, meeting_id: int, user: TokenData) -> Meeting:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    enforce_transcription_access(db, meeting_id, user)
    return meeting


def _meeting_data(meeting: Meeting) -> dict:
    transcription = meeting.transcription
    owner = transcription.ownership
    return {
        "id": meeting.id,
        "transcription_id": transcription.id,
        "owner_user_id": owner.user_id if owner else None,
        "title": meeting.title,
        "created_at": meeting.created_at,
        "updated_at": meeting.updated_at,
        "duration_seconds": transcription.duration_seconds,
        "language": meeting.language,
        "status": transcription.status,
        "speaker_count": len(meeting.speakers),
        "speakers": [
            {"id": speaker.speaker_id, "display_name": speaker.display_name}
            for speaker in sorted(meeting.speakers, key=lambda item: item.speaker_id)
        ],
        "processing_metadata": {
            "model": transcription.transcription_model,
            "use_diarization": transcription.use_diarization,
            "processing_time_seconds": transcription.processing_time_seconds,
            "word_count": transcription.word_count,
            "job_completed_at": transcription.job.completed_at if transcription.job else None,
        },
    }


@router.get("")
def list_meetings(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: TokenData = Depends(require_scope("read_transcriptions")),
):
    query = db.query(Meeting)
    if not is_admin(user):
        query = query.join(
            TranscriptionOwnership,
            TranscriptionOwnership.transcription_id == Meeting.id,
        ).filter(
            ownership_filter(user.user_id, user.username, user.registration_source)
        )
    total = query.count()
    meetings = (
        query.order_by(Meeting.created_at.desc(), Meeting.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return {"total": total, "skip": skip, "limit": limit, "meetings": [_meeting_data(item) for item in meetings]}


@router.get("/{meeting_id}")
def get_meeting(
    meeting_id: int,
    db: Session = Depends(get_db),
    user: TokenData = Depends(require_scope("read_transcriptions")),
):
    return _meeting_data(_get_owned_meeting(db, meeting_id, user))


@router.get("/{meeting_id}/transcript")
def get_meeting_transcript(
    meeting_id: int,
    db: Session = Depends(get_db),
    user: TokenData = Depends(require_scope("read_transcriptions")),
):
    meeting = _get_owned_meeting(db, meeting_id, user)
    names = {speaker.speaker_id: speaker.display_name for speaker in meeting.speakers}
    segments = [
        {**segment, "speaker_display_name": names.get(segment.get("speaker"))}
        for segment in ordered_segments(meeting.transcription.segments)
    ]
    return {
        "meeting_id": meeting.id,
        "segments": segments,
        "text": "\n".join(segment.get("text", "") for segment in segments),
    }


@router.patch("/{meeting_id}")
def update_meeting_title(
    meeting_id: int,
    payload: MeetingTitleUpdate,
    db: Session = Depends(get_db),
    user: TokenData = Depends(require_scope("transcribe")),
):
    meeting = _get_owned_meeting(db, meeting_id, user)
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Title cannot be blank")
    meeting.title = title
    append_audit_event(
        db,
        event="meeting.title_updated",
        actor_user_id=user.user_id,
        resource_type="meeting",
        resource_id=meeting.id,
    )
    db.commit()
    db.refresh(meeting)
    return _meeting_data(meeting)


@router.patch("/{meeting_id}/speakers/{speaker_id}")
def rename_meeting_speaker(
    meeting_id: int,
    speaker_id: str,
    payload: SpeakerNameUpdate,
    db: Session = Depends(get_db),
    user: TokenData = Depends(require_scope("transcribe")),
):
    _get_owned_meeting(db, meeting_id, user)
    speaker = db.get(MeetingSpeaker, (meeting_id, speaker_id))
    if speaker is None:
        raise HTTPException(status_code=404, detail="Speaker not found")
    display_name = payload.display_name.strip()
    if not display_name:
        raise HTTPException(status_code=422, detail="Speaker name cannot be blank")
    speaker.display_name = display_name
    append_audit_event(
        db,
        event="meeting.speaker_renamed",
        actor_user_id=user.user_id,
        resource_type="meeting",
        resource_id=meeting_id,
        metadata={"speaker_id": speaker_id},
    )
    db.commit()
    return {"id": speaker.speaker_id, "display_name": speaker.display_name}


@router.delete("/{meeting_id}")
def delete_meeting(
    meeting_id: int,
    db: Session = Depends(get_db),
    user: TokenData = Depends(require_scope("delete_transcriptions")),
):
    meeting = _get_owned_meeting(db, meeting_id, user)
    try:
        delete_transcription_data(db, meeting.transcription, user.user_id)
    except ActiveTranscriptionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"message": "Meeting deleted successfully"}
