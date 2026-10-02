"""Persistent local authentication endpoints."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..security import TokenData, create_access_token, get_authenticated_user
from ..services.audit import append_audit_event
from ..services.identity import authenticate_local_user, principal_for_user
from ..services.rate_limit import enforce_rate_limit


router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


def _admin_credentials_configured() -> bool:
    return bool(settings.AUTH_ADMIN_PASSWORD_HASH or settings.AUTH_ADMIN_PASSWORD)


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(request, "login", payload.username)
    try:
        user = authenticate_local_user(db, payload.username, payload.password)
        if user is None:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )
        principal = principal_for_user(user)
        append_audit_event(
            db,
            event="user.login",
            actor_user_id=user.id,
            resource_type="user",
            resource_id=user.id,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to provision local identity",
        ) from exc

    token = create_access_token(
        data=principal,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "roles": principal["roles"],
            "scopes": principal["scopes"],
        },
    }


@router.get("/me")
async def me(current_user: TokenData = Depends(get_authenticated_user)):
    return {
        "authenticated": True,
        "user": {
            "id": current_user.user_id,
            "username": current_user.username,
            "email": current_user.email,
            "roles": current_user.roles,
            "scopes": current_user.scopes,
        },
    }


@router.get("/config")
async def auth_config():
    # Public bootstrap metadata contains no credential/configuration details.
    return {"mode": "strict", "strict": True, "demo_login": False}
