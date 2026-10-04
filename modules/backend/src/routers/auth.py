"""Persistent local authentication endpoints."""

from datetime import timedelta
import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..security import TokenData, create_access_token, get_authenticated_user, oauth2_scheme, verify_password
from ..models import FirebaseIdentity, User
from ..services.firebase_identity import verify_firebase_token, resolve_firebase_user
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
    if settings.FIREBASE_AUTH_ENABLED:
        raise HTTPException(409, 'Use Google sign-in to create your account')
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
async def me(current_user: TokenData = Depends(get_authenticated_user), db: Session = Depends(get_db)):
    return {
        "authenticated": True,
        "user": {
            "id": current_user.user_id,
            "username": current_user.username,
            "email": current_user.email,
            "roles": current_user.roles,
            "scopes": current_user.scopes,
            "registration_source": current_user.registration_source,
            "auth_provider": current_user.auth_provider,
            "display_name": current_user.display_name,
            "google_connected": db.query(FirebaseIdentity).filter_by(user_id=current_user.user_id).first() is not None,
        },
    }


@router.get("/config")
async def auth_config():
    # Public bootstrap metadata contains no credential/configuration details.
    return {"mode": "strict", "strict": True, "demo_login": False,
            "firebase_enabled": settings.FIREBASE_AUTH_ENABLED,
            "firebase_project_id": settings.FIREBASE_PROJECT_ID if settings.FIREBASE_AUTH_ENABLED else None,
            "local_signup_enabled": not settings.FIREBASE_AUTH_ENABLED}


def _firebase_response(user: User, display_name: str | None) -> dict:
    principal = principal_for_user(user)
    return {'authenticated': True, 'user': {
        'id': user.id, 'username': user.username, 'email': user.email,
        'roles': principal['roles'], 'scopes': principal['scopes'],
        'registration_source': user.registration_source,
        'auth_provider': 'firebase', 'display_name': display_name, 'google_connected': True,
    }}


@router.post('/firebase')
def firebase_login(request: Request, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    enforce_rate_limit(request, 'firebase-login')
    identity = verify_firebase_token(token)
    enforce_rate_limit(request, 'firebase-account', identity.project_id + ':' + identity.uid)
    user, created = resolve_firebase_user(db, identity)
    append_audit_event(db, event='user.registered' if created else 'user.login',
                       actor_user_id=user.id, resource_type='user', resource_id=user.id)
    db.commit()
    return _firebase_response(user, identity.display_name)


class FirebaseLinkRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id_token: SecretStr = Field(min_length=1, max_length=16384)
    password: SecretStr = Field(min_length=1, max_length=256)


@router.post('/firebase/link')
def link_firebase(payload: FirebaseLinkRequest, request: Request,
                  current: TokenData = Depends(get_authenticated_user), db: Session = Depends(get_db)):
    if current.auth_provider != 'local':
        raise HTTPException(403, 'Sign in with your existing USAGI password to link Google')
    enforce_rate_limit(request, 'firebase-link', str(current.user_id))
    user = db.query(User).filter_by(id=current.user_id).with_for_update().one()
    if not verify_password(payload.password.get_secret_value(), user.hashed_password):
        raise HTTPException(401, 'Unable to link Google; confirm your existing password')
    identity = verify_firebase_token(payload.id_token.get_secret_value())
    if not 0 <= time.time() - identity.auth_time <= 300:
        raise HTTPException(401, 'Authenticate with Google again to link your account')
    binding = db.get(FirebaseIdentity, (identity.project_id, identity.uid))
    existing = db.query(FirebaseIdentity).filter_by(user_id=user.id).first()
    if ((binding is not None and binding.user_id != user.id)
            or (existing is not None and existing != binding)):
        raise HTTPException(409, 'This Google identity or USAGI account is already linked')
    if binding is None:
        try:
            with db.begin_nested():
                db.add(FirebaseIdentity(project_id=identity.project_id, uid=identity.uid, user_id=user.id))
                db.flush()
        except IntegrityError:
            raise HTTPException(409, 'Unable to link Google; account is already linked') from None
        append_audit_event(db, event='user.identity_linked', actor_user_id=user.id,
                           resource_type='user', resource_id=user.id)
    db.commit()
    return _firebase_response(user, identity.display_name)
