"""Bound actual HTTP bytes before parsing sensitive public request bodies."""

import logging

from fastapi import HTTPException
from fastapi.routing import APIRoute
from starlette.concurrency import run_in_threadpool

from ..config import settings
from ..database import SessionLocal
from ..models import User
from ..security import decode_access_token
from ..services.transcription_entitlements import has_development_local_access
from ..services.upload_policy import upload_limit_mb

logger = logging.getLogger(__name__)


class BodyLimitedRoute(APIRoute):
    async def handle(self, scope, receive, send):
        limit = None
        path = scope.get("path")
        if scope.get("method") == "DELETE" and path == "/account":
            limit = 16 * 1024
        if scope.get("method") in {"POST", "PATCH"} and path.startswith("/settings/providers"):
            limit = 16 * 1024
        if scope.get("method") == "PATCH" and path.startswith("/admin/accounts/"):
            limit = 16 * 1024
        if scope.get("method") == "POST":
            if path in {"/auth/signup", "/auth/login", "/guest/claim"}:
                limit = 16 * 1024
            public_upload = path == "/guest/transcriptions/jobs"
            upload_mb = settings.PUBLIC_MAX_UPLOAD_MB
            if path == "/transcriptions/jobs":
                authorization = dict(scope.get("headers", [])).get(b"authorization", b"").decode("latin-1")
                scheme, _, token = authorization.partition(" ")
                principal = decode_access_token(token) if scheme.lower() == "bearer" else None
                upload_mb = settings.PUBLIC_MAX_UPLOAD_MB
                development_access = False
                if principal and principal.user_id is not None:
                    def current_development_access():
                        db = SessionLocal()
                        try:
                            user = db.get(User, principal.user_id)
                            return (has_development_local_access(user),
                                    user.registration_source if user else None)
                        finally:
                            db.close()
                    try:
                        development_access, registration_source = await run_in_threadpool(current_development_access)
                        if registration_source is not None:
                            upload_mb = upload_limit_mb(principal.user_id, registration_source,
                                                         development_access)
                    except Exception:
                        logger.warning("Upload policy lookup unavailable; applying public body limit")
                        development_access = False
                if development_access:
                    upload_mb = settings.MAX_UPLOAD_SIZE_MB
            if path in {"/guest/transcriptions/jobs", "/transcriptions/jobs"}:
                limit = upload_mb * 1024 * 1024 + 64 * 1024
        if limit is not None:
            received = 0
            original_receive = receive

            async def bounded_receive():
                nonlocal received
                message = await original_receive()
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(413, "Request exceeds size limit")
                return message

            receive = bounded_receive
        await super().handle(scope, receive, send)
