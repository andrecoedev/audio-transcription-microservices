"""Light FastAPI process: HTTP, auth, database, uploads and queueing only."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .config import sanitize_settings_snapshot, settings
from .logging_config import configure_logging
from .routers import api_keys, auth, guests, health, meeting_actions, meeting_intelligence, meeting_minutes, meetings, provider_preferences, reviewed_meeting_minutes, transcriptions
from .routers import usage, account_plans


configure_logging()
logger = logging.getLogger(__name__)


async def validate_api_startup() -> None:
    validation_errors = settings.validate_startup()
    if validation_errors:
        for error in validation_errors:
            logger.error("Startup config error: %s", error)
        raise RuntimeError("Invalid API configuration")
    logger.info("API ready without loading processing engines: %s", sanitize_settings_snapshot())


@asynccontextmanager
async def lifespan(_: FastAPI):
    await validate_api_startup()
    yield


app = FastAPI(
    title="Transcription API",
    description="HTTP API and RQ queue for transcription processing",
    version="2.2.0",
    debug=settings.DEBUG,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins_list,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(provider_preferences.router)
app.include_router(usage.router)
app.include_router(account_plans.router)
app.include_router(guests.router)
app.include_router(transcriptions.router)
app.include_router(meetings.router)
app.include_router(meeting_actions.router)
app.include_router(meeting_intelligence.router)
app.include_router(api_keys.router)
app.include_router(meeting_minutes.router)
app.include_router(reviewed_meeting_minutes.router)


@app.exception_handler(RequestValidationError)
async def safe_validation_error(_request, exc):
    # FastAPI's default includes rejected input, potentially a password/token.
    return JSONResponse(status_code=422, content={"detail": [
        {"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]})


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path.startswith(("/usage", "/auth", "/guest", "/settings", "/transcriptions", "/meetings", "/meeting-minutes")):
        response.headers["Cache-Control"] = "no-store"
    return response

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
    )
