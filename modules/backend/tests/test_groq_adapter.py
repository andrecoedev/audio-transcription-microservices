import json

import httpx
import pytest

from src.services import groq_intelligence as groq


def _response(content='{"schema_version":"1"}', *, finish="stop", usage=None, refusal=None):
    return {"choices": [{"finish_reason": finish, "message": {"content": content, "refusal": refusal}}], "usage": usage}


def _provider(monkeypatch, response=None, status=200):
    seen = {}
    seen["requests"] = 0

    def handler(request):
        seen["requests"] += 1
        seen["request"] = request
        if response is None:
            body = _response()
        else:
            body = response
        return httpx.Response(status, json=body)

    class Client(httpx.Client):
        def __init__(self, *args, **kwargs):
            seen["client"] = kwargs
            super().__init__(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(groq.httpx, "Client", Client)
    monkeypatch.setattr(groq.settings, "GROQ_MAX_INPUT_CHARACTERS", 20000, raising=False)
    monkeypatch.setattr(groq.settings, "GROQ_MAX_INPUT_TOKENS", 32000, raising=False)
    monkeypatch.setattr(groq.settings, "GROQ_MAX_OUTPUT_TOKENS", 4096, raising=False)
    monkeypatch.setattr(groq.settings, "GROQ_TIMEOUT_SECONDS", 60, raising=False)
    return groq.GroqIntelligenceProvider("secret-key", "openai/gpt-oss-20b"), seen


def test_strict_schema_request_and_limits(monkeypatch):
    provider, seen = _provider(monkeypatch)
    assert provider.generate({"segments": [{"text": "Olá"}]}) == '{"schema_version":"1"}'
    request = seen["request"]
    assert request.url == groq.ENDPOINT
    assert request.headers["authorization"] == "Bearer secret-key"
    payload = json.loads(request.content)
    assert payload["max_completion_tokens"] == 4096
    assert payload["response_format"]["type"] == "json_schema"
    schema = payload["response_format"]["json_schema"]
    assert schema["strict"] is True
    assert schema["schema"]["additionalProperties"] is False
    assert schema["schema"]["required"] == list(schema["schema"]["properties"])
    assert seen["client"]["timeout"] == 60
    assert seen["client"]["follow_redirects"] is False


def test_utf8_transcript_limit_and_token_bound(monkeypatch):
    provider, _ = _provider(monkeypatch)
    monkeypatch.setattr(groq.settings, "GROQ_MAX_INPUT_CHARACTERS", 2)
    with pytest.raises(ValueError, match="configured limit"):
        provider.generate({"segments": [{"text": "abc"}]})
    monkeypatch.setattr(groq.settings, "GROQ_MAX_INPUT_CHARACTERS", 20)
    payload, bound = groq.prepared_request({"segments": [{"text": "á"}]}, "model")
    prompt = payload["messages"][0]["content"]
    schema_size = len(json.dumps(groq.IntelligenceResult.model_json_schema(), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    assert bound == len(prompt.encode("utf-8")) + schema_size + 1024
    monkeypatch.setattr(groq.settings, "GROQ_MAX_INPUT_TOKENS", bound - 1)
    with pytest.raises(ValueError, match="token limit"):
        groq.prepared_request({"segments": [{"text": "á"}]}, "model")


def test_http_error_is_sanitized_and_not_retried(monkeypatch):
    provider, seen = _provider(monkeypatch, status=429, response={"error": {"message": "secret response"}})
    with pytest.raises(RuntimeError, match="HTTP 429") as error:
        provider.generate({"segments": []})
    assert "secret response" not in str(error.value)
    assert seen["request"].headers["authorization"] == "Bearer secret-key"
    assert seen["requests"] == 1


def test_redirect_is_rejected_without_following(monkeypatch):
    provider, seen = _provider(monkeypatch, status=302, response={"location": "https://other.invalid"})
    with pytest.raises(RuntimeError, match="HTTP 302"):
        provider.generate({"segments": []})
    assert seen["requests"] == 1


def test_timeout_is_sanitized(monkeypatch):
    original_client = httpx.Client
    provider, _ = _provider(monkeypatch)

    def timeout(_request):
        raise httpx.ReadTimeout("secret-key and response text")

    monkeypatch.setattr(groq.httpx, "Client", lambda *a, **kw: original_client(
        *a, transport=httpx.MockTransport(timeout), **kw
    ))
    with pytest.raises(RuntimeError, match="Groq request failed") as error:
        provider.generate({"segments": []})
    assert "secret-key" not in str(error.value)


def test_missing_usage_is_allowed_without_token_fields(monkeypatch):
    provider, _ = _provider(monkeypatch, response={"choices": [{"finish_reason": "stop",
        "message": {"content": "ok"}}]})
    events = []
    provider.set_usage_observer(events.append)
    assert provider.generate({"segments": []}) == "ok"
    assert events[0]["status"] == "response"
    assert not {"prompt_tokens", "completion_tokens", "total_tokens", "cached_tokens", "reasoning_tokens"} & events[0].keys()


def test_response_over_one_megabyte_is_rejected(monkeypatch):
    original_client = httpx.Client
    provider, _ = _provider(monkeypatch)
    class LargeClient(original_client):
        def __init__(self, *args, **kwargs):
            transport = httpx.MockTransport(lambda _request: httpx.Response(
                200, content=b"x" * (groq.MAX_RESPONSE_BYTES + 1)
            ))
            super().__init__(*args, transport=transport, **kwargs)
    monkeypatch.setattr(groq.httpx, "Client", LargeClient)
    with pytest.raises(RuntimeError, match="size limit"):
        provider.generate({"segments": []})


@pytest.mark.parametrize("body", [
    _response(finish="length"),
    _response(finish="tool_calls"),
    _response(refusal="cannot comply"),
    {"choices": []},
    {"choices": [{"finish_reason": "stop", "message": {"content": None}}]},
    {"choices": ["malformed"]},
    {"choices": [{"finish_reason": "stop", "message": ["malformed"]}]},
])
def test_rejects_refusal_truncation_and_malformed_response(monkeypatch, body):
    provider, _ = _provider(monkeypatch, response=body)
    with pytest.raises(RuntimeError, match="invalid or incomplete"):
        provider.generate({"segments": []})


def test_usage_observer_validates_numbers_and_failure_is_nonfatal(monkeypatch):
    body = _response(usage={"prompt_tokens": 12, "completion_tokens": 7, "total_tokens": 19,
                            "prompt_tokens_details": {"cached_tokens": 3},
                            "completion_tokens_details": {"reasoning_tokens": 2,
                                                          "unknown_metadata": "sensitive response text"}})
    provider, _ = _provider(monkeypatch, response=body)
    events = []
    provider.set_usage_observer(events.append)
    assert provider.generate({"segments": []}) == '{"schema_version":"1"}'
    assert events[0]["status"] == "response"
    assert events[0]["prompt_tokens"] == 12
    assert events[0]["completion_tokens"] == 7
    assert events[0]["total_tokens"] == 19
    assert events[0]["cached_tokens"] == 3
    assert events[0]["reasoning_tokens"] == 2
    assert "sensitive response text" not in repr(events[0])
    provider.set_usage_observer(lambda _: (_ for _ in ()).throw(RuntimeError("secret-key")))
    assert provider.generate({"segments": []}) == '{"schema_version":"1"}'
