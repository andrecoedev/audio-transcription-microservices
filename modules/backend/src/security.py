"""JWT, password hashing and FastAPI authentication dependencies."""

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    """Validated identity extracted from a signed access token."""

    user_id: Optional[int] = None
    username: Optional[str] = None
    email: Optional[str] = None
    roles: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)
    legacy_subject: bool = False


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except (TypeError, ValueError):
        return False


def get_password_hash(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > 72:
        raise ValueError("Password exceeds bcrypt's 72-byte limit")
    return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=12)).decode("ascii")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    claims = data.copy()
    claims.update(
        {
            "exp": expire,
            "iat": now,
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
            "jti": uuid4().hex,
        }
    )
    return jwt.encode(claims, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> Optional[TokenData]:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
            options={"require": ["exp", "iat", "sub"]},
        )
        subject = payload.get("sub")
        if not isinstance(subject, str) or not subject:
            return None
        try:
            user_id = int(subject)
            legacy_subject = False
        except ValueError:
            user_id = None
            legacy_subject = True
        return TokenData(
            user_id=user_id,
            username=payload.get("username") or (subject if legacy_subject else None),
            email=payload.get("email"),
            roles=payload.get("roles", []),
            scopes=payload.get("scopes", []),
            legacy_subject=legacy_subject,
        )
    except (jwt.PyJWTError, TypeError, ValueError):
        return None


def _invalid_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_optional_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Optional[TokenData]:
    if token is None:
        return None
    token_data = decode_access_token(token)
    if token_data is None:
        raise _invalid_credentials()

    if token_data.user_id is not None:
        user = db.get(User, token_data.user_id)
    else:
        # Compatibility for short-lived pre-P2-B tokens: only an exact stored
        # username is accepted, never a guessed/fallback identity.
        user = db.query(User).filter(User.username == token_data.username).one_or_none()
    if user is None or not user.is_active:
        raise _invalid_credentials()

    token_data.user_id = user.id
    token_data.username = user.username
    token_data.email = user.email
    token_data.roles = ["admin"] if user.is_superuser else ["user"]
    return token_data


async def get_authenticated_user(
    current_user: Optional[TokenData] = Depends(get_optional_user),
) -> TokenData:
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user


require_authentication = get_authenticated_user
get_current_user = get_authenticated_user


def require_scope(scope: str):
    def _require_scope(
        current_user: TokenData = Depends(get_authenticated_user),
    ) -> TokenData:
        if "admin" not in current_user.roles and scope not in current_user.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scope: {scope}",
            )
        return current_user

    return _require_scope


def require_scope_when(scope: str, _enabled: bool):
    """Compatibility alias: private endpoints are always protected in P2-B."""
    return require_scope(scope)


def require_admin(
    current_user: TokenData = Depends(get_authenticated_user),
) -> TokenData:
    if "admin" not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin role required")
    return current_user


def require_admin_when(_enabled: bool):
    return require_admin
