from datetime import timezone
from io import BytesIO

import pytest

from src.services.object_storage import LocalObjectStorage, ObjectNotFound, StorageError


KEY = "0123456789abcdef0123456789abcdef.wav"


def test_put_open_metadata_materialize_and_delete(tmp_path):
    storage = LocalObjectStorage(tmp_path / "objects")
    payload = b"audio bytes"

    metadata = storage.put(KEY, BytesIO(payload))

    assert metadata.key == KEY
    assert metadata.size_bytes == len(payload)
    assert metadata.modified_at.tzinfo == timezone.utc
    assert storage.exists(KEY)
    assert storage.metadata(KEY) == metadata
    with storage.open(KEY) as stream:
        assert stream.read() == payload
    with storage.materialize(KEY) as path:
        assert path == storage.root / KEY
        assert path.read_bytes() == payload
    storage.delete(KEY)
    storage.delete(KEY)
    assert not storage.exists(KEY)


@pytest.mark.parametrize("key", [
    "../0123456789abcdef0123456789abcdef.wav",
    "C:\\0123456789abcdef0123456789abcdef.wav",
    "/0123456789abcdef0123456789abcdef.wav",
    "0123456789abcdef0123456789abcdef.wav/child",
    "0123456789ABCDEF0123456789ABCDEF.wav",
    "0123456789abcdef0123456789abcdef.wav.exe",
    "not-a-key.wav",
])
def test_rejects_non_opaque_keys(tmp_path, key):
    storage = LocalObjectStorage(tmp_path / "objects")
    with pytest.raises(StorageError, match="Invalid object key"):
        storage.exists(key)


def test_put_does_not_overwrite_existing_object(tmp_path):
    storage = LocalObjectStorage(tmp_path / "objects")
    storage.put(KEY, BytesIO(b"original"))

    with pytest.raises(StorageError, match="already exists"):
        storage.put(KEY, BytesIO(b"replacement"))
    with storage.open(KEY) as stream:
        assert stream.read() == b"original"


def test_missing_operations_have_explicit_behavior(tmp_path):
    storage = LocalObjectStorage(tmp_path / "objects")
    assert storage.exists(KEY) is False
    storage.delete(KEY)
    for operation in (storage.open, storage.metadata, storage.materialize):
        with pytest.raises(ObjectNotFound):
            result = operation(KEY)
            if hasattr(result, "__enter__"):
                with result:
                    pass


def test_symlink_object_is_never_read_or_materialized(tmp_path):
    storage = LocalObjectStorage(tmp_path / "objects")
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"private")
    try:
        (storage.root / KEY).symlink_to(outside)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows requires symlink privilege; exercised in Linux CI")
        raise

    with pytest.raises(StorageError):
        storage.exists(KEY)
    with pytest.raises(StorageError):
        with storage.open(KEY):
            pass
    with pytest.raises(StorageError):
        with storage.materialize(KEY):
            pass


def test_source_read_failure_leaves_no_partial_object_or_temp_file(tmp_path):
    storage = LocalObjectStorage(tmp_path / "objects")

    class BrokenSource:
        def __init__(self):
            self.calls = 0

        def read(self, size=-1):
            self.calls += 1
            if self.calls == 1:
                return b"partial"
            raise OSError("source path and sensitive detail")

    with pytest.raises(StorageError) as error:
        storage.put(KEY, BrokenSource())
    assert "sensitive detail" not in str(error.value)
    assert not storage.exists(KEY)
    assert list(storage.root.iterdir()) == []
