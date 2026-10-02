"""One SQLAlchemy engine and session factory per application process."""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from .config import settings


def _resolve_database_url(db_url: str) -> str:
    """Resolve the SQLite path used only by isolated tests/lightweight dev."""
    if not db_url.startswith("sqlite"):
        return db_url
    backend_root = Path(__file__).resolve().parents[1]
    if db_url.startswith("sqlite:///./"):
        relative_path = db_url.replace("sqlite:///./", "", 1)
        absolute_path = (backend_root / relative_path).resolve()
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{absolute_path.as_posix()}"
    return db_url


def _engine_options(database_url: str) -> dict:
    backend = make_url(database_url).get_backend_name()
    options: dict = {"pool_pre_ping": True}
    if backend == "sqlite":
        options["connect_args"] = {"check_same_thread": False}
    else:
        options.update(
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_timeout=settings.DB_POOL_TIMEOUT_SECONDS,
            pool_recycle=settings.DB_POOL_RECYCLE_SECONDS,
        )
    return options


resolved_database_url = _resolve_database_url(settings.DATABASE_URL)
engine = create_engine(resolved_database_url, **_engine_options(resolved_database_url))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Provide an isolated transaction-capable Session for one HTTP request."""
    db: Session = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
