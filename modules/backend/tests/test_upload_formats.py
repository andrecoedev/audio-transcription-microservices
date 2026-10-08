import pytest
from pydantic import ValidationError

from src.config import Settings, settings
from src.routers.guests import guest_policy
from src.utils.upload_formats import DEFAULT_ALLOWED_EXTENSIONS
from src.utils.uploads import _detected_format, _format_matches_extension


@pytest.mark.parametrize(
    "frame",
    [
        b"\xff\xfb\x90\x64",  # MPEG-1 Layer III
        b"\xff\xf3\x90\x64",  # MPEG-2 Layer III
        b"\xff\xe3\x90\x64",  # MPEG-2.5 Layer III
        b"\xff\xfd\x90\x64",  # MPEG-1 Layer II (legacy .mpeg)
    ],
)
def test_recognizes_mpeg_audio_frame_headers(frame):
    detected = _detected_format(frame)
    assert detected == "mpeg-audio"
    assert _format_matches_extension(detected, "mp3")
    assert _format_matches_extension(detected, "mpeg")


def test_rejects_reserved_mpeg_frame_header_fields():
    assert _detected_format(b"\xff\xe0\xf0\x00") is None
    assert _detected_format(b"\xff\xfb\xfc\x00") is None


def test_recognizes_rf64_wave_header():
    assert _detected_format(b"RF64\xff\xff\xff\xffWAVEds64") == "wav"


def test_rejects_rf64_without_required_ds64_chunk():
    assert _detected_format(b"RF64\xff\xff\xff\xffWAVEdata") is None


def test_upload_extension_allowlist_is_central_and_exposed_to_policy():
    defaults = Settings(
        _env_file=None,
        DATABASE_URL="postgresql+psycopg://user:pass@localhost/db",
    )
    assert tuple(defaults.allowed_extensions_list) == DEFAULT_ALLOWED_EXTENSIONS
    assert guest_policy()["allowed_extensions"] == settings.allowed_extensions_list


def test_unsupported_configured_extension_fails_with_clear_validation_error():
    with pytest.raises(ValidationError, match="unsupported upload extension"):
        Settings(
            _env_file=None,
            DATABASE_URL="postgresql+psycopg://user:pass@localhost/db",
            ALLOWED_EXTENSIONS="mp3,avi",
        )


def test_configured_extensions_are_normalized_and_deduplicated():
    configured = Settings(
        _env_file=None,
        DATABASE_URL="postgresql+psycopg://user:pass@localhost/db",
        ALLOWED_EXTENSIONS=".MP3, wav, mp3",
    )
    assert configured.allowed_extensions_list == ["mp3", "wav"]
