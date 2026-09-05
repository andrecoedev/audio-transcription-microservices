import os
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# As flags precisam existir antes da importação dos routers, pois as dependências
# condicionais de autenticação são construídas no registro das rotas.
os.environ.update(
    {
        "APP_ENV": "test",
        "AUTH_MODE": "strict",
        "AUTH_PROTECT_PROCESSING": "true",
        "AUTH_PROTECT_READS": "true",
        "SECRET_KEY": "test-secret-key-with-at-least-32-characters",
        "DATABASE_URL": "sqlite:///:memory:",
        "DEBUG": "false",
    }
)

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import get_db
from src.models import Base
from src.routers import transcribe, transcriptions
from src.security import create_access_token


class FakeRedisConnection:
    def ping(self):
        return True


class FakeStartedJobRegistry:
    def cleanup(self):
        return None


class FakeQueue:
    def __init__(self):
        self.connection = FakeRedisConnection()
        self.started_job_registry = FakeStartedJobRegistry()
        self.enqueued = []

    def enqueue(self, function, transcription_id, **kwargs):
        self.enqueued.append((function, transcription_id, kwargs))
        return object()

    def __len__(self):
        return len(self.enqueued)


@pytest.fixture
def db_context(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    app = FastAPI()
    app.include_router(transcribe.router)
    app.include_router(transcriptions.router)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    queue = FakeQueue()
    monkeypatch.setattr(transcriptions, "get_transcription_queue", lambda: queue)
    monkeypatch.setattr(transcriptions, "_UPLOAD_DIRECTORY", tmp_path / "uploads")

    with TestClient(app) as client:
        yield {
            "client": client,
            "session_factory": testing_session,
            "queue": queue,
            "tmp_path": tmp_path,
        }

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def auth_headers():
    def make(username="alice", scopes=None, roles=None):
        token = create_access_token(
            {
                "sub": username,
                "scopes": scopes
                or ["transcribe", "read_transcriptions", "delete_transcriptions"],
                "roles": roles or [],
            }
        )
        return {"Authorization": f"Bearer {token}"}

    return make


@pytest.fixture
def wav_bytes():
    # Cabeçalho WAV suficiente para a validação de assinatura dos testes de API.
    return b"RIFF" + (36).to_bytes(4, "little") + b"WAVEfmt " + (b"\x00" * 32)
