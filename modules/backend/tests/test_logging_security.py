from src.logging_config import redact_sensitive_text


def test_log_redaction_removes_tokens_keys_passwords_urls_and_email():
    source = (
        "Authorization: Bearer abc.def.ghi "
        "api_key=super-secret password=hunter2 "
        "postgresql+psycopg://user:db-secret@postgres/app "
        "alice@example.com"
    )
    redacted = redact_sensitive_text(source)
    for secret in ("abc.def.ghi", "super-secret", "hunter2", "db-secret", "alice@example.com"):
        assert secret not in redacted
    assert "[REDACTED]" in redacted
    assert "[REDACTED_EMAIL]" in redacted
