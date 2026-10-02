"""Central log redaction for credentials and common personal identifiers."""

import logging
import re
from typing import Any


_PATTERNS = (
    (re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]+=*"), r"\1[REDACTED]"),
    (
        re.compile(r"(?i)((?:api[_-]?key|token|secret|password)\s*[:=]\s*)[^\s,;]+"),
        r"\1[REDACTED]",
    ),
    (
        re.compile(r"(?i)(postgres(?:ql)?(?:\+\w+)?://[^:\s/@]+:)[^@\s]+(@)"),
        r"\1[REDACTED]\2",
    ),
    (re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"), "[REDACTED_EMAIL]"),
)


def redact_sensitive_text(value: Any) -> str:
    redacted = str(value)
    for pattern, replacement in _PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_sensitive_text(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    key: redact_sensitive_text(value) if isinstance(value, str) else value
                    for key, value in record.args.items()
                }
            else:
                record.args = tuple(
                    redact_sensitive_text(value) if isinstance(value, str) else value
                    for value in record.args
                )
        return True


class RedactingFormatter(logging.Formatter):
    def formatException(self, exc_info):
        return redact_sensitive_text(super().formatException(exc_info))


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.addFilter(RedactingFilter())
    handler.setFormatter(
        RedactingFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    handler._usagi_redacting = True
    root = logging.getLogger()
    if not any(getattr(existing, "_usagi_redacting", False) for existing in root.handlers):
        root.addHandler(handler)
    root.setLevel(logging.INFO)
