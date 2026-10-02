import pytest
from pydantic import ValidationError

from src.config import Settings


def test_invalid_settings_error_does_not_echo_secrets(monkeypatch):
    secret = "private_test_credential_value"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError) as captured:
        Settings(_env_file=None, HF_TOKEN=secret)

    assert secret not in str(captured.value)
    assert "input_value" not in str(captured.value)
