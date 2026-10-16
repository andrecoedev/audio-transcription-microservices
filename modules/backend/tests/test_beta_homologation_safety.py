"""The test-only HTTP harness must never launch against a persistent database."""
import pytest
from tests.homologation.server import main


@pytest.mark.parametrize("environment,database", [
    ("dev", "postgresql://localhost/usagi_beta_e2e_test"),
    ("test", "postgresql://localhost/transcription_db"),
    ("test", "sqlite:///:memory:"),
])
def test_homologation_refuses_nonisolated_target(monkeypatch, environment, database):
    monkeypatch.setenv("APP_ENV", environment)
    monkeypatch.setenv("DATABASE_URL", database)
    with pytest.raises(RuntimeError, match="dedicated disposable"):
        main()


def test_homologation_refuses_external_credentials(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/usagi_beta_e2e_test")
    monkeypatch.setenv("AAI_API_KEY", "clearly-synthetic-test-value")
    with pytest.raises(RuntimeError, match="must not receive external credentials"):
        main()
