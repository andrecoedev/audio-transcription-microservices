"""Deterministic owner-scoped operations on user-managed meeting actions."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import MeetingActionItem, MeetingActionSuggestionReview, MeetingIntelligence
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


class SuggestionAccept(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    description: str | None = Field(default=None, min_length=1, max_length=4000)
    assignee: str | None = Field(default=None, max_length=255)
    due_date: date | None = None

    @field_validator("description")
    @classmethod
    def description_cannot_be_null(cls, value):
        if value is None:
            raise ValueError("description cannot be null")
        return value

    @field_validator("assignee")
    @classmethod
    def empty_assignee_is_unassigned(cls, value):
        return value or None


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


def _completed_suggestion(db, meeting_id, revision, source_index):
    intelligence = db.query(MeetingIntelligence).filter_by(
        meeting_id=meeting_id, revision=revision
    ).first()
    if intelligence is None:
        raise HTTPException(404, "Intelligence revision not found")
    if intelligence.status != "completed" or not isinstance(intelligence.result, dict):
        raise HTTPException(409, "Intelligence revision is not completed")
    suggestions = intelligence.result.get("action_items")
    if not isinstance(suggestions, list) or source_index < 0 or source_index >= len(suggestions):
        raise HTTPException(404, "Action suggestion not found")
    suggestion = suggestions[source_index]
    if not isinstance(suggestion, dict) or not isinstance(suggestion.get("description"), str):
        raise HTTPException(409, "Action suggestion is invalid")
    return intelligence, suggestion


def _review_for(db, meeting_id, revision, source_index):
    return db.query(MeetingActionSuggestionReview).filter_by(
        meeting_id=meeting_id, source_revision=revision, source_index=source_index
    ).first()


def _review_dict(review):
    return {"source_revision": review.source_revision,
            "source_index": review.source_index, "status": review.status}


@router.get("/{meeting_id}/actions")
def list_actions(meeting_id: int, db: Session = Depends(get_db),
                 user: TokenData = Depends(require_scope("read_transcriptions"))):
    _get_owned_meeting(db, meeting_id, user)
    items = db.query(MeetingActionItem).filter_by(meeting_id=meeting_id).order_by(MeetingActionItem.id).all()
    reviews = db.query(MeetingActionSuggestionReview).filter_by(meeting_id=meeting_id).order_by(
        MeetingActionSuggestionReview.source_revision, MeetingActionSuggestionReview.source_index
    ).all()
    return {"meeting_id": meeting_id, "action_items": [item.to_dict() for item in items],
            "suggestion_reviews": [_review_dict(review) for review in reviews]}


@router.post("/{meeting_id}/actions/suggestions/{revision}/{source_index}", status_code=201)
def accept_suggestion(meeting_id: int, revision: int, source_index: int, response: Response,
                      payload: SuggestionAccept | None = None, db: Session = Depends(get_db),
                      user: TokenData = Depends(require_scope("transcribe"))):
    _get_owned_meeting(db, meeting_id, user)
    intelligence, suggestion = _completed_suggestion(db, meeting_id, revision, source_index)
    review = _review_for(db, meeting_id, revision, source_index)
    if review:
        if review.status == "accepted" and review.action_id:
            item = db.get(MeetingActionItem, review.action_id)
            if item:
                response.status_code = 200
                return item.to_dict()
        raise HTTPException(409, f"Suggestion was already {review.status}")

    overrides = payload.model_dump(exclude_unset=True) if payload else {}
    item = MeetingActionItem(
        meeting_id=meeting_id,
        description=overrides.get("description", suggestion["description"]),
        assignee=overrides.get("assignee", suggestion.get("assignee")),
        # Intelligence stores a literal transcript phrase, not a normalized date.
        due_date=overrides.get("due_date"),
        source_intelligence_id=intelligence.id,
        source_revision=revision,
        source_index=source_index,
        original_description=suggestion["description"],
        original_assignee=suggestion.get("assignee"),
        original_due_date=suggestion.get("due_date"),
        evidence=suggestion.get("evidence", []),
    )
    review = MeetingActionSuggestionReview(
        meeting_id=meeting_id, source_intelligence_id=intelligence.id,
        source_revision=revision, source_index=source_index, status="accepted",
    )
    db.add(item)
    db.flush()
    review.action_id = item.id
    db.add(review)
    record_change(db, item, user, "meeting_action.created")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        prior = _review_for(db, meeting_id, revision, source_index)
        if prior and prior.status == "accepted" and prior.action_id:
            existing = db.get(MeetingActionItem, prior.action_id)
            if existing:
                response.status_code = 200
                return existing.to_dict()
        if prior:
            raise HTTPException(409, f"Suggestion was already {prior.status}")
        raise
    db.refresh(item)
    return item.to_dict()


@router.post("/{meeting_id}/actions/suggestions/{revision}/{source_index}/dismiss", status_code=200)
def dismiss_suggestion(meeting_id: int, revision: int, source_index: int,
                       db: Session = Depends(get_db),
                       user: TokenData = Depends(require_scope("transcribe"))):
    _get_owned_meeting(db, meeting_id, user)
    intelligence, _ = _completed_suggestion(db, meeting_id, revision, source_index)
    review = _review_for(db, meeting_id, revision, source_index)
    if review:
        if review.status == "dismissed":
            return _review_dict(review)
        raise HTTPException(409, f"Suggestion was already {review.status}")
    review = MeetingActionSuggestionReview(
        meeting_id=meeting_id, source_intelligence_id=intelligence.id,
        source_revision=revision, source_index=source_index, status="dismissed",
    )
    db.add(review)
    append_audit_event(db, event="meeting_action.suggestion_dismissed", actor_user_id=user.user_id,
                       resource_type="meeting_action_suggestion", resource_id=f"{revision}:{source_index}",
                       metadata={"meeting_id": meeting_id})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        prior = _review_for(db, meeting_id, revision, source_index)
        if prior and prior.status == "dismissed":
            return _review_dict(prior)
        if prior:
            raise HTTPException(409, f"Suggestion was already {prior.status}")
        raise
    return _review_dict(review)


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
    if item.source_intelligence_id is not None:
        review = _review_for(db, meeting_id, item.source_revision, item.source_index)
        if review:
            review.status = "deleted"
            review.action_id = None
    record_change(db, item, user, "meeting_action.deleted")
    db.delete(item)
    db.commit()
    return Response(status_code=204)
