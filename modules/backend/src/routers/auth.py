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
from ..services.identity import authenticate_local_user, principal_for_user, register_public_user
from ..services.rate_limit import enforce_rate_limit
from ..utils.http_limits import BodyLimitedRoute


router = APIRouter(prefix="/auth", tags=["auth"], route_class=BodyLimitedRoute)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class SignupRequest(LoginRequest):
    email: str = Field(min_length=3, max_length=255)


@router.post("/signup", response_model=LoginResponse, status_code=201)
async def signup(payload: SignupRequest, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(request, "signup", payload.username)
    try:
        user = register_public_user(db, payload.username, payload.email, payload.password)
        append_audit_event(db, event="user.registered", actor_user_id=user.id,
                           resource_type="user", resource_id=user.id)
        db.commit()
    except (ValueError, IntegrityError):
        db.rollback()
        raise HTTPException(400, "Unable to create account with these details") from None
    principal = principal_for_user(user)
    return {"access_token": create_access_token(principal), "user": {
        "id": user.id, "username": user.username, "email": user.email,
        "roles": principal["roles"], "scopes": principal["scopes"],
        "registration_source": user.registration_source,
    }}


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
            "registration_source": user.registration_source,
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
            "registration_source": current_user.registration_source,
        },
    }


@router.get("/config")
async def auth_config():
    # Public bootstrap metadata contains no credential/configuration details.
    return {"mode": "strict", "strict": True, "demo_login": False}
