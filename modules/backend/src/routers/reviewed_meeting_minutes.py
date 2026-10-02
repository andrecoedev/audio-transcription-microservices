"""Owner-scoped deterministic meeting minutes and Markdown download."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..security import TokenData, require_scope
from ..services.reviewed_meeting_minutes import render_markdown, reviewed_minutes
from .meetings import _get_owned_meeting

router = APIRouter(prefix="/meetings", tags=["meeting minutes"])


@router.get("/{meeting_id}/minutes")
def get_reviewed_minutes(
    meeting_id: int,
    db: Session = Depends(get_db),
    user: TokenData = Depends(require_scope("read_transcriptions")),
):
    meeting = _get_owned_meeting(db, meeting_id, user)
    return reviewed_minutes(db, meeting)


@router.get("/{meeting_id}/minutes.md")
def download_reviewed_minutes(
    meeting_id: int,
    db: Session = Depends(get_db),
    user: TokenData = Depends(require_scope("read_transcriptions")),
):
    meeting = _get_owned_meeting(db, meeting_id, user)
    minutes = reviewed_minutes(db, meeting)
    return Response(
        content=render_markdown(minutes),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="meeting-{meeting_id}-minutes.md"'},
    )
