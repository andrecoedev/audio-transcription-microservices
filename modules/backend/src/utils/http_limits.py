"""Bound actual HTTP bytes before parsing sensitive public request bodies."""

from fastapi import HTTPException
from fastapi.routing import APIRoute

from ..config import settings
from ..security import decode_verified_claims


class BodyLimitedRoute(APIRoute):
    async def handle(self, scope, receive, send):
        limit = None
        path = scope.get("path")
        if scope.get("method") in {"POST", "PATCH"} and path.startswith("/settings/providers"):
            limit = 16 * 1024
        if scope.get("method") == "POST":
            if path in {"/auth/signup", "/auth/login", "/guest/claim"}:
                limit = 16 * 1024
            public_upload = path == "/guest/transcriptions/jobs"
            if path == "/transcriptions/jobs":
                authorization = dict(scope.get("headers", [])).get(b"authorization", b"").decode("latin-1")
                scheme, _, token = authorization.partition(" ")
                claims = decode_verified_claims(token) if scheme.lower() == "bearer" else None
                public_upload = bool(claims and claims.get("registration_source") == "public")
            if public_upload:
                limit = settings.PUBLIC_MAX_UPLOAD_MB * 1024 * 1024 + 64 * 1024
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
