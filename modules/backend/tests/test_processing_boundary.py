import os
import secrets
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src import engine_registry
from src.main import app
from src.routers import health
from src.services import processing_engines
from src.workers import transcription_worker


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _reset_engines() -> None:
    engine_registry.diarization_engine = None
    engine_registry.whisper_engine = None
    engine_registry.assemblyai_engine = None
    engine_registry.meeting_minutes_generator = None
    transcription_worker._processing_service = None


def test_web_application_import_and_startup_do_not_import_ml_stack():
    script = r'''
import importlib.abc
import sys

blocked = {
    "assemblyai", "ctranslate2", "faster_whisper", "firebase_admin", "librosa",
    "pydub", "pyannote", "torch", "transformers"
}
baseline_modules = set(sys.modules)

class BlockHeavyImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".", 1)[0] in blocked or fullname.startswith("google.generativeai"):
            raise RuntimeError(f"heavy import attempted: {fullname}")
        return None

sys.meta_path.insert(0, BlockHeavyImports())
from fastapi.testclient import TestClient
from src.main import app

with TestClient(app) as client:
    response = client.get("/")
    assert response.status_code == 200

loaded = {
    name
    for name in set(sys.modules) - baseline_modules
    if name.split(".", 1)[0] in blocked
}
assert not loaded, loaded
assert 'google.generativeai' not in sys.modules
'''
    environment = os.environ.copy()
    environment.update(
        {
            "APP_ENV": "test",
            "AUTH_MODE": "strict",
            "SECRET_KEY": secrets.token_urlsafe(32),
            "DATABASE_URL": "sqlite:///:memory:",
            "DEBUG": "false",
            "HF_TOKEN": "",
            "AAI_API_KEY": "",
            "GEMINI_API_KEY": "",
        }
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_job_creation_does_not_initialize_engines(
    db_context, auth_headers, wav_bytes, monkeypatch
):
    def forbidden_initialization(*_args, **_kwargs):
        raise AssertionError("API attempted to initialize processing engines")

    monkeypatch.setattr(
        processing_engines,
        "initialize_processing_engines",
        forbidden_initialization,
    )
    response = db_context["client"].post(
        "/transcriptions/jobs",
        files={"file": ("meeting.wav", wav_bytes, "audio/wav")},
        headers=auth_headers(),
    )

    assert response.status_code == 202


def test_worker_initializes_and_reuses_engine_instances(monkeypatch):
    _reset_engines()
    calls = {name: 0 for name in ("diarization", "whisper", "assemblyai", "gemini")}

    def factory(name):
        def create(_credential):
            calls[name] += 1
            return object()

        return create

    factories = {name: factory(name) for name in calls}
    monkeypatch.setattr(transcription_worker.settings, "HF_TOKEN", "hf_test")
    monkeypatch.setattr(transcription_worker.settings, "AAI_API_KEY", "aai_test")
    monkeypatch.setattr(transcription_worker.settings, "GEMINI_API_KEY", "gemini_test")

    try:
        first = transcription_worker.initialize_worker_engines(factories=factories)
        instances = (
            engine_registry.diarization_engine,
            engine_registry.whisper_engine,
            engine_registry.assemblyai_engine,
            engine_registry.meeting_minutes_generator,
        )
        second = transcription_worker.initialize_worker_engines(factories=factories)

        assert all(first.values())
        assert second == first
        assert calls == {name: 1 for name in calls}
        assert instances == (
            engine_registry.diarization_engine,
            engine_registry.whisper_engine,
            engine_registry.assemblyai_engine,
            engine_registry.meeting_minutes_generator,
        )
        assert transcription_worker.get_processing_service() is (
            transcription_worker.get_processing_service()
        )
    finally:
        _reset_engines()


def test_worker_lazy_initialization_occurs_once_after_job_start(monkeypatch):
    _reset_engines()
    service = object()
    calls = []

    def initialize():
        calls.append("initialized")
        transcription_worker._processing_service = service

    monkeypatch.setattr(transcription_worker, "initialize_worker_engines", initialize)
    try:
        assert transcription_worker.get_processing_service() is service
        assert transcription_worker.get_processing_service() is service
        assert calls == ["initialized"]
    finally:
        _reset_engines()


def test_assemblyai_cloud_worker_initialization_stays_outside_local_ml_stack():
    script = r'''
import importlib.abc
import sys

blocked = {
    "torch", "pyannote", "transformers", "faster_whisper",
    "ctranslate2", "pydub"
}
baseline_modules = set(sys.modules)

class BlockLocalMLImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        root = fullname.split(".", 1)[0]
        if root in blocked or fullname.startswith("google.generativeai"):
            raise RuntimeError(f"local ML import attempted: {fullname}")
        return None

sys.meta_path.insert(0, BlockLocalMLImports())
from src import engine_registry
from src.workers import transcription_worker

first = transcription_worker.get_cloud_processing_service()
second = transcription_worker.get_cloud_processing_service()
assert first is second
assert engine_registry.assemblyai_engine is not None
assert engine_registry.whisper_engine is None
assert engine_registry.diarization_engine is None
assert engine_registry.meeting_minutes_generator is None

loaded = {
    name
    for name in set(sys.modules) - baseline_modules
    if name.split(".", 1)[0] in blocked
    or name.startswith("google.generativeai")
}
assert not loaded, loaded
'''
    environment = os.environ.copy()
    environment.update(
        {
            "APP_ENV": "test",
            "AUTH_MODE": "strict",
            "SECRET_KEY": secrets.token_urlsafe(32),
            "DATABASE_URL": "sqlite:///:memory:",
            "DEBUG": "false",
            "HF_TOKEN": "hf-test",
            "AAI_API_KEY": "aai-test",
            "GEMINI_API_KEY": "gemini-test",
        }
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "path",
    [
        "/transcribe",
        "/diarize",
        "/whisper/transcribe_segment",
        "/assemblyai/transcribe_segment",
    ],
)
def test_unconsumed_legacy_processing_endpoints_are_removed(path):
    registered_paths = set(app.openapi()["paths"])
    assert path not in registered_paths


def test_official_job_endpoints_and_deprecated_gpu_endpoint_remain():
    routes = {
        (path, method.upper())
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    }
    assert ("/transcriptions/jobs", "POST") in routes
    assert ("/transcriptions/jobs/{transcription_id}/status", "GET") in routes
    assert ("/transcriptions/{transcription_id}", "GET") in routes

    with TestClient(app) as client:
        response = client.get("/system/gpu")

    assert response.status_code == 200
    assert response.headers["Deprecation"] == "true"
    assert response.json()["deprecated"] is True


def test_health_degrades_cleanly_when_redis_is_unavailable(monkeypatch):
    monkeypatch.setattr(health, "get_redis_connection", object)
    monkeypatch.setattr(health, "is_redis_available", lambda _connection: False)

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["processing"] == {
        "redis": "unavailable",
        "worker_available": False,
        "worker_count": 0,
        "queue": "transcriptions",
    }
