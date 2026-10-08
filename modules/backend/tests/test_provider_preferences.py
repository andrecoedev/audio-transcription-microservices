"""Permanent security and persistence coverage for account provider settings."""

import secrets

from cryptography.fernet import Fernet
import pytest

from src.config import settings
from src.models import PlatformProviderBudget, Transcription, TranscriptionJob, User, UserProviderCredential, UserProviderPreferences
from src.services.provider_credentials import decrypt_credential, resolve_transcription


@pytest.fixture
def credential_cipher(monkeypatch):
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(settings, "PROVIDER_CREDENTIAL_ENCRYPTION_KEY", key)
    return key


def _save(client, headers, provider="assemblyai", secret=None):
    # Synthetic input generated per call; never a real provider credential.
    if secret is None:
        secret = secrets.token_urlsafe(32)
    return client.post(
        f"/settings/providers/{provider}/credential",
        json={"secret": secret},
        headers=headers,
    )


def test_settings_are_account_scoped_and_credentials_are_write_only(
    db_context, auth_headers, credential_cipher
):
    client = db_context["client"]
    alice_headers, bob_headers = auth_headers(), auth_headers(username="bob")
    default = client.get("/settings/providers", headers=alice_headers)
    assert default.status_code == 200
    assert default.json()["preferences"] == {
        "transcription_provider": "automatic",
        "intelligence_provider": "automatic",
        "use_diarization": False,
    }

    secret = secrets.token_urlsafe(32)
    saved = _save(client, alice_headers, secret=secret)
    assert saved.status_code == 200
    assert secret not in saved.text
    assert "ciphertext" not in saved.text
    assert saved.json()["credentials"]["assemblyai"]["configured"] is True
    assert saved.json()["providers"]["assemblyai"]["credential_source"] == "user"

    bob = client.get("/settings/providers", headers=bob_headers)
    assert bob.status_code == 200
    assert bob.json()["credentials"]["assemblyai"]["configured"] is False
    assert bob.json()["providers"]["assemblyai"]["credential_source"] is None

    db = db_context["session_factory"]()
    try:
        row = db.query(UserProviderCredential).filter_by(user_id=1, provider="assemblyai").one()
        assert row.ciphertext != secret
        assert secret not in row.ciphertext
        assert decrypt_credential(db, row.id, 1, "assemblyai") == secret
        assert db.query(UserProviderCredential).filter_by(user_id=2).count() == 0
    finally:
        db.close()


def test_preferences_persist_across_requests_and_invalid_values_are_rejected(
    db_context, auth_headers, credential_cipher
):
    client = db_context["client"]
    headers = auth_headers()
    assert _save(client, headers).status_code == 200
    response = client.patch(
        "/settings/providers",
        json={"transcription_provider": "assemblyai", "intelligence_provider": "automatic", "use_diarization": True},
        headers=headers,
    )
    assert response.status_code == 200
    refreshed = client.get("/settings/providers", headers=headers)
    assert refreshed.json()["preferences"] == {
        "transcription_provider": "assemblyai",
        "intelligence_provider": "automatic",
        "use_diarization": True,
    }
    assert client.patch(
        "/settings/providers",
        json={"transcription_provider": "gemini", "intelligence_provider": "automatic", "use_diarization": False},
        headers=headers,
    ).status_code == 422

    db = db_context["session_factory"]()
    try:
        row = db.get(UserProviderPreferences, 1)
        assert (row.transcription_provider, row.use_diarization) == ("assemblyai", True)
    finally:
        db.close()


def test_rotation_revokes_queued_reference_and_delete_is_owner_scoped_and_idempotent(
    db_context, auth_headers, credential_cipher
):
    client = db_context["client"]
    headers = auth_headers()
    assert _save(client, headers).status_code == 200
    db = db_context["session_factory"]()
    old = db.query(UserProviderCredential).filter_by(user_id=1, provider="assemblyai").one()
    transcription = Transcription(
        filename="a.wav", original_filename="a.wav", file_size_mb=0.01,
        duration_seconds=1, transcription_model="assemblyai", status="queued", segments=[],
    )
    db.add(transcription)
    db.flush()
    job = TranscriptionJob(transcription_id=transcription.id, input_path="a.wav", transcription_model="assemblyai", status="queued", credential_source="user", credential_id=old.id, credential_user_id=1)
    db.add(job)
    db.commit()
    old_id = old.id
    db.close()

    rotated = _save(client, headers)
    assert rotated.status_code == 200
    db = db_context["session_factory"]()
    try:
        job = db.query(TranscriptionJob).one()
        current = db.query(UserProviderCredential).filter_by(user_id=1, provider="assemblyai").one()
        assert job.credential_id is None  # FK SET NULL prevents queued jobs adopting replacement.
        assert current.id != old_id
        assert db.get(UserProviderCredential, old_id) is None
    finally:
        db.close()

    bob_headers = auth_headers(username="bob")
    assert client.delete("/settings/providers/assemblyai/credential", headers=bob_headers).status_code == 200
    assert client.get("/settings/providers", headers=headers).json()["credentials"]["assemblyai"]["configured"] is True
    assert client.delete("/settings/providers/assemblyai/credential", headers=headers).status_code == 200
    assert client.delete("/settings/providers/assemblyai/credential", headers=headers).status_code == 200
    db = db_context["session_factory"]()
    try:
        assert db.query(UserProviderCredential).count() == 0
    finally:
        db.close()


