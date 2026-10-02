"""Deterministic owner-scoped operations on user-managed meeting actions."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import MeetingActionItem
from ..security import TokenData, require_scope
from ..services.audit import append_audit_event
from .meetings import _get_owned_meeting

router = APIRouter(prefix="/meetings", tags=["meeting actions"])
ActionStatus = Literal["open", "done", "dismissed"]


class ActionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    description: str = Field(min_length=1, max_length=4000)
    assignee: str | None = Field(default=None, max_length=255)
    due_date: date | None = None

    @field_validator("assignee")
    @classmethod
    def empty_assignee_is_unassigned(cls, value):
        return value or None


class ActionUpdate(ActionCreate):
    description: str | None = Field(default=None, min_length=1, max_length=4000)
    status: ActionStatus | None = None

    @field_validator("description", "status")
    @classmethod
    def required_fields_cannot_be_cleared(cls, value):
        if value is None:
            raise ValueError("This field cannot be null")
        return value


def owned_action(db, meeting_id, action_id, user):
    _get_owned_meeting(db, meeting_id, user)
    item = db.query(MeetingActionItem).filter_by(id=action_id, meeting_id=meeting_id).first()
    if item is None:
        raise HTTPException(404, "Action item not found")
    return item


def record_change(db, item, user, event):
    append_audit_event(db, event=event, actor_user_id=user.user_id,
                       resource_type="meeting_action_item", resource_id=item.id,
                       metadata={"meeting_id": item.meeting_id})


@router.get("/{meeting_id}/actions")
def list_actions(meeting_id: int, db: Session = Depends(get_db),
                 user: TokenData = Depends(require_scope("read_transcriptions"))):
    _get_owned_meeting(db, meeting_id, user)
    items = db.query(MeetingActionItem).filter_by(meeting_id=meeting_id).order_by(MeetingActionItem.id).all()
    return {"meeting_id": meeting_id, "action_items": [item.to_dict() for item in items]}


@router.post("/{meeting_id}/actions", status_code=201)
def create_action(meeting_id: int, payload: ActionCreate, db: Session = Depends(get_db),
                  user: TokenData = Depends(require_scope("transcribe"))):
    _get_owned_meeting(db, meeting_id, user)
    item = MeetingActionItem(meeting_id=meeting_id, **payload.model_dump())
    db.add(item)
    db.flush()
    record_change(db, item, user, "meeting_action.created")
    db.commit()
    db.refresh(item)
    return item.to_dict()


@router.patch("/{meeting_id}/actions/{action_id}")
def update_action(meeting_id: int, action_id: int, payload: ActionUpdate,
                  db: Session = Depends(get_db), user: TokenData = Depends(require_scope("transcribe"))):
    item = owned_action(db, meeting_id, action_id, user)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(422, "At least one field is required")
    for field, value in changes.items():
        setattr(item, field, value)
    record_change(db, item, user, "meeting_action.updated")
    db.commit()
    db.refresh(item)
    return item.to_dict()


@router.delete("/{meeting_id}/actions/{action_id}", status_code=204)
def delete_action(meeting_id: int, action_id: int, db: Session = Depends(get_db),
                  user: TokenData = Depends(require_scope("delete_transcriptions"))):
    item = owned_action(db, meeting_id, action_id, user)
    record_change(db, item, user, "meeting_action.deleted")
    db.delete(item)
    db.commit()
    return Response(status_code=204)
