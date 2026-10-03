"""Verified Firebase identity -> internal user. No email-based account linking."""
from dataclasses import dataclass
import os
import re
from threading import Lock
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..models import FirebaseIdentity, User

_app_lock = Lock()


@dataclass(frozen=True)
class VerifiedFirebaseIdentity:
    project_id: str
    uid: str
    email: str
    auth_time: int
    display_name: str | None = None


def _verify_with_sdk(token: str) -> dict:
    # Lazy, API-only: no credentials/models/network at web import/startup.
    import firebase_admin
    from firebase_admin import auth, exceptions
    from google.auth.exceptions import DefaultCredentialsError

    try:
        with _app_lock:
            name = 'usagi-auth-' + settings.FIREBASE_PROJECT_ID
            try:
                app = firebase_admin.get_app(name)
            except ValueError:
                app = firebase_admin.initialize_app(options={
                    'projectId': settings.FIREBASE_PROJECT_ID,
                    'httpTimeout': settings.FIREBASE_HTTP_TIMEOUT_SECONDS,
                }, name=name)
    except (DefaultCredentialsError, ValueError, OSError):
        raise HTTPException(503, 'Authentication service temporarily unavailable') from None
    try:
        return auth.verify_id_token(token, app=app, check_revoked=True, clock_skew_seconds=0)
    except auth.CertificateFetchError:
        raise HTTPException(503, 'Authentication service temporarily unavailable') from None
    except (auth.InvalidIdTokenError, auth.RevokedIdTokenError, auth.UserDisabledError,
            auth.UserNotFoundError, ValueError):
        raise HTTPException(401, 'Could not validate credentials', headers={'WWW-Authenticate': 'Bearer'}) from None
    except exceptions.FirebaseError:
        raise HTTPException(503, 'Authentication service temporarily unavailable') from None


def verify_firebase_token(token: str) -> VerifiedFirebaseIdentity:
    project = settings.FIREBASE_PROJECT_ID
    # Never let an accidentally inherited emulator env accept unsigned tokens.
    if (not settings.FIREBASE_AUTH_ENABLED or not project
            or not re.fullmatch(r'[a-z0-9][a-z0-9-]{4,127}', project)
            or os.getenv('FIREBASE_AUTH_EMULATOR_HOST')):
        raise HTTPException(503, 'Authentication service unavailable')
    if not isinstance(token, str) or not 1 <= len(token) <= 16384:
        raise HTTPException(401, 'Could not validate credentials')
    claims = _verify_with_sdk(token)
    uid, email = claims.get('uid'), claims.get('email')
    firebase = claims.get('firebase', {})
    if (claims.get('aud') != project or claims.get('iss') != f'https://securetoken.google.com/{project}'
            or not isinstance(uid, str) or not 1 <= len(uid) <= 128 or claims.get('sub') != uid
            or not isinstance(email, str) or not 3 <= len(email) <= 255
            or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email)
            or claims.get('email_verified') is not True
            or not isinstance(firebase, dict) or firebase.get('sign_in_provider') != 'google.com'
            or firebase.get('tenant') is not None or type(claims.get('auth_time')) is not int):
        raise HTTPException(401, 'Could not validate credentials')
    name = claims.get('name')
    return VerifiedFirebaseIdentity(project, uid, email.strip().lower(), claims['auth_time'],
        name[:100] if isinstance(name, str) else None)


def find_firebase_user(db: Session, identity: VerifiedFirebaseIdentity) -> User | None:
    binding = db.get(FirebaseIdentity, (identity.project_id, identity.uid))
    if binding is None:
        return None
    user = db.get(User, binding.user_id)
    if user is None or not user.is_active:
        raise HTTPException(401, 'Could not validate credentials')
    return user


def resolve_firebase_user(db: Session, identity: VerifiedFirebaseIdentity) -> tuple[User, bool]:
    user = find_firebase_user(db, identity)
    if user:
        return user, False
    if (db.query(User.id).filter(User.email == identity.email).first()
            or identity.email == settings.AUTH_ADMIN_EMAIL.strip().lower()):
        raise HTTPException(409, 'Sign in to your existing USAGI account to link Google')
    try:
        with db.begin_nested():
            user = User(username='firebase-' + uuid4().hex, email=identity.email,
                hashed_password=None, registration_source='public', is_active=True, is_superuser=False)
            db.add(user)
            db.flush()
            db.add(FirebaseIdentity(project_id=identity.project_id, uid=identity.uid, user_id=user.id))
            db.flush()
        return user, True
    except IntegrityError:
        # First-login race: only the same verified project+UID may reuse a user.
        user = find_firebase_user(db, identity)
        if user:
            return user, False
        raise HTTPException(409, 'Unable to complete sign-in; use your existing USAGI account') from None
