from types import SimpleNamespace

import pytest

from src.services import assemblyai_engine as aai_module
from src.services import meeting_minutes as gemini_module
from src.services.assemblyai_engine import AssemblyAIEngine, AssemblyAIProcessingError
from src.services.intelligence_provider import GeminiIntelligenceProvider
from src.services.meeting_minutes import MeetingMinutesGenerator


class _Response:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class _HttpClient:
    def __init__(self, payload, events=None):
        self.payload = payload
        self.http_client = self
        self.events = events
        self.calls = 0

    def get(self, _path, *, timeout):
        self.calls += 1
        if self.events is not None:
            self.events.append("poll")
        if isinstance(self.payload, Exception):
            raise self.payload
        return _Response(self.payload)


class _Transcriber:
    def __init__(self, events):
        self.events = events

    def submit(self, _path, *, config):
        self.events.append("submit")
        return SimpleNamespace(id="transcript-1")


def _assembly_engine(monkeypatch, payload, events):
    client = _HttpClient(payload, events)
    transcriber = _Transcriber(events)
    monkeypatch.setattr(aai_module.aai, "Client", lambda **_kwargs: client)
    monkeypatch.setattr(aai_module.aai, "Transcriber", lambda **_kwargs: transcriber)
    return AssemblyAIEngine("test-key", poll_interval=0.001), client


def test_assemblyai_observes_submission_and_provider_usage_before_mapping(monkeypatch):
    events = []
    engine, _client = _assembly_engine(monkeypatch, {
        "id": "transcript-1", "status": "completed", "audio_duration": 8.5,
        "text": "hello", "words": [{"start": 0, "end": 100}],
    }, events)

    def observe(event):
        events.append(event)

    engine.set_usage_observer(observe)
    engine._word_result = lambda *_args: (_ for _ in ()).throw(RuntimeError("mapped"))
    with pytest.raises(RuntimeError, match="mapped"):
        engine.transcribe_file("audio.wav", 1, False)

    assert events[0] == {
        "phase": "submitted", "status": "unknown", "model": "universal-2",
        "use_diarization": False,
    }
    assert events[1] == "submit"
    assert events[2] == "poll"
    assert events[3] == {
        "phase": "polled", "status": "completed", "model": "universal-2",
        "use_diarization": False, "provider_id": "transcript-1",
        "audio_duration_seconds": 8.5,
    }


@pytest.mark.parametrize("duration", [None, -1, float("nan"), float("inf"), True, "8"])
def test_assemblyai_omits_invalid_audio_duration_and_observer_errors_are_nonfatal(monkeypatch, duration):
    events = []
    engine, _client = _assembly_engine(monkeypatch, {
        "status": "completed", "audio_duration": duration,
        "text": "hello", "words": [{"start": 0, "end": 100}],
    }, events)
    engine.set_usage_observer(events.append)
    assert engine.transcribe_file("audio.wav", 1, False)["segments"][0]["text"] == "hello"
    assert "audio_duration_seconds" not in events[1]


def test_assemblyai_observer_failure_does_not_break_delivery(monkeypatch):
    engine, _client = _assembly_engine(monkeypatch, {
        "status": "completed", "text": "hello", "words": [{"start": 0, "end": 100}],
    }, [])
    engine.set_usage_observer(lambda _event: (_ for _ in ()).throw(RuntimeError("secret")))
    assert engine.transcribe_file("audio.wav", 1, False)["segments"][0]["text"] == "hello"


def test_assemblyai_poll_failure_emits_unknown_without_provider_error(monkeypatch):
    events = []
    engine, _client = _assembly_engine(monkeypatch, RuntimeError("private provider response"), events)
    engine.set_usage_observer(events.append)
    with pytest.raises(AssemblyAIProcessingError):
        engine.transcribe_file("audio.wav", 1, False)
    assert events[-1] == {
        "phase": "polled", "status": "unknown", "model": "universal-2",
        "use_diarization": False, "provider_id": "transcript-1",
    }


def test_mandatory_execution_observer_records_acceptance_before_poll(monkeypatch):
    events = []
    engine, _client = _assembly_engine(monkeypatch, {
        "status": "completed", "text": "hello", "words": [{"start": 0, "end": 100}],
    }, events)
    engine.set_execution_observer(events.append)

    engine.transcribe_file("audio.wav", 1, False)

    assert events[0] == "submit"
    assert events[1] == {
        "phase": "accepted", "status": "queued", "model": "universal-2",
        "use_diarization": False, "provider_id": "transcript-1",
    }
    assert events[2] == "poll"
    assert events[3]["phase"] == "polled"
    assert events[3]["status"] == "completed"
    assert events[3]["provider_id"] == "transcript-1"


