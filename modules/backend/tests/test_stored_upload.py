from io import BytesIO

import pytest
from starlette.datastructures import UploadFile

from src.services.object_storage import LocalObjectStorage, StorageError
from src.utils.uploads import (
    StoredUpload,
    UploadValidationError,
    sanitize_filename,
    store_validated_upload,
)


WAV = b"RIFF" + (4).to_bytes(4, "little") + b"WAVE" + b"data"


def upload(filename: str, payload: bytes) -> UploadFile:
    return UploadFile(filename=filename, file=BytesIO(payload))


@pytest.mark.asyncio
async def test_stores_valid_upload_with_opaque_key_and_original_name(tmp_path):
    storage = LocalObjectStorage(tmp_path / "objects")

    result = await store_validated_upload(
        upload("../../Reunião da equipe 2026.wav", WAV),
        storage,
        ["wav"],
        1024,
    )

    assert isinstance(result, StoredUpload)
    assert result.key.endswith(".wav")
    assert "/" not in result.key and "\\" not in result.key
    assert result.original_filename == "Reunião da equipe 2026.wav"
    assert result.extension == "wav"
    assert result.size_bytes == len(WAV)
    with storage.open(result.key) as stream:
        assert stream.read() == WAV


@pytest.mark.asyncio
async def test_repeated_original_names_keep_distinct_opaque_storage_keys(tmp_path):
    storage = LocalObjectStorage(tmp_path / "objects")

    first = await store_validated_upload(
        upload("Reunião.wav", WAV), storage, ["wav"], 1024
    )
    second = await store_validated_upload(
        upload("Reunião.wav", WAV), storage, ["wav"], 1024
    )

    assert first.original_filename == second.original_filename == "Reunião.wav"
    assert first.key != second.key


def test_filename_removes_controls_and_bidi_formatting_but_keeps_visible_unicode():
    assert sanitize_filename("ReuniÃ£o\x00\r\n\u202eFinal.wav") == "ReuniÃ£oFinal.wav"


@pytest.mark.asyncio
async def test_long_filename_is_capped_without_losing_supported_extension(tmp_path):
    storage = LocalObjectStorage(tmp_path / "objects")

    result = await store_validated_upload(
        upload(f"{ 'á' * 300 }.wav", WAV), storage, ["wav"], 1024
    )

    assert len(result.original_filename) == 255
    assert result.original_filename.endswith(".wav")
    assert result.extension == "wav"


@pytest.mark.asyncio
async def test_rejects_invalid_signature_without_storing(tmp_path):
    storage = LocalObjectStorage(tmp_path / "objects")

    with pytest.raises(UploadValidationError) as error:
        await store_validated_upload(
            upload("recording.wav", b"not audio"), storage, ["wav"], 1024
        )

    assert error.value.status_code == 415
    assert list(storage.root.iterdir()) == []


@pytest.mark.asyncio
async def test_streamed_oversize_rejects_and_leaves_no_object_or_temp_file(tmp_path):
    storage = LocalObjectStorage(tmp_path / "objects")

    with pytest.raises(UploadValidationError) as error:
        await store_validated_upload(
            upload("recording.wav", WAV), storage, ["wav"], len(WAV) - 1
        )

    assert error.value.status_code == 413
    assert list(storage.root.iterdir()) == []


@pytest.mark.asyncio
async def test_storage_failure_is_sanitized():
    class FailingStorage:
        def put(self, key, source):
            raise StorageError("C:/private/path and secret detail")

    with pytest.raises(StorageError) as error:
        await store_validated_upload(
            upload("recording.wav", WAV), FailingStorage(), ["wav"], 1024
        )

    assert str(error.value) == "Unable to store upload"
    assert "private" not in str(error.value)
    assert "secret" not in str(error.value)
