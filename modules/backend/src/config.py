from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
import os
from pathlib import Path
from typing import Literal, Optional


class Settings(BaseSettings):
    """Configurações da aplicação."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # Keep accepting older .env keys during migration.
        hide_input_in_errors=True,
    )

    APP_ENV: Literal["dev", "prod", "test"] = Field(
        default="dev",
        description="Application environment (dev, prod, test)",
    )
    
    # API Keys
    HF_TOKEN: Optional[str] = Field(default=None, description="Hugging Face API Token")
    AAI_API_KEY: Optional[str] = Field(default=None, description="AssemblyAI API Key")
    GEMINI_API_KEY: Optional[str] = Field(default=None, description="Google Gemini API Key")
    HF_TOKEN_CONFIGURED: bool = Field(default=False)
    AAI_API_KEY_CONFIGURED: bool = Field(default=False)
    GEMINI_API_KEY_CONFIGURED: bool = Field(default=False)
    GEMINI_MODEL: str = Field(default="gemini-2.5-flash", min_length=1, max_length=100)
    INTELLIGENCE_MAX_INPUT_CHARACTERS: int = Field(default=200000, ge=1000, le=2000000)
    
    # Database
    DATABASE_URL: str = Field(
        description="SQLAlchemy URL; PostgreSQL+psycopg is the official runtime"
    )
    DB_POOL_SIZE: int = Field(default=5, description="Persistent connections per process")
    DB_MAX_OVERFLOW: int = Field(default=5, description="Temporary overflow connections")
    DB_POOL_TIMEOUT_SECONDS: int = Field(default=30, description="Pool checkout timeout")
    DB_POOL_RECYCLE_SECONDS: int = Field(default=1800, description="Connection recycle age")
    
    # Redis & Job Queue
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL for job queue"
    )
    
    # API Configuration
    API_HOST: str = Field(default="0.0.0.0", description="API Host")
    API_PORT: int = Field(default=2020, description="API Port")
    DEBUG: bool = Field(default=False, description="Debug mode")
    
    # Security
    SECRET_KEY: Optional[str] = Field(
        default=None,
        description="Secret key for JWT (required in production)",
    )
    ALGORITHM: str = Field(default="HS256", description="JWT Algorithm")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=30,
        description="Access token expiration time"
    )
    LOGIN_RATE_LIMIT_PER_IP: int = Field(default=30)
    LOGIN_RATE_LIMIT_PER_ACCOUNT: int = Field(default=10)
    UPLOAD_RATE_LIMIT_PER_IP: int = Field(default=300)
    JOB_RATE_LIMIT_PER_USER: int = Field(default=30)
    SIGNUP_RATE_LIMIT_PER_IP: int = Field(default=5, ge=1)
    PUBLIC_MAX_UPLOAD_MB: int = Field(default=100, ge=1, le=100)
    PUBLIC_MAX_AUDIO_SECONDS: int = Field(default=600, ge=1, le=600)
    PUBLIC_JOB_TIMEOUT_SECONDS: int = Field(default=300, ge=60, le=1800)
    PUBLIC_JOB_RATE_LIMIT_PER_IP: int = Field(default=3, ge=1)
    PUBLIC_JOB_RATE_LIMIT_GLOBAL: int = Field(default=10, ge=1)
    GUEST_SESSION_RATE_LIMIT_PER_IP: int = Field(default=5, ge=1)
    GUEST_RETENTION_HOURS: int = Field(default=24, ge=1, le=168)
    GUEST_JOBS_PER_SESSION: int = Field(default=1, ge=1, le=10)
    JWT_ISSUER: str = Field(default="usagi-api", description="Expected JWT issuer")
    JWT_AUDIENCE: str = Field(default="usagi-web", description="Expected JWT audience")

    CORS_ALLOWED_ORIGINS: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173",
        description="Comma-separated browser origins allowed to call the API",
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(
        default=False,
        description="Whether CORS may include browser credentials",
    )
    
    # File Upload
    MAX_UPLOAD_SIZE_MB: int = Field(
        default=5120,
        description="Maximum upload size in MB"
    )
    ALLOWED_EXTENSIONS: str = Field(
        default="mp3,wav,mp4,mpeg,m4a,flac,ogg,opus",
        description="Allowed file extensions"
    )
    
    # Processing
    DEFAULT_TRANSCRIPTION_MODEL: str = Field(
        default="whisper",
        description="Default transcription model (whisper or assemblyai)"
    )
    TRANSCRIPTION_JOB_TIMEOUT_SECONDS: int = Field(
        default=3600,
        ge=60,
        description="RQ timeout for long-running transcription jobs and recovery",
    )
    MIN_SEGMENT_DURATION: float = Field(
        default=0.0,
        description=(
            "Optional minimum Pyannote turn duration; zero preserves short speech"
        )
    )
    AUDIO_UPLOAD_DIRECTORY: str = Field(
        default="database/uploads",
        description="Worker-shared directory for original uploads",
    )
    AUDIO_ORPHAN_RETENTION_HOURS: int = Field(
        default=24,
        description="Minimum age before unreferenced uploads may be reconciled",
    )
    TRANSCRIPTION_RETENTION_DAYS: int = Field(
        default=0,
        description="Result retention; zero means no automatic expiry",
    )
    AUDIT_RETENTION_DAYS: int = Field(
        default=0,
        description="Audit retention; zero means no automatic expiry",
    )
    SILENCE_THRESHOLD: float = Field(
        default=-100.0,
        description=(
            "Optional RMS dBFS post-filter; -100 disables redundant filtering"
        )
    )
    MEETING_MINUTES_TIMEOUT_SECONDS: int = Field(
        default=600,
        description="Maximum wait for the compatibility meeting-minutes endpoint",
    )
    
    # GPU/Device Configuration
    FORCE_CPU: bool = Field(
        default=False,
        description="Force CPU usage even if GPU is available"
    )
    GPU_MEMORY_FRACTION: float = Field(
        default=0.8,
        description="Fraction of GPU memory to use (0.1-1.0)"
    )
    WHISPER_MODEL: str = Field(
        default="large-v3",
        description="Faster-Whisper model size or converted model path",
    )
    WHISPER_DEVICE: Literal["auto", "cpu", "cuda"] = Field(
        default="auto",
        description="CTranslate2 execution device",
    )
    WHISPER_COMPUTE_TYPE: str = Field(
        default="auto",
        description="CTranslate2 compute type; auto selects float16 CUDA or int8 CPU",
    )
    WHISPER_LANGUAGE: Literal["pt", "en", "auto"] = Field(
        default="pt",
        description="Transcription language; auto enables detection",
    )
    WHISPER_BEAM_SIZE: int = Field(
        default=1,
        description="Beam size used by both benchmarkable Whisper engines",
    )
    WHISPER_MAX_DECODE_CHUNK_SECONDS: float = Field(
        default=300.0,
        description="Maximum PCM window held in memory during Faster-Whisper inference",
    )
    WHISPER_CPU_THREADS: int = Field(
        default=0,
        description="CTranslate2 CPU threads; zero uses its default",
    )

    # Authentication. Rollout flags remain readable for old deployments, but
    # private routes no longer use them to permit anonymous access.
    AUTH_MODE: Literal["permissive", "strict"] = Field(
        default="strict",
        description="Authentication rollout mode",
    )
    AUTH_PROTECT_API_KEYS: bool = Field(
        default=True,
        description="Protect /api-keys endpoints",
    )
    AUTH_PROTECT_PROCESSING: bool = Field(
        default=True,
        description="Protect job creation and meeting-minutes endpoints",
    )
    AUTH_PROTECT_READS: bool = Field(
        default=True,
        description="Protect read endpoints (/transcriptions, /stats)",
    )
    AUTH_ADMIN_USERNAME: str = Field(
        default="admin",
        description="Bootstrap admin username",
    )
    AUTH_ADMIN_EMAIL: str = Field(
        default="admin@local.invalid",
        description="Email stored for the bootstrap administrator",
    )
    AUTH_ADMIN_PASSWORD: Optional[str] = Field(
        default=None,
        description="Bootstrap admin password (dev only)",
    )
    AUTH_ADMIN_PASSWORD_HASH: Optional[str] = Field(
        default=None,
        description="Bootstrap admin password hash (recommended)",
    )
    AUTH_ALLOW_DEMO_LOGIN: bool = Field(
        default=False,
        description="Allow first-login local users in dev only",
    )
    
    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "prod"

    @property
    def allowed_extensions_list(self) -> list[str]:
        """Retorna lista de extensões permitidas."""
        return [ext.strip() for ext in self.ALLOWED_EXTENSIONS.split(",")]

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ALLOWED_ORIGINS.split(",") if origin.strip()]
    
    @property
    def max_upload_size_bytes(self) -> int:
        """Retorna tamanho máximo de upload em bytes."""
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    def validate_startup(self, *, require_api_security: bool = True) -> list[str]:
        """Valida configurações obrigatórias para startup seguro."""
        errors: list[str] = []

        if not self.DATABASE_URL or not self.DATABASE_URL.strip():
            errors.append("DATABASE_URL is required")
        if min(
            self.LOGIN_RATE_LIMIT_PER_IP,
            self.LOGIN_RATE_LIMIT_PER_ACCOUNT,
            self.UPLOAD_RATE_LIMIT_PER_IP,
            self.JOB_RATE_LIMIT_PER_USER,
        ) <= 0:
            errors.append("Rate limits must be greater than zero")

        if self.is_production and not self.DATABASE_URL.startswith(
            "postgresql+psycopg://"
        ):
            errors.append(
                "DATABASE_URL must use PostgreSQL with the psycopg driver "
                "when APP_ENV=prod"
            )

        if self.DB_POOL_SIZE <= 0:
            errors.append("DB_POOL_SIZE must be greater than zero")
        if self.DB_MAX_OVERFLOW < 0:
            errors.append("DB_MAX_OVERFLOW cannot be negative")
        if self.DB_POOL_TIMEOUT_SECONDS <= 0:
            errors.append("DB_POOL_TIMEOUT_SECONDS must be greater than zero")
        if self.DB_POOL_RECYCLE_SECONDS <= 0:
            errors.append("DB_POOL_RECYCLE_SECONDS must be greater than zero")

        if self.DEFAULT_TRANSCRIPTION_MODEL not in {"whisper", "assemblyai"}:
            errors.append("DEFAULT_TRANSCRIPTION_MODEL must be 'whisper' or 'assemblyai'")

        if not (0.1 <= self.GPU_MEMORY_FRACTION <= 1.0):
            errors.append("GPU_MEMORY_FRACTION must be between 0.1 and 1.0")

        if not self.WHISPER_MODEL.strip():
            errors.append("WHISPER_MODEL is required")

        if self.WHISPER_COMPUTE_TYPE not in {
            "auto",
            "default",
            "float32",
            "float16",
            "bfloat16",
            "int16",
            "int8",
            "int8_float32",
            "int8_float16",
            "int8_bfloat16",
        }:
            errors.append("WHISPER_COMPUTE_TYPE is not supported")

        if self.WHISPER_BEAM_SIZE <= 0:
            errors.append("WHISPER_BEAM_SIZE must be greater than zero")

        if self.WHISPER_MAX_DECODE_CHUNK_SECONDS <= 0:
            errors.append("WHISPER_MAX_DECODE_CHUNK_SECONDS must be greater than zero")

        if self.MIN_SEGMENT_DURATION < 0:
            errors.append("MIN_SEGMENT_DURATION cannot be negative")

        if not (-100.0 <= self.SILENCE_THRESHOLD <= 0.0):
            errors.append("SILENCE_THRESHOLD must be between -100 and 0 dBFS")

        if self.WHISPER_CPU_THREADS < 0:
            errors.append("WHISPER_CPU_THREADS cannot be negative")

        if self.ACCESS_TOKEN_EXPIRE_MINUTES <= 0:
            errors.append("ACCESS_TOKEN_EXPIRE_MINUTES must be greater than 0")

        if self.ALGORITHM not in {"HS256", "HS384", "HS512"}:
            errors.append("ALGORITHM must be an HMAC SHA-2 JWT algorithm")

        if not self.JWT_ISSUER.strip() or not self.JWT_AUDIENCE.strip():
            errors.append("JWT_ISSUER and JWT_AUDIENCE are required")

        if not self.cors_allowed_origins_list:
            errors.append("CORS_ALLOWED_ORIGINS must contain at least one origin")

        if self.AUDIO_ORPHAN_RETENTION_HOURS <= 0:
            errors.append("AUDIO_ORPHAN_RETENTION_HOURS must be greater than zero")
        if self.TRANSCRIPTION_RETENTION_DAYS < 0:
            errors.append("TRANSCRIPTION_RETENTION_DAYS cannot be negative")
        if self.AUDIT_RETENTION_DAYS < 0:
            errors.append("AUDIT_RETENTION_DAYS cannot be negative")

        if self.AUTH_MODE not in {"permissive", "strict"}:
            errors.append("AUTH_MODE must be 'permissive' or 'strict'")

        # Security checks are strict in production only (low-risk migration).
        if self.is_production and require_api_security:
            secret = (self.SECRET_KEY or "").strip()
            if not secret:
                errors.append("SECRET_KEY is required when APP_ENV=prod")
            else:
                insecure_markers = {
                    "your-secret-key-change-this-in-production",
                    "your-secret-key-here-change-in-production",
                    "changeme",
                    "change-me",
                    "default",
                }
                if secret.lower() in insecure_markers:
                    errors.append("SECRET_KEY uses an insecure placeholder value in production")
                if len(secret) < 32:
                    errors.append("SECRET_KEY must have at least 32 characters in production")

            if not self.AUTH_ADMIN_PASSWORD_HASH and not self.AUTH_ADMIN_PASSWORD:
                errors.append(
                    "AUTH_ADMIN_PASSWORD_HASH or AUTH_ADMIN_PASSWORD is required when APP_ENV=prod"
                )

            if self.AUTH_MODE != "strict":
                errors.append("AUTH_MODE must be 'strict' when APP_ENV=prod")
            if self.AUTH_ALLOW_DEMO_LOGIN:
                errors.append("AUTH_ALLOW_DEMO_LOGIN must be false when APP_ENV=prod")
            if not all(
                (
                    self.AUTH_PROTECT_API_KEYS,
                    self.AUTH_PROTECT_PROCESSING,
                    self.AUTH_PROTECT_READS,
                )
            ):
                errors.append("All AUTH_PROTECT_* flags must be true in production")
            if "*" in self.cors_allowed_origins_list:
                errors.append("CORS_ALLOWED_ORIGINS cannot contain '*' in production")
            if not self.AUTH_ADMIN_EMAIL.strip():
                errors.append("AUTH_ADMIN_EMAIL is required when APP_ENV=prod")

        return errors


def resolve_env_file() -> str:
    """
    Resolve qual arquivo de ambiente usar.

    Prioridade:
    1) SETTINGS_ENV_FILE (override explícito)
    2) .env.<APP_ENV> se existir (ex.: .env.dev, .env.prod)
    3) .env (fallback)
    """
    explicit_file = os.getenv("SETTINGS_ENV_FILE")
    if explicit_file:
        return explicit_file

    app_env = (os.getenv("APP_ENV", "dev") or "dev").strip().lower()
    env_candidate = f".env.{app_env}"
    if Path(env_candidate).exists():
        return env_candidate

    return ".env"


def sanitize_settings_snapshot() -> dict:
    """Retorna snapshot seguro para logs de startup (sem expor segredos)."""
    return {
        "app_env": settings.APP_ENV,
        "api_host": settings.API_HOST,
        "api_port": settings.API_PORT,
        "debug": settings.DEBUG,
        "database_url_set": bool(settings.DATABASE_URL),
        "hf_token_configured": settings.HF_TOKEN_CONFIGURED or bool(settings.HF_TOKEN),
        "aai_api_key_configured": settings.AAI_API_KEY_CONFIGURED or bool(settings.AAI_API_KEY),
        "gemini_api_key_configured": settings.GEMINI_API_KEY_CONFIGURED or bool(settings.GEMINI_API_KEY),
        "transcription_engine": "faster-whisper",
        "whisper_model": settings.WHISPER_MODEL,
        "whisper_device": settings.WHISPER_DEVICE,
        "whisper_compute_type": settings.WHISPER_COMPUTE_TYPE,
        "whisper_language": settings.WHISPER_LANGUAGE,
        "secret_key_configured": bool(settings.SECRET_KEY),
        "auth_mode": settings.AUTH_MODE,
        "auth_protect_api_keys": settings.AUTH_PROTECT_API_KEYS,
        "auth_protect_processing": settings.AUTH_PROTECT_PROCESSING,
        "auth_protect_reads": settings.AUTH_PROTECT_READS,
        "cors_origins": settings.cors_allowed_origins_list,
        "audio_orphan_retention_hours": settings.AUDIO_ORPHAN_RETENTION_HOURS,
        "transcription_retention_days": settings.TRANSCRIPTION_RETENTION_DAYS,
        "audit_retention_days": settings.AUDIT_RETENTION_DAYS,
    }


# Instância global de configurações
settings = Settings(_env_file=resolve_env_file(), _env_file_encoding="utf-8")