def test_execution_observer_preserves_accepted_id_when_poll_times_out(monkeypatch):
    events = []
    engine, _client = _assembly_engine(monkeypatch, {"status": "queued"}, events)
    engine.set_execution_observer(events.append)
    engine.timeout_seconds = 0.5
    ticks = iter([1.0, 2.0])
    monkeypatch.setattr(aai_module.time, "monotonic", lambda: next(ticks))

    with pytest.raises(AssemblyAIProcessingError) as error:
        engine.transcribe_file("audio.wav", 1, False)

    assert error.value.code == "timeout"
    assert events[1]["phase"] == "accepted"
    assert events[1]["provider_id"] == "transcript-1"
    assert events[-1] == {
        "phase": "polled", "status": "unknown", "model": "universal-2",
        "use_diarization": False, "provider_id": "transcript-1",
    }
    assert "private" not in str(events)


def test_execution_observer_persistence_failure_aborts_without_poll_or_resubmit(monkeypatch):
    events = []
    engine, client = _assembly_engine(monkeypatch, {
        "status": "completed", "text": "hello", "words": [{"start": 0, "end": 100}],
    }, events)

    def fail(_event):
        raise RuntimeError("database password must not leak")

    engine.set_execution_observer(fail)
    with pytest.raises(AssemblyAIProcessingError) as error:
        engine.transcribe_file("audio.wav", 1, False)

    assert error.value.code == "observer"
    assert "password" not in str(error.value)
    assert client.calls == 0
    assert events.count("submit") == 1


class _GeminiModel:
    def __init__(self, response=None, failure=None):
        self.response = response
        self.failure = failure

    def generate_content(self, *_args, **_kwargs):
        if self.failure:
            raise self.failure
        return self.response


class _TextResponse:
    usage_metadata = SimpleNamespace(
        prompt_token_count=10, candidates_token_count=4, total_token_count=20,
        thoughts_token_count=6, cached_content_token_count=0,
        tool_use_prompt_token_count=None,
    )

    def __init__(self, text, events):
        self._text = text
        self.events = events

    @property
    def text(self):
        self.events.append("text")
        return self._text


def _generator(model, callback=None):
    generator = MeetingMinutesGenerator.__new__(MeetingMinutesGenerator)
    generator.model = model
    generator._usage_observer = callback
    return generator


def test_gemini_observes_actual_counts_before_empty_response_validation(monkeypatch):
    events = []
    response = _TextResponse("", events)
    generator = _generator(_GeminiModel(response=response), events.append)
    monkeypatch.setattr(gemini_module.settings, "GEMINI_MODEL", "gemini-test")

    with pytest.raises(ValueError, match="Empty Gemini response"):
        generator.generate_intelligence("prompt")

    assert events[0]["model"] == "gemini-test"
    assert events[0]["status"] == "response"
    assert events[0]["prompt_tokens"] == 10
    assert events[0]["candidates_tokens"] == 4
    assert events[0]["total_tokens"] == 20
    assert events[0]["thoughts_tokens"] == 6
    assert events[0]["cached_tokens"] == 0
    assert "tool_use_prompt_tokens" not in events[0]
    assert events[1] == "text"


def test_gemini_does_not_invent_invalid_counts_and_observer_errors_are_nonfatal():
    response = SimpleNamespace(text="answer", usage_metadata=SimpleNamespace(
        prompt_token_count=True, candidates_token_count=-2, total_token_count=1.5,
        thoughts_token_count=None, cached_content_token_count=0,
    ))
    generator = _generator(_GeminiModel(response=response), lambda _event: 1 / 0)
    assert generator.generate_intelligence("prompt") == "answer"


def test_gemini_provider_exception_emits_unknown_without_exception_details():
    events = []
    generator = _generator(_GeminiModel(failure=RuntimeError("private response")), events.append)
    with pytest.raises(RuntimeError, match="private response"):
        generator.generate_intelligence("prompt")
    assert events[0]["status"] == "unknown"
    assert events[0]["model"] == gemini_module.settings.GEMINI_MODEL
    assert "prompt_tokens" not in events[0]
    assert "private response" not in str(events[0])


def test_legacy_minutes_calls_observer_and_intelligence_provider_forwards_it(monkeypatch):
    observed = []
    response = SimpleNamespace(text="## RESUMO EXECUTIVO\nResumo", usage_metadata=SimpleNamespace(prompt_token_count=2))
    generator = _generator(_GeminiModel(response=response), observed.append)
    result = generator.generate_minutes("transcript")
    assert result["full_text"] == "## RESUMO EXECUTIVO\nResumo"
    assert observed[0]["prompt_tokens"] == 2

    class FakeGenerator:
        def __init__(self):
            self.callback = None

        def set_usage_observer(self, callback):
            self.callback = callback

        def generate_intelligence(self, _prompt):
            return "{}"

    fake = FakeGenerator()
    provider = GeminiIntelligenceProvider(fake)
    callback = lambda _event: None
    provider.set_usage_observer(callback)
    assert fake.callback is callback


def test_gemini_provider_observer_is_optional_for_fake_generators():
    provider = GeminiIntelligenceProvider(SimpleNamespace(generate_intelligence=lambda _prompt: "{}"))
    provider.set_usage_observer(lambda _event: None)
