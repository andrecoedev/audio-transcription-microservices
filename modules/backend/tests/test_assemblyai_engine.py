from types import SimpleNamespace

import pytest

from src.services import assemblyai_engine as module
from src.services.assemblyai_engine import (
    AssemblyAIEngine,
    AssemblyAIProcessingError,
)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            error = RuntimeError("provider body contains a secret transcript")
            error.response = SimpleNamespace(status_code=self.status_code)
            raise error

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, payloads):
        self.payloads = iter(payloads)
        self.calls = []
        self.http_client = self

    def get(self, path, *, timeout):
        self.calls.append((path, timeout))
        payload = next(self.payloads)
        if isinstance(payload, Exception):
            raise payload
        return payload


class FakeTranscriber:
    def __init__(self, transcript_id="abc-123", error=None):
        self.transcript_id = transcript_id
        self.error = error
        self.calls = []

    def submit(self, path, *, config):
        self.calls.append((path, config))
        if self.error:
            raise self.error
        return SimpleNamespace(id=self.transcript_id)


def make_engine(monkeypatch, payloads, *, transcriber=None, **kwargs):
    client = FakeClient(payloads)
    fake_transcriber = transcriber or FakeTranscriber()
    monkeypatch.setattr(module.aai, "Client", lambda **_kwargs: client)
    monkeypatch.setattr(module.aai, "Transcriber", lambda **_kwargs: fake_transcriber)
    return AssemblyAIEngine("test-key", **kwargs), client, fake_transcriber


def test_native_utterances_map_milliseconds_to_seconds_and_keep_overlaps(monkeypatch):
    engine, client, transcriber = make_engine(
        monkeypatch,
        [
            FakeResponse(
                {
                    "status": "completed",
                    "text": "Olá. Tudo bem?",
                    "utterances": [
                        {"start": 1000, "end": 2400, "speaker": "A", "text": "Tudo bem?"},
                        {"start": 200, "end": 1200, "speaker": "B", "text": "Olá."},
                    ],
                }
            )
        ],
    )

    result = engine.transcribe_file("normalized.wav", 3.0, use_diarization=True)

    assert result == {
        "segments": [
            {"start": 0.2, "end": 1.2, "speaker": "SPEAKER_00", "text": "Olá."},
            {"start": 1.0, "end": 2.4, "speaker": "SPEAKER_01", "text": "Tudo bem?"},
        ],
        "num_speakers": 2,
    }
    assert len(transcriber.calls) == 1
    assert transcriber.calls[0][0] == "normalized.wav"
    assert client.calls[0][0] == "/v2/transcript/abc-123"


def test_submit_config_pins_universal_2_and_never_changes_global_settings(monkeypatch):
    prior_key = module.aai.settings.api_key
    engine, _client, transcriber = make_engine(
        monkeypatch,
        [FakeResponse({"status": "completed", "text": "", "utterances": []})],
    )

    assert engine.transcribe_file("normalized.wav", 2.0, True) == {
        "segments": [],
        "num_speakers": 0,
    }

    config = transcriber.calls[0][1]
    assert config.speaker_labels is True
    # SDK 0.40.2 exposes the wire config internally; guard its pinned contract.
    assert config._raw_transcription_config.model_dump(exclude_none=True)["speech_models"] == ["universal-2"]
    assert config.language_code == "pt"
    assert module.aai.settings.api_key == prior_key
    assert engine.get_metadata() == {
        "engine": "assemblyai",
        "model": "universal-2",
        "device": "cloud",
        "language": "pt",
    }


def test_non_diarized_flow_uses_word_timestamps_for_single_segment(monkeypatch):
    engine, _client, transcriber = make_engine(
        monkeypatch,
        [
            FakeResponse(
                {
                    "status": "completed",
                    "text": "Bom dia",
                    "words": [
                        {"start": 120, "end": 700},
                        {"start": 700, "end": 1300},
                    ],
                }
            )
        ],
    )

    assert engine.transcribe_file("normalized.wav", 2.0, False) == {
        "segments": [
            {"start": 0.12, "end": 1.3, "speaker": "SPEAKER_00", "text": "Bom dia"}
        ],
        "num_speakers": 1,
    }
    # The pinned SDK omits the false flag rather than serializing false.
    assert transcriber.calls[0][1].speaker_labels in (None, False)


def test_empty_audio_response_is_successful_without_speakers(monkeypatch):
    engine, _, _ = make_engine(
        monkeypatch,
        [FakeResponse({"status": "completed", "text": "", "utterances": []})],
    )
    assert engine.transcribe_file("silence.wav", 1.0, True) == {
        "segments": [],
        "num_speakers": 0,
    }