def test_credential_configuration_and_provider_inputs_fail_closed(
    db_context, auth_headers, monkeypatch
):
    client, headers = db_context["client"], auth_headers()
    secret = secrets.token_urlsafe(32)
    monkeypatch.setattr(settings, "PROVIDER_CREDENTIAL_ENCRYPTION_KEY", None)
    unavailable = _save(client, headers, secret=secret)
    assert unavailable.status_code == 503
    assert secret not in unavailable.text
    # The JWT signing key is not an acceptable substitute for the independent
    # at-rest encryption key, even though it is valid key material.
    monkeypatch.setattr(settings, "PROVIDER_CREDENTIAL_ENCRYPTION_KEY", settings.SECRET_KEY)
    reused_jwt_key = _save(client, headers, secret=secret)
    assert reused_jwt_key.status_code == 503
    assert secret not in reused_jwt_key.text
    db = db_context["session_factory"]()
    try:
        assert db.query(UserProviderCredential).count() == 0
    finally:
        db.close()

    monkeypatch.setattr(settings, "PROVIDER_CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    assert _save(client, headers, provider="unknown").status_code == 404
    assert client.get("/settings/providers").status_code == 401
    assert client.patch(
        "/settings/providers",
        json={"transcription_provider": "automatic", "intelligence_provider": "automatic", "use_diarization": False},
    ).status_code == 401


def test_main_validation_handler_never_echoes_rejected_secret():
    import asyncio
    from fastapi.exceptions import RequestValidationError
    from src.main import safe_validation_error

    rejected = "synthetic invalid input with spaces"
    error = RequestValidationError([{
        "type": "value_error", "loc": ("body", "secret"),
        "msg": "Invalid provider credential format", "input": rejected,
    }])
    response = asyncio.run(safe_validation_error(None, error))
    assert response.status_code == 422
    assert rejected.encode() not in response.body


def test_ciphertext_swap_between_accounts_or_providers_cannot_decrypt(
    db_context, auth_headers, credential_cipher
):
    client = db_context["client"]
    assert _save(client, auth_headers()).status_code == 200
    assert _save(client, auth_headers(username="bob")).status_code == 200
    assert _save(client, auth_headers(), provider="gemini").status_code == 200
    db = db_context["session_factory"]()
    try:
        aai = db.query(UserProviderCredential).filter_by(user_id=1, provider="assemblyai").one()
        bob_aai = db.query(UserProviderCredential).filter_by(user_id=2, provider="assemblyai").one()
        gemini = db.query(UserProviderCredential).filter_by(user_id=1, provider="gemini").one()
        aai_ciphertext, bob_ciphertext = aai.ciphertext, bob_aai.ciphertext
        aai.ciphertext, bob_aai.ciphertext = bob_ciphertext, aai_ciphertext
        db.commit()
        with pytest.raises(RuntimeError, match="credential is unavailable"):
            decrypt_credential(db, aai.id, 1, "assemblyai")
        aai.ciphertext, bob_aai.ciphertext = aai_ciphertext, bob_ciphertext
        gemini_ciphertext = gemini.ciphertext
        aai.ciphertext, gemini.ciphertext = gemini_ciphertext, aai_ciphertext
        db.commit()
        with pytest.raises(RuntimeError, match="credential is unavailable"):
            decrypt_credential(db, aai.id, 1, "assemblyai")
        with pytest.raises(RuntimeError, match="credential is unavailable"):
            decrypt_credential(db, aai.id, 2, "assemblyai")
        with pytest.raises(RuntimeError, match="credential is unavailable"):
            decrypt_credential(db, gemini.id, 1, "gemini")
    finally:
        db.close()


def test_automatic_transcription_uses_own_assemblyai_else_whisper_without_fallback(
    db_context, auth_headers, credential_cipher, monkeypatch
):
    from src.models import User

    db = db_context["session_factory"]()
    assert db.get(User, 1) is not None
    assert resolve_transcription(db, type("Identity", (), {"user_id": 1})(), None)["provider"] == "whisper"
    monkeypatch.setattr(settings, "AAI_API_KEY", "")
    monkeypatch.setattr(settings, "AAI_API_KEY_CONFIGURED", False)
    monkeypatch.setattr(settings, "AAI_PLATFORM_ENABLED", False)
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        resolve_transcription(db, type("Identity", (), {"user_id": 2, "registration_source": "public"})(), "assemblyai")
    db.add(UserProviderCredential(id="credential-aai", user_id=1, provider="assemblyai", ciphertext="ciphertext"))
    db.commit()
    selection = resolve_transcription(db, type("Identity", (), {"user_id": 1})(), "automatic")
    assert selection == {"provider": "assemblyai", "credential_source": "user", "credential_id": "credential-aai", "credential_user_id": 1}
    assert resolve_transcription(db, type("Identity", (), {"user_id": 2})(), "automatic")["provider"] == "whisper"
    db.close()


def test_public_account_upload_queues_byok_reference_without_platform_reservation(
    db_context, auth_headers, credential_cipher, monkeypatch, wav_bytes
):
    from src.models import User
    from src.routers import transcriptions

    assert _save(db_context["client"], auth_headers()).status_code == 200
    db = db_context["session_factory"]()
    try:
        db.get(User, 1).registration_source = "public"
        db.commit()
    finally:
        db.close()
    monkeypatch.setattr(
        transcriptions, "reserve_platform_call",
        lambda *_args, **_kwargs: pytest.fail("BYOK must not reserve a platform call"),
    )

    response = db_context["client"].post(
        "/transcriptions/jobs", files={"file": ("meeting.wav", wav_bytes, "audio/wav")},
        headers=auth_headers(),
    )
    assert response.status_code == 202
    db = db_context["session_factory"]()
    try:
        job = db.query(TranscriptionJob).one()
        credential = db.query(UserProviderCredential).filter_by(user_id=1, provider="assemblyai").one()
        assert job.transcription_model == "assemblyai"
        assert (job.credential_source, job.credential_id, job.credential_user_id) == ("user", credential.id, 1)
    finally:
        db.close()


def test_platform_access_is_separate_from_byok_and_storage_capability(
    db_context, auth_headers, credential_cipher, monkeypatch
):
    from src.services.platform_budget import platform_reservation_amount_cents

    client = db_context["client"]
    headers = auth_headers()
    monkeypatch.setattr(settings, "AAI_API_KEY_CONFIGURED", True)
    monkeypatch.setattr(settings, "AAI_API_KEY", "")
    monkeypatch.setattr(settings, "AAI_PLATFORM_ENABLED", True)
    monkeypatch.setattr(settings, "AAI_PLATFORM_BUDGET_CENTS", 100)
    monkeypatch.setattr(settings, "AAI_MAX_AUDIO_SECONDS", 600)
    monkeypatch.setattr(settings, "GEMINI_API_KEY_CONFIGURED", True)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")

    # Public accounts cannot inherit configured platform credentials.
    db = db_context["session_factory"]()
    try:
        db.get(User, 1).registration_source = "public"
        db.commit()
    finally:
        db.close()
    public_view = client.get("/settings/providers", headers=headers).json()
    assert public_view["providers"]["assemblyai"]["platform_access"] is False
    assert public_view["providers"]["assemblyai"]["allowed"] is False

    # A user credential remains usable when platform access is off.
    monkeypatch.setattr(settings, "AAI_PLATFORM_ENABLED", False)
    byok = _save(client, headers, secret=secrets.token_urlsafe(32))
    assert byok.status_code == 200
    byok_view = byok.json()
    assert byok_view["providers"]["assemblyai"]["platform_access"] is False
    assert byok_view["providers"]["assemblyai"]["allowed"] is True
    assert byok_view["providers"]["assemblyai"]["credential_source"] == "user"

    # A local account can use platform access without BYOK encryption storage.
    db = db_context["session_factory"]()
    try:
        db.get(User, 1).registration_source = "local"
        db.query(UserProviderCredential).filter_by(user_id=1, provider="assemblyai").delete()
        db.commit()
    finally:
        db.close()
    monkeypatch.setattr(settings, "AAI_PLATFORM_ENABLED", True)
    monkeypatch.setattr(settings, "PROVIDER_CREDENTIAL_ENCRYPTION_KEY", None)
    platform_view = client.get("/settings/providers", headers=headers).json()
    assert platform_view["credential_storage_available"] is False
    assert platform_view["providers"]["assemblyai"]["platform_access"] is True
    assert platform_view["providers"]["assemblyai"]["allowed"] is True
    assert platform_view["providers"]["assemblyai"]["credential_source"] == "platform"
    rejected_secret = secrets.token_urlsafe(32)
    rejected = _save(client, headers, secret=rejected_secret)
    assert rejected.status_code == 503
    assert rejected_secret not in rejected.text

    # Exhausted cumulative budget removes platform access without disclosing amounts.
    exhausted = db_context["session_factory"]()
    try:
        exhausted.add(PlatformProviderBudget(
            provider="assemblyai", limit_cents=100,
            reserved_cents=100 - platform_reservation_amount_cents() + 1,
        ))
        exhausted.commit()
    finally:
        exhausted.close()
    exhausted_view = client.get("/settings/providers", headers=headers).json()
    assert exhausted_view["providers"]["assemblyai"]["platform_access"] is False
    assert exhausted_view["providers"]["assemblyai"]["allowed"] is False
    assert "reserved_cents" not in str(exhausted_view)
    assert "limit_cents" not in str(exhausted_view)
