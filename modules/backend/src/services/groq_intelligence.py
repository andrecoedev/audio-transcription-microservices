"""Groq adapter for the provider-neutral meeting intelligence contract."""

import json
import logging
import math
import time
from typing import Callable

import httpx

from ..config import settings
from ..intelligence_schema import IntelligenceResult
from .intelligence_provider import build_prompt

logger = logging.getLogger(__name__)

ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
MAX_RESPONSE_BYTES = 1_000_000
CONTEXT_WINDOW_TOKENS = 131_072


def _transcript_characters(context: dict) -> int:
    segments = context.get("segments", [])
    if not isinstance(segments, list):
        raise ValueError("Invalid intelligence context")
    total = 0
    for segment in segments:
        if not isinstance(segment, dict) or not isinstance(segment.get("text", ""), str):
            raise ValueError("Invalid intelligence context")
        total += len(segment.get("text", ""))
    return total


def prepared_request(context: dict, model: str) -> tuple[dict, int]:
    """Build the strict-schema request and a conservative UTF-8 token bound."""
    if not isinstance(context, dict):
        raise ValueError("Invalid intelligence context")
    if _transcript_characters(context) > settings.GROQ_MAX_INPUT_CHARACTERS:
        raise ValueError("Intelligence input exceeds configured limit")

    schema = IntelligenceResult.model_json_schema()
    # OpenAI-compatible strict structured outputs require all fields to be required
    # and every object to disallow additional properties.
    def strictify(node):
        if isinstance(node, dict):
            if node.get("type") == "object" or "properties" in node:
                node["additionalProperties"] = False
                properties = node.get("properties", {})
                node["required"] = list(properties)
            for value in node.values():
                strictify(value)
        elif isinstance(node, list):
            for value in node:
                strictify(value)

    strictify(schema)
    prompt = build_prompt(context)
    prompt_bytes = len(prompt.encode("utf-8"))
    schema_bytes = len(json.dumps(schema, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    bound_tokens = prompt_bytes + schema_bytes + 1024
    output_tokens = settings.GROQ_MAX_OUTPUT_TOKENS
    if bound_tokens > settings.GROQ_MAX_INPUT_TOKENS or bound_tokens + output_tokens > CONTEXT_WINDOW_TOKENS:
        raise ValueError("Intelligence input exceeds configured token limit")

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_completion_tokens": output_tokens,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "intelligence_result", "strict": True, "schema": schema},
        },
    }
    return payload, bound_tokens


class GroqIntelligenceProvider:
    def __init__(self, api_key: str, model: str):
        if not api_key or not isinstance(api_key, str):
            raise ValueError("Groq API key is required")
        if not model or not isinstance(model, str):
            raise ValueError("Groq model is required")
        self.api_key = api_key
        self.model = model
        self._usage_observer: Callable[[dict], None] | None = None

    def set_usage_observer(self, callback) -> None:
        self._usage_observer = callback

    def _observe(self, status: str, started: float, usage=None) -> None:
        if self._usage_observer is None:
            return
        elapsed = time.monotonic() - started
        event = {"status": status, "model": self.model}
        if math.isfinite(elapsed) and elapsed >= 0:
            event["elapsed_seconds"] = elapsed
        if isinstance(usage, dict):
            prompt_details = usage.get("prompt_tokens_details")
            completion_details = usage.get("completion_tokens_details")
            cached = prompt_details.get("cached_tokens") if isinstance(prompt_details, dict) else None
            reasoning = completion_details.get("reasoning_tokens") if isinstance(completion_details, dict) else None
            for name, value in (("prompt_tokens", usage.get("prompt_tokens")),
                                ("completion_tokens", usage.get("completion_tokens")),
                                ("total_tokens", usage.get("total_tokens")),
                                ("cached_tokens", cached), ("reasoning_tokens", reasoning)):
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                    event[name] = value
        try:
            self._usage_observer(event)
        except Exception as exc:
            logger.warning("Groq usage observer failed (%s)", type(exc).__name__)

    def generate(self, context: dict) -> str:
        payload, _ = prepared_request(context, self.model)
        started = time.monotonic()
        try:
            with httpx.Client(timeout=settings.GROQ_TIMEOUT_SECONDS, follow_redirects=False) as client:
                with client.stream(
                    "POST", ENDPOINT,
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=payload,
                ) as response:
                    if response.status_code < 200 or response.status_code >= 300:
                        self._observe("error", started)
                        raise RuntimeError(f"Groq request failed (HTTP {response.status_code})")
                    chunks = []
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > MAX_RESPONSE_BYTES:
                            self._observe("error", started)
                            raise RuntimeError("Groq response exceeded size limit")
                        chunks.append(chunk)
                    data = json.loads(b"".join(chunks))
        except RuntimeError:
            raise
        except (httpx.HTTPError, ValueError, TypeError):
            self._observe("error", started)
            raise RuntimeError("Groq request failed") from None

        usage = data.get("usage") if isinstance(data, dict) else None
        self._observe("response", started, usage)
        try:
            choice = data["choices"][0]
            if not isinstance(choice, dict):
                raise ValueError
            if choice.get("finish_reason") != "stop":
                raise ValueError
            message = choice["message"]
            if not isinstance(message, dict):
                raise ValueError
            if message.get("refusal"):
                raise ValueError
            content = message.get("content")
            if not isinstance(content, str) or not content:
                raise ValueError
            return content
        except (AttributeError, KeyError, IndexError, TypeError, ValueError):
            raise RuntimeError("Groq returned an invalid or incomplete response") from None