def test_small_codec_timestamp_overshoot_is_clamped_to_duration(monkeypatch):
    engine, _, _ = make_engine(
        monkeypatch,
        [
            FakeResponse(
                {
                    "status": "completed",
                    "text": "fim",
                    "utterances": [
                        {"start": 950, "end": 2050, "speaker": "A", "text": "fim"}
                    ],
                }
            )
        ],
    )
    assert engine.transcribe_file("normalized.wav", 2.0, True)["segments"] == [
        {"start": 0.95, "end": 2.0, "speaker": "SPEAKER_00", "text": "fim"}
    ]


@pytest.mark.parametrize(
    "utterance",
    [
        {"start": float("nan"), "end": 200, "speaker": "A", "text": "x"},
        {"start": 200, "end": float("inf"), "speaker": "A", "text": "x"},
        {"start": -1, "end": 200, "speaker": "A", "text": "x"},
        {"start": 200, "end": 1200, "speaker": "A", "text": "x"},
        {"start": 200, "end": 300, "speaker": None, "text": "x"},
    ],
)
def test_malformed_or_out_of_range_utterance_fails_closed(monkeypatch, utterance):
    engine, _, _ = make_engine(
        monkeypatch,
        [FakeResponse({"status": "completed", "text": "x", "utterances": [utterance]})],
    )
    with pytest.raises(AssemblyAIProcessingError) as error:
        engine.transcribe_file("normalized.wav", 1.0, True)
    assert error.value.code == "invalid_response"


@pytest.mark.parametrize(
    ("status_code", "code"), [(401, "credential"), (403, "credential"), (429, "quota")]
)
def test_http_failures_are_categorized_without_provider_payload(monkeypatch, status_code, code):
    engine, _, _ = make_engine(monkeypatch, [FakeResponse({}, status_code=status_code)])
    with pytest.raises(AssemblyAIProcessingError) as error:
        engine.transcribe_file("normalized.wav", 1.0, True)
    assert error.value.code == code
    assert "secret" not in str(error.value)
    assert "transcript" not in str(error.value)


def test_provider_error_state_is_sanitized(monkeypatch):
    engine, _, _ = make_engine(
        monkeypatch,
        [
            FakeResponse(
                {
                    "status": "error",
                    "error": "quota exhausted; api key and transcript text must stay private",
                }
            )
        ],
    )
    with pytest.raises(AssemblyAIProcessingError) as error:
        engine.transcribe_file("normalized.wav", 1.0, True)
    assert error.value.code == "quota"
    assert "private" not in str(error.value)


def test_submit_failure_is_sanitized_and_does_not_retry(monkeypatch):
    failure = RuntimeError("provider returned private transcript and API key")
    transcriber = FakeTranscriber(error=failure)
    engine, client, _ = make_engine(monkeypatch, [], transcriber=transcriber)

    with pytest.raises(AssemblyAIProcessingError) as error:
        engine.transcribe_file("normalized.wav", 1.0, True)

    assert error.value.code == "unavailable"
    assert "private" not in str(error.value)
    assert "API key" not in str(error.value)
    assert len(transcriber.calls) == 1
    assert client.calls == []


def test_bad_transcript_id_is_rejected_before_polling(monkeypatch):
    transcriber = FakeTranscriber(transcript_id="../secret")
    engine, client, _ = make_engine(monkeypatch, [], transcriber=transcriber)

    with pytest.raises(AssemblyAIProcessingError) as error:
        engine.transcribe_file("normalized.wav", 1.0, True)

    assert error.value.code == "invalid_response"
    assert client.calls == []


def test_poll_timeout_has_a_bounded_http_timeout(monkeypatch):
    engine, client, _ = make_engine(
        monkeypatch,
        [FakeResponse({"status": "queued"}), FakeResponse({"status": "queued"})],
        http_timeout=5.0,
        timeout_seconds=1.0,
        poll_interval=0.5,
    )
    ticks = iter([0.0, 0.0, 0.1, 0.6, 1.1])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)

    with pytest.raises(AssemblyAIProcessingError) as error:
        engine.transcribe_file("normalized.wav", 1.0, True)

    assert error.value.code == "timeout"
    assert all(timeout <= 1.0 for _, timeout in client.calls)


def test_missing_credential_is_rejected_before_client_creation(monkeypatch):
    created = []
    monkeypatch.setattr(module.aai, "Client", lambda **_kwargs: created.append(True))

    with pytest.raises(AssemblyAIProcessingError) as error:
        AssemblyAIEngine("")

    assert error.value.code == "credential"
    assert created == []
