"""Validação e persistência segura de uploads de áudio/vídeo."""

import logging
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import aiofiles
from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from ..services.object_storage import ObjectStorage, StorageError
from .upload_formats import UPLOAD_EXTENSION_FORMATS

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 1024 * 1024


class UploadValidationError(ValueError):
    def __init__(self, detail: str, status_code: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


@dataclass(frozen=True)
class SavedUpload:
    path: Path
    original_filename: str
    extension: str
    size_bytes: int


@dataclass(frozen=True)
class StoredUpload:
    key: str
    original_filename: str
    extension: str
    size_bytes: int


class StorageUploadLimitError(StorageError):
    """The upload stream exceeded its configured maximum size."""


class _LimitedUploadReader:
    """Synchronous view of an upload stream that rejects bytes past the limit."""

    def __init__(self, source: BinaryIO, max_size_bytes: int):
        self.source = source
        self.max_size_bytes = max_size_bytes
        self.size_bytes = 0

    def read(self, size: int = -1) -> bytes:
        remaining = self.max_size_bytes - self.size_bytes
        # Read one byte beyond the remaining budget to detect oversize input.
        request_size = remaining + 1 if size < 0 else min(size, remaining + 1)
        chunk = self.source.read(request_size)
        if len(chunk) > remaining:
            raise StorageUploadLimitError("Upload exceeds configured size limit")
        self.size_bytes += len(chunk)
        return chunk


def sanitize_filename(filename: str | None) -> str:
    """Keep the visible basename while removing paths and unsafe format controls."""
    basename = Path((filename or "upload").replace("\\", "/")).name
    basename = "".join(
        character
        for character in basename
        if unicodedata.category(character) not in {"Cc", "Cf"}
    )
    if basename in {"", ".", ".."}:
        return "upload"
    if len(basename) <= 255:
        return basename

    suffix = Path(basename).suffix
    extension = suffix[1:]
    if (
        len(suffix) <= 11
        and extension
        and extension.isascii()
        and extension.isalnum()
    ):
        return basename[: 255 - len(suffix)] + suffix
    return basename[:255]


def _detected_format(header: bytes) -> str | None:
    if len(header) >= 12 and header[8:12] == b"WAVE":
        if header[:4] == b"RIFF":
            return "wav"
        if len(header) >= 16 and header[:4] == b"RF64" and header[12:16] == b"ds64":
            return "wav"
    if header.startswith(b"fLaC"):
        return "flac"
    if header.startswith(b"OggS") and len(header) >= 5 and header[4] == 0:
        return "ogg"
    if header.startswith(b"ID3") and _has_valid_id3_header(header):
        return "mpeg-audio"
    if _has_mpeg_audio_frame(header):
        return "mpeg-audio"
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return "iso-bmff"
    return None


def _has_valid_id3_header(header: bytes) -> bool:
    if len(header) < 10 or header[3] not in {2, 3, 4} or header[4] == 0xFF:
        return False
    return all(byte & 0x80 == 0 for byte in header[6:10])


def _has_mpeg_audio_frame(header: bytes) -> bool:
    if len(header) < 4 or header[0] != 0xFF or (header[1] & 0xE0) != 0xE0:
        return False
    version = (header[1] >> 3) & 0x03
    layer = (header[1] >> 1) & 0x03
    bitrate_index = (header[2] >> 4) & 0x0F
    sample_rate_index = (header[2] >> 2) & 0x03
    return (
        version != 0x01
        and layer != 0x00
        and bitrate_index != 0x0F
        and sample_rate_index != 0x03
    )


def _format_matches_extension(detected: str, extension: str) -> bool:
    return UPLOAD_EXTENSION_FORMATS.get(extension) == detected


async def save_validated_upload(
    upload: UploadFile,
    destination: Path,
    allowed_extensions: list[str],
    max_size_bytes: int,
) -> SavedUpload:
    """Valida nome, extensão, tamanho e assinatura antes de persistir o upload."""
    safe_name = sanitize_filename(upload.filename)
    extension = Path(safe_name).suffix.lower().lstrip(".")
    allowed = {item.lower().lstrip(".") for item in allowed_extensions}

    if not extension or extension not in allowed:
        logger.warning("Upload rejected: unsupported extension")
        raise UploadValidationError(
            f"File extension '{extension or 'missing'}' is not allowed",
            status_code=415,
        )

    first_chunk = await upload.read(_CHUNK_SIZE)
    if not first_chunk:
        logger.warning("Upload rejected: empty file")
        raise UploadValidationError("Uploaded file is empty")

    detected = _detected_format(first_chunk[:64])
    if detected is None or not _format_matches_extension(detected, extension):
        logger.warning(
            "Upload rejected: content signature does not match extension '%s'",
            extension,
        )
        raise UploadValidationError(
            "File content does not match a supported audio/video format",
            status_code=415,
        )

    destination.mkdir(parents=True, exist_ok=True)
    stored_path = destination / f"{uuid.uuid4().hex}.{extension}"
    size_bytes = 0

    try:
        async with aiofiles.open(stored_path, "wb") as output:
            chunk = first_chunk
            while chunk:
                size_bytes += len(chunk)
                if size_bytes > max_size_bytes:
                    logger.warning("Upload rejected: file exceeds configured size limit")
                    raise UploadValidationError(
                        "File size exceeds the maximum allowed size",
                        status_code=413,
                    )
                await output.write(chunk)
                chunk = await upload.read(_CHUNK_SIZE)
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise

    return SavedUpload(
        path=stored_path,
        original_filename=safe_name,
        extension=extension,
        size_bytes=size_bytes,
    )


async def store_validated_upload(
    upload: UploadFile,
    storage: ObjectStorage,
    allowed_extensions: list[str],
    max_size_bytes: int,
) -> StoredUpload:
    """Validate and store an upload directly under a generated opaque key."""
    safe_name = sanitize_filename(upload.filename)
    extension = Path(safe_name).suffix.lower().lstrip(".")
    allowed = {item.lower().lstrip(".") for item in allowed_extensions}

    if not extension or extension not in allowed:
        logger.warning("Upload rejected: unsupported extension")
        raise UploadValidationError(
            f"File extension '{extension or 'missing'}' is not allowed",
            status_code=415,
        )

    first_chunk = await upload.read(_CHUNK_SIZE)
    if not first_chunk:
        logger.warning("Upload rejected: empty file")
        raise UploadValidationError("Uploaded file is empty")

    detected = _detected_format(first_chunk[:64])
    if detected is None or not _format_matches_extension(detected, extension):
        logger.warning(
            "Upload rejected: content signature does not match extension '%s'",
            extension,
        )
        raise UploadValidationError(
            "File content does not match a supported audio/video format",
            status_code=415,
        )

    source = _LimitedUploadReader(upload.file, max_size_bytes)
    try:
        upload.file.seek(0)
        source.size_bytes = 0
        key = f"{uuid.uuid4().hex}.{extension}"
        await run_in_threadpool(storage.put, key, source)
    except StorageUploadLimitError:
        logger.warning("Upload rejected: file exceeds configured size limit")
        raise UploadValidationError(
            "File size exceeds the maximum allowed size",
            status_code=413,
        ) from None
    except StorageError:
        logger.error("Upload storage failed")
        raise StorageError("Unable to store upload") from None
    except Exception:
        logger.error("Upload storage failed")
        raise StorageError("Unable to store upload") from None

    return StoredUpload(
        key=key,
        original_filename=safe_name,
        extension=extension,
        size_bytes=source.size_bytes,
    )
