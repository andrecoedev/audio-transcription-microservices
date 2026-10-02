"""Validação e persistência segura de uploads de áudio/vídeo."""

import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

import aiofiles
from fastapi import UploadFile

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 1024 * 1024
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._ -]+")


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


def sanitize_filename(filename: str | None) -> str:
    """Remove componentes de caminho e caracteres inadequados para exibição."""
    basename = Path((filename or "upload").replace("\\", "/")).name
    sanitized = _SAFE_FILENAME_RE.sub("_", basename).strip(" .")
    return sanitized[:255] or "upload"


def _detected_format(header: bytes) -> str | None:
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WAVE":
        return "wav"
    if header.startswith(b"fLaC"):
        return "flac"
    if header.startswith(b"OggS"):
        return "ogg"
    if header.startswith(b"ID3") or (
        len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0
    ):
        return "mpeg"
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return "mp4"
    return None


def _format_matches_extension(detected: str, extension: str) -> bool:
    compatible_extensions = {
        "wav": {"wav"},
        "flac": {"flac"},
        "ogg": {"ogg", "opus"},
        "mpeg": {"mp3", "mpeg"},
        "mp4": {"mp4", "m4a"},
    }
    return extension in compatible_extensions.get(detected, set())


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
