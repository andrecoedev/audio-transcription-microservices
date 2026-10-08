"""Supported upload extensions and their container/signature families."""

UPLOAD_EXTENSION_FORMATS = {
    "mp3": "mpeg-audio",
    "wav": "wav",
    "mp4": "iso-bmff",
    "mpeg": "mpeg-audio",
    "m4a": "iso-bmff",
    "flac": "flac",
    "ogg": "ogg",
    "opus": "ogg",
}

DEFAULT_ALLOWED_EXTENSIONS = tuple(UPLOAD_EXTENSION_FORMATS)
SUPPORTED_UPLOAD_EXTENSIONS = frozenset(UPLOAD_EXTENSION_FORMATS)
