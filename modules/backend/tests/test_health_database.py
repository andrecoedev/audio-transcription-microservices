from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.database import get_db
from src.routers import health


def test_health_reports_database_unavailable(monkeypatch):
    class UnavailableDatabase:
        def execute(self, _statement):
            raise ConnectionError("database offline")

    app = FastAPI()
    app.include_router(health.router)

    def override_get_db():
        yield UnavailableDatabase()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(
        health,
        "_processing_status",
        lambda: {
            "redis": "connected",
            "queue": "transcriptions",
            "worker_available": False,
            "worker_count": 0,
        },
    )
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["database"] == "unavailable"
    assert response.json()["postgresql"] == "unavailable"
