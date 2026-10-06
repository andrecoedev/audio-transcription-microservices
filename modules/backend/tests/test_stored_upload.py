from io import BytesIO

import pytest
from starlette.datastructures import UploadFile

from src.services.object_storage import LocalObjectStorage, StorageError
from src.utils.uploads import StoredUpload, UploadValidationError, store_validated_upload


WAV = b"RIFF" + (4).to_bytes(4, "little") + b"WAVE" + b"data"


def upload(filename: str, payload: bytes) -> UploadFile:
    return UploadFile(filename=filename, file=BytesIO(payload))


@pytest.mark.asyncio
async def test_stores_valid_upload_with_opaque_key_and_sanitized_name(tmp_path):
    storage = LocalObjectStorage(tmp_path / "objects")

    result = await store_validated_upload(
        upload("../../private meeting?.wav", WAV),
        storage,
        ["wav"],
        1024,
    )

    assert isinstance(result, StoredUpload)
    assert result.key.endswith(".wav")
    assert "/" not in result.key and "\\" not in result.key
    assert result.original_filename == "private meeting_.wav"
    assert result.extension == "wav"
    assert result.size_bytes == len(WAV)
    with storage.open(result.key) as stream:
        assert stream.read() == WAV


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
