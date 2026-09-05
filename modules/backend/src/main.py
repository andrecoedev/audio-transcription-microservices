import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import apply_persisted_secrets, sanitize_settings_snapshot, settings
from . import engine_registry  # noqa: F401
from .api_keys_manager import api_keys_manager
from .services.diarization_engine import DiarizationEngine
from .services.transcription_engine import WhisperEngine, AssemblyAIEngine
from .services.meeting_minutes import MeetingMinutesGenerator
from .utils.gpu_utils import log_device_info, optimize_gpu_settings
from .database import engine as db_engine  # noqa: F401 – aciona create_all na importação
from .routers import api_keys, auth, compat, health, meeting_minutes, transcribe, transcriptions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Aplicação
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Transcription API - All Services Integrated",
    description=(
        "API de transcrição de áudio com diarização de falantes "
        "(Whisper, AssemblyAI, Pyannote) - Tudo em um processo no port 2020"
    ),
    version="2.0.0",
    debug=settings.DEBUG,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restringir origens em produção
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(transcribe.router)
app.include_router(transcriptions.router)
app.include_router(api_keys.router)
app.include_router(meeting_minutes.router)
app.include_router(compat.router)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def load_models():
    """Carrega todos os engines de ML no startup, protegido pelo mutation_lock."""
    async with engine_registry.mutation_lock:
        logger.info("=" * 60)
        logger.info("INICIANDO CARREGAMENTO DOS MODELOS")
        logger.info("=" * 60)

        # Sobrescrever settings com chaves persistidas (têm prioridade sobre .env)
        saved_keys = api_keys_manager.get_all()
        applied_keys = apply_persisted_secrets(saved_keys)
        if applied_keys:
            logger.info(f"Secrets carregados do armazenamento persistente: {applied_keys}")
        logger.info(f"Config snapshot: {sanitize_settings_snapshot()}")

        validation_errors = settings.validate_startup()
        if validation_errors:
            for err in validation_errors:
                logger.error(f"Startup config error: {err}")
            raise RuntimeError(
                "Invalid configuration. Fix startup settings before running the API."
            )

        log_device_info()
        optimize_gpu_settings()

        if settings.HF_TOKEN:
            try:
                logger.info("Carregando Pyannote para diarizacao...")
                engine_registry.diarization_engine = DiarizationEngine(settings.HF_TOKEN)
                logger.info(f"Pyannote carregado! Device: {engine_registry.diarization_engine.get_device()}")
            except Exception as e:
                logger.error(f"Erro ao carregar Pyannote: {e}")
                logger.warning("Diarizacao nao estara disponivel")

            try:
                logger.info("Carregando Whisper para transcricao local...")
                engine_registry.whisper_engine = WhisperEngine(settings.HF_TOKEN)
                logger.info(f"Whisper carregado! Device: {engine_registry.whisper_engine.get_device()}")
            except Exception as e:
                logger.error(f"Erro ao carregar Whisper: {e}")
                logger.warning("Transcricao Whisper nao estara disponivel")
        else:
            logger.warning("HF_TOKEN nao configurado - Pyannote e Whisper nao serao carregados")

        if settings.AAI_API_KEY:
            try:
                logger.info("Configurando AssemblyAI para transcricao cloud...")
                engine_registry.assemblyai_engine = AssemblyAIEngine(settings.AAI_API_KEY)
                logger.info("AssemblyAI configurado!")
            except Exception as e:
                logger.error(f"Erro ao configurar AssemblyAI: {e}")
                logger.warning("Transcricao AssemblyAI nao estara disponivel")
        else:
            logger.warning("AAI_API_KEY nao configurado - AssemblyAI nao sera carregado")

        if settings.GEMINI_API_KEY:
            try:
                logger.info("Configurando Gemini para geracao de atas...")
                engine_registry.meeting_minutes_generator = MeetingMinutesGenerator(settings.GEMINI_API_KEY)
                logger.info("Gemini configurado!")
            except Exception as e:
                logger.error(f"Erro ao configurar Gemini: {e}")
                logger.warning("Geracao de atas nao estara disponivel")
        else:
            logger.warning("GEMINI_API_KEY nao configurado - Geracao de atas nao sera carregada")

        logger.info("=" * 60)
        logger.info("MODELOS CARREGADOS - API PRONTA!")
        logger.info("=" * 60)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
    )
