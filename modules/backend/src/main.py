"""FastAPI leve: HTTP, autenticação, banco, uploads e filas."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api_keys_manager import api_keys_manager
from .config import apply_persisted_secrets, sanitize_settings_snapshot, settings
from .database import engine as db_engine  # noqa: F401 - garante o schema atual
from .routers import api_keys, auth, health, meeting_minutes, transcriptions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Transcription API",
    description="API HTTP e fila RQ para processamento de transcrições",
    version="2.1.0",
    debug=settings.DEBUG,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restringir origens em produção
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(transcriptions.router)
app.include_router(api_keys.router)
app.include_router(meeting_minutes.router)


@app.on_event("startup")
async def validate_api_startup() -> None:
    """Carrega configuração leve; engines pertencem exclusivamente ao worker."""
    applied_keys = apply_persisted_secrets(api_keys_manager.get_all())
    if applied_keys:
        logger.info("Persisted API key configuration loaded: %s", applied_keys)

    validation_errors = settings.validate_startup()
    if validation_errors:
        for error in validation_errors:
            logger.error("Startup config error: %s", error)
        raise RuntimeError("Invalid API configuration")

    logger.info("API ready without loading processing engines: %s", sanitize_settings_snapshot())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
    )
