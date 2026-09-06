from types import SimpleNamespace

import numpy as np
import pytest

from src.config import settings
from src.services.faster_whisper_engine import (
    FasterWhisperEngine,
    FasterWhisperEngineError,
)


class FakeModel:
    def __init__(self, segments=None):
        self.calls = []
        self.segments = segments or [
            SimpleNamespace(start=0.0, end=1.0, text=" olá mundo ")
        ]

    def transcribe(self, audio, **kwargs):
        self.calls.append((audio, kwargs))
        return iter(self.segments), SimpleNamespace(language="pt")


def _engine(monkeypatch, *, cuda_count=0, device="auto", compute_type="auto", model=None):
    fake_model = model or FakeModel()
    model_arguments = {}

    def model_factory(model_name, **kwargs):
        model_arguments.update({"model_name": model_name, **kwargs})
        return fake_model

    monkeypatch.setattr(settings, "WHISPER_MAX_DECODE_CHUNK_SECONDS", 300.0)
    engine = FasterWhisperEngine(
        model_name="large-v3",
        device=device,
        compute_type=compute_type,
        language="pt",
        model_factory=model_factory,
        cuda_device_count=lambda: cuda_count,
        supported_compute_types=lambda selected_device: (
            {"float16", "int8_float16"}
            if selected_device == "cuda"
            else {"int8", "float32"}
        ),
        segment_decoder=lambda *_args, **_kwargs: np.ones(16_000, dtype=np.float32),
        duration_probe=lambda _path: 1.0,
    )
    return engine, fake_model, model_arguments


def test_auto_selects_cpu_int8_and_initializes_large_v3(monkeypatch):
    engine, _, arguments = _engine(monkeypatch)

    assert engine.device == "cpu"
    assert engine.compute_type == "int8"
    assert arguments["model_name"] == "large-v3"
    assert arguments["device"] == "cpu"
    assert arguments["compute_type"] == "int8"


def test_auto_selects_cuda_float16(monkeypatch):
    engine, _, arguments = _engine(monkeypatch, cuda_count=1)

    assert engine.device == "cuda"
    assert engine.compute_type == "float16"
    assert arguments["device"] == "cuda"


def test_explicit_cuda_fails_when_unavailable(monkeypatch):
    with pytest.raises(FasterWhisperEngineError, match="no CUDA device"):
        _engine(monkeypatch, device="cuda", cuda_count=0)


def test_unsupported_compute_type_fails_predictably(monkeypatch):
    with pytest.raises(FasterWhisperEngineError, match="not supported"):
        _engine(monkeypatch, compute_type="float16", cuda_count=0)


def test_transcription_preserves_pt_and_text_contract(monkeypatch):
    engine, model, _ = _engine(monkeypatch)

    text = engine.transcribe_segment("audio.wav", start=0.0, end=1.0)

    assert text == "olá mundo"
    assert model.calls[0][1]["language"] == "pt"
    assert model.calls[0][1]["beam_size"] == 1
    assert engine.get_metadata() == {
        "engine": "faster-whisper",
        "model": "large-v3",
        "device": "cpu",
        "compute_type": "int8",
        "language": "pt",
    }


def test_long_audio_is_decoded_in_bounded_memory_windows(monkeypatch):
    decoded_windows = []
    fake_model = FakeModel()
    monkeypatch.setattr(settings, "WHISPER_MAX_DECODE_CHUNK_SECONDS", 2.0)
    engine = FasterWhisperEngine(
        model_factory=lambda *_args, **_kwargs: fake_model,
        cuda_device_count=lambda: 0,
        supported_compute_types=lambda _device: {"int8"},
        segment_decoder=lambda _path, **window: (
            decoded_windows.append(window) or np.ones(10, dtype=np.float32)
        ),
    )

    assert engine.transcribe_segment("large.wav", start=0.0, end=5.0) == (
        "olá mundo olá mundo olá mundo"
    )
    assert [window["duration"] for window in decoded_windows] == [2.0, 2.0, 1.0]
    assert len(fake_model.calls) == 3


def test_invalid_faster_whisper_timestamps_are_rejected(monkeypatch):
    model = FakeModel(
        segments=[SimpleNamespace(start=2.0, end=1.0, text="inválido")]
    )
    engine, _, _ = _engine(monkeypatch, model=model)

    with pytest.raises(FasterWhisperEngineError, match="invalid segment timestamps"):
        engine.transcribe_segment("audio.wav", end=3.0)


def test_model_initialization_error_is_wrapped(monkeypatch):
    def fail(*_args, **_kwargs):
        raise RuntimeError("private model detail")

    with pytest.raises(FasterWhisperEngineError, match="Unable to initialize"):
        FasterWhisperEngine(
            model_factory=fail,
            cuda_device_count=lambda: 0,
            supported_compute_types=lambda _device: {"int8"},
        )


def test_inference_error_is_wrapped(monkeypatch):
    class FailingModel(FakeModel):
        def transcribe(self, audio, **kwargs):
            raise RuntimeError("runtime library unavailable")

    engine, _, _ = _engine(monkeypatch, model=FailingModel())

    with pytest.raises(FasterWhisperEngineError, match="inference failed"):
        engine.transcribe_segment("audio.wav", end=1.0)


def test_auto_language_enables_detection(monkeypatch):
    engine, model, _ = _engine(monkeypatch)
    engine.language = "auto"

    engine.transcribe_segment("audio.wav", end=1.0)

    assert model.calls[0][1]["language"] is None
