"""Vendor-neutral object storage contract and a safe local implementation."""

from __future__ import annotations

import os
import logging
import re
import shutil
import stat
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, ContextManager, Iterator, Protocol

logger = logging.getLogger(__name__)


class StorageError(Exception):
    """A storage operation failed; messages intentionally omit local paths."""


class ObjectNotFound(StorageError):
    """The requested object does not exist."""


@dataclass(frozen=True)
class ObjectMetadata:
    key: str
    size_bytes: int
    modified_at: datetime


class ObjectStorage(Protocol):
    def put(self, key: str, source: BinaryIO) -> ObjectMetadata: ...

    def open(self, key: str) -> ContextManager[BinaryIO]: ...

    def delete(self, key: str) -> None: ...

    def exists(self, key: str) -> bool: ...

    def metadata(self, key: str) -> ObjectMetadata: ...

    def materialize(self, key: str) -> ContextManager[Path]: ...


_KEY_PATTERN = re.compile(r"^[a-f0-9]{32}\.[a-z0-9]{1,8}$")


class LocalObjectStorage:
    """Store opaque object keys as files directly beneath a private directory."""

    def __init__(self, root: Path):
        self.root = Path(root)
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            if self.root.is_symlink() or not self.root.is_dir():
                raise StorageError("Storage root is unavailable")
            self.root = self.root.resolve(strict=True)
        except StorageError:
            raise
        except OSError:
            raise StorageError("Storage root is unavailable") from None

    @staticmethod
    def _validate_key(key: str) -> None:
        if not isinstance(key, str) or _KEY_PATTERN.fullmatch(key) is None:
            raise StorageError("Invalid object key")

    def _path(self, key: str) -> Path:
        self._validate_key(key)
        path = self.root / key
        if path.parent != self.root:
            raise StorageError("Invalid object key")
        return path

    def _regular_stat(self, key: str) -> os.stat_result:
        path = self._path(key)
        try:
            result = path.stat(follow_symlinks=False)
        except FileNotFoundError:
            raise ObjectNotFound("Object not found") from None
        except OSError:
            raise StorageError("Unable to inspect object") from None
        if not stat.S_ISREG(result.st_mode):
            raise StorageError("Object is not a regular file")
        return result

    @staticmethod
    def _metadata(key: str, result: os.stat_result) -> ObjectMetadata:
        return ObjectMetadata(
            key=key,
            size_bytes=result.st_size,
            modified_at=datetime.fromtimestamp(result.st_mtime, tz=timezone.utc),
        )

    def put(self, key: str, source: BinaryIO) -> ObjectMetadata:
        target = self._path(key)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.root, prefix=".upload-", delete=False) as temp:
                temp_path = Path(temp.name)
                shutil.copyfileobj(source, temp)
                temp.flush()
                os.fsync(temp.fileno())
            # link() is atomic and fails if the destination already exists.
            os.link(temp_path, target)
            return self.metadata(key)
        except FileExistsError:
            raise StorageError("Object already exists") from None
        except StorageError:
            raise
        except OSError:
            raise StorageError("Unable to store object") from None
        except Exception:
            # Source read errors are deliberately converted to a safe public error.
            raise StorageError("Unable to read object source") from None
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    logger.warning("Storage staging cleanup failed; reconciliation required")

    @contextmanager
    def open(self, key: str) -> Iterator[BinaryIO]:
        path = self._path(key)
        self._regular_stat(key)
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                os.close(descriptor)
                raise StorageError("Object is not a regular file")
        except FileNotFoundError:
            raise ObjectNotFound("Object not found") from None
        except StorageError:
            raise
        except OSError:
            raise StorageError("Unable to open object") from None
        try:
            stream = os.fdopen(descriptor, "rb")
        except OSError:
            os.close(descriptor)
            raise StorageError("Unable to open object") from None
        with stream:
            yield stream

    def delete(self, key: str) -> None:
        path = self._path(key)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            raise StorageError("Unable to delete object") from None

    def exists(self, key: str) -> bool:
        try:
            self._regular_stat(key)
            return True
        except ObjectNotFound:
            return False

    def metadata(self, key: str) -> ObjectMetadata:
        return self._metadata(key, self._regular_stat(key))

    @contextmanager
    def materialize(self, key: str) -> Iterator[Path]:
        path = self._path(key)
        self._regular_stat(key)
        yield path
