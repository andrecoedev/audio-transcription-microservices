"""Private, owner-scoped usage history and summaries."""

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import UsageEvent
from ..security import TokenData, get_authenticated_user

router = APIRouter(prefix="/usage", tags=["usage"])

_FILTERS = {"after", "before", "provider", "credential_source", "resource_type", "limit", "offset"}
_PROVIDERS = Literal["assemblyai", "gemini", "whisper", "object_storage"]
_CREDENTIAL_SOURCES = Literal["user", "platform", "local", "none"]
_RESOURCE_TYPES = Literal["meeting", "transcription", "object"]
_MAX_WINDOW = timedelta(days=366)
_MAX_OFFSET = 10_000


def _time_window(after: datetime | None, before: datetime | None):
    now = datetime.now(timezone.utc)
    if after is not None and (after.tzinfo is None or after.utcoffset() is None):
        raise HTTPException(422, "after must include a timezone")
    if before is not None and (before.tzinfo is None or before.utcoffset() is None):
        raise HTTPException(422, "before must include a timezone")
    end = before.astimezone(timezone.utc) if before is not None else now
    start = after.astimezone(timezone.utc) if after is not None else end - timedelta(days=30)
    if end <= start:
        raise HTTPException(422, "before must be later than after")
    if end - start > _MAX_WINDOW:
        raise HTTPException(422, "Usage date range cannot exceed 366 days")
    return start, end


def _base_query(db: Session, user: TokenData, start: datetime, end: datetime):
    if user.user_id is None:
        raise HTTPException(401, "Authenticated user identity is required")
    return db.query(UsageEvent).filter(
        UsageEvent.user_id == user.user_id,
        UsageEvent.occurred_at >= start,
        UsageEvent.occurred_at < end,
    )


def _apply_filters(query, provider, credential_source, resource_type):
    if provider is not None:
        query = query.filter(UsageEvent.provider == provider)
    if credential_source is not None:
        query = query.filter(UsageEvent.credential_source == credential_source)
    if resource_type is not None:
        query = query.filter(UsageEvent.resource_type == resource_type)
    return query


def _validate_query_keys(request: Request, *, paginated: bool):
    allowed = _FILTERS if paginated else _FILTERS - {"limit", "offset"}
    unknown = set(request.query_params) - allowed
    if unknown:
        raise HTTPException(422, "Unsupported usage filter")


def _decimal_string(value):
    return str(value) if value is not None else None


def _datetime_string(value):
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _event_view(row: UsageEvent):
    return {
        "id": row.id,
        "operation_id": row.operation_id,
        "resource_type": row.resource_type,
        "resource_id": row.resource_id,
        "operation": row.operation,
        "provider": row.provider,
        "credential_source": row.credential_source,
        "metric": row.metric,
        "unit": row.unit,
        "quantity": _decimal_string(row.quantity),
        "status": row.status,
        "occurred_at": _datetime_string(row.occurred_at),
        "measurement_source": row.measurement_source,
        "model": row.model,
        "use_diarization": row.use_diarization,
        "price_id": row.price_id,
        "currency": row.currency,
        "estimated_cost": _decimal_string(row.estimated_cost),
        "cost_scope": row.cost_scope,
        "cost_reason": row.cost_reason,
    }


@router.get("/events")
def list_usage_events(
    request: Request,
    after: datetime | None = None,
    before: datetime | None = None,
    provider: _PROVIDERS | None = None,
    credential_source: _CREDENTIAL_SOURCES | None = None,
    resource_type: _RESOURCE_TYPES | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=_MAX_OFFSET),
    db: Session = Depends(get_db),
    user: TokenData = Depends(get_authenticated_user),
):
    _validate_query_keys(request, paginated=True)
    start, end = _time_window(after, before)
    query = _apply_filters(_base_query(db, user, start, end), provider, credential_source, resource_type)
    total = query.count()
    rows = query.order_by(UsageEvent.occurred_at.desc(), UsageEvent.id.desc()).offset(offset).limit(limit).all()
    return {
        "events": [_event_view(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "after": start.isoformat(),
        "before": end.isoformat(),
    }


@router.get("/summary")
def summarize_usage(
    request: Request,
    after: datetime | None = None,
    before: datetime | None = None,
    provider: _PROVIDERS | None = None,
    credential_source: _CREDENTIAL_SOURCES | None = None,
    resource_type: _RESOURCE_TYPES | None = None,
    db: Session = Depends(get_db),
    user: TokenData = Depends(get_authenticated_user),
):
    _validate_query_keys(request, paginated=False)
    start, end = _time_window(after, before)
    dimensions = (
        UsageEvent.provider, UsageEvent.credential_source, UsageEvent.resource_type,
        UsageEvent.operation, UsageEvent.metric, UsageEvent.unit,
        UsageEvent.currency, UsageEvent.cost_scope,
    )
    query = _apply_filters(_base_query(db, user, start, end), provider, credential_source, resource_type)
    rows = query.with_entities(
        *dimensions,
        func.count(UsageEvent.id).label("event_count"),
        func.count(UsageEvent.quantity).label("known_quantity_count"),
        func.sum(UsageEvent.quantity).label("quantity_total"),
        func.sum(case((UsageEvent.quantity.is_(None), 1), else_=0)).label("unknown_quantity_count"),
        func.count(UsageEvent.estimated_cost).label("known_cost_count"),
        func.sum(UsageEvent.estimated_cost).label("estimated_cost_total"),
        func.sum(case((UsageEvent.estimated_cost.is_(None), 1), else_=0)).label("unknown_cost_count"),
    ).group_by(*dimensions).order_by(*dimensions).all()

    groups = []
    for row in rows:
        groups.append({
            "provider": row.provider,
            "credential_source": row.credential_source,
            "resource_type": row.resource_type,
            "operation": row.operation,
            "metric": row.metric,
            "unit": row.unit,
            "currency": row.currency,
            "cost_scope": row.cost_scope,
            "event_count": row.event_count,
            "known_quantity_count": row.known_quantity_count,
            "unknown_quantity_count": row.unknown_quantity_count,
            "quantity_total": _decimal_string(row.quantity_total),
            "known_cost_count": row.known_cost_count,
            "unknown_cost_count": row.unknown_cost_count,
            "estimated_cost_total": _decimal_string(row.estimated_cost_total),
        })
    return {"groups": groups, "after": start.isoformat(), "before": end.isoformat()}
