from types import SimpleNamespace
from contextlib import nullcontext
import logging

import pytest

import numpy as np

from src.config import settings
from src.services import diarization_engine as diarization_module
from src.services.diarization_engine import DiarizationEngine


def _engine_without_model():
    return DiarizationEngine.__new__(DiarizationEngine)


class SensitiveSyntheticError(Exception):
    def __str__(self):
        return "private provider response body"


def test_pipeline_load_error_log_does_not_include_exception_text(monkeypatch, caplog):
    monkeypatch.setattr(diarization_module, "version", lambda _name: "4.0")
    monkeypatch.setattr(
        diarization_module, "pipeline_config", lambda *_args: ("repo", {})
    )
    monkeypatch.setattr(diarization_module, "hf_hub_download", lambda **_kwargs: None)
    monkeypatch.setattr(diarization_module.torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr(
        diarization_module.Pipeline,
        "from_pretrained",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(SensitiveSyntheticError()),
    )

    with caplog.at_level(logging.ERROR, logger=diarization_module.__name__):
        with pytest.raises(SensitiveSyntheticError):
            engine = _engine_without_model()
            engine.hf_token = None
            engine._load_pipeline()

    assert "Erro ao carregar pipeline de diarização (SensitiveSyntheticError)" in caplog.text
    assert "private provider response body" not in caplog.text


def test_segment_error_log_does_not_include_exception_text(monkeypatch, caplog):
    engine = _engine_without_model()
    monkeypatch.setattr(
        diarization_module.librosa,
        "load",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(SensitiveSyntheticError()),
    )

    with caplog.at_level(logging.ERROR, logger=diarization_module.__name__):
        assert not engine.is_valid_segment("fixture.wav", 0.0, 1.0, 0.1, -40.0)

    assert "Erro ao verificar segmento 0.00s-1.00s (SensitiveSyntheticError)" in caplog.text
    assert "private provider response body" not in caplog.text


def test_diarization_error_log_does_not_include_exception_text(monkeypatch, caplog):
    class Pipeline:
        def __call__(self, _path, hook=None):
            raise SensitiveSyntheticError()

    engine = _engine_without_model()
    engine.pipeline = Pipeline()
    monkeypatch.setattr(diarization_module, "ProgressHook", nullcontext)
    monkeypatch.setattr(settings, "MIN_SEGMENT_DURATION", 0.0)
    monkeypatch.setattr(settings, "SILENCE_THRESHOLD", -100.0)

    with caplog.at_level(logging.ERROR, logger=diarization_module.__name__):
        with pytest.raises(SensitiveSyntheticError):
            engine.diarize("fixture.wav")

    assert "Erro durante diarização (SensitiveSyntheticError)" in caplog.text
    assert "private provider response body" not in caplog.text


def test_short_segment_is_rejected_before_audio_decode(monkeypatch):
    engine = _engine_without_model()
    monkeypatch.setattr(
        diarization_module.librosa,
        "load",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("short segment must not be decoded")
        ),
    )

    assert not engine.is_valid_segment("fixture.wav", 0.0, 0.49, 0.5, -40.0)


def test_short_valid_segment_at_boundary_is_accepted(monkeypatch):
    engine = _engine_without_model()
    samples = np.full(8000, 0.02, dtype=np.float32)  # about -34 dBFS
    monkeypatch.setattr(
        diarization_module.librosa, "load", lambda *_args, **_kwargs: (samples, 16000)
    )

    assert engine.is_valid_segment("fixture.wav", 0.0, 0.5, 0.5, -40.0)


def test_volume_filter_rejects_audio_below_final_threshold(monkeypatch):
    engine = _engine_without_model()
    samples = np.full(16000, 0.001, dtype=np.float32)  # -60 dBFS
    monkeypatch.setattr(
        diarization_module.librosa, "load", lambda *_args, **_kwargs: (samples, 16000)
    )

    assert not engine.is_valid_segment("fixture.wav", 0.0, 1.0, 0.5, -40.0)


def test_diarize_uses_configured_filter_and_preserves_speaker_labels(monkeypatch):
    class Annotation:
        def itertracks(self, yield_label=False):
            assert yield_label
            yield SimpleNamespace(start=0.0, end=1.0), None, "SPEAKER_00"
            yield SimpleNamespace(start=1.0, end=2.0), None, "SPEAKER_01"

    class Pipeline:
        def __call__(self, _path, hook=None):
            assert hook is not None
            return Annotation()

    engine = _engine_without_model()
    engine.pipeline = Pipeline()
    observed = []
    monkeypatch.setattr(settings, "MIN_SEGMENT_DURATION", 0.5)
    monkeypatch.setattr(settings, "SILENCE_THRESHOLD", -40.0)
    monkeypatch.setattr(
        engine,
        "is_valid_segment",
        lambda path, start, end, minimum, threshold: observed.append(
            (path, start, end, minimum, threshold)
        )
        or True,
    )

    result = engine.diarize("fixture.wav")

    assert result["num_speakers"] == 2
    assert [segment["speaker"] for segment in result["segments"]] == [
        "SPEAKER_00",
        "SPEAKER_01",
    ]
    assert {(row[3], row[4]) for row in observed} == {(0.5, -40.0)}


def test_default_disabled_post_filter_preserves_short_low_volume_and_overlap(monkeypatch):
    class Annotation:
        def itertracks(self, yield_label=False):
            assert yield_label
            yield SimpleNamespace(start=0.0, end=0.2), None, "SPEAKER_00"
            yield SimpleNamespace(start=0.1, end=0.4), None, "SPEAKER_01"

    class Pipeline:
        def __call__(self, _path, hook=None):
            assert hook is not None
            return Annotation()

    engine = _engine_without_model()
    engine.pipeline = Pipeline()
    monkeypatch.setattr(settings, "MIN_SEGMENT_DURATION", 0.0)
    monkeypatch.setattr(settings, "SILENCE_THRESHOLD", -100.0)
    monkeypatch.setattr(
        engine,
        "is_valid_segment",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("disabled post-filter must not decode segments")
        ),
    )

    result = engine.diarize("fixture.wav")

    assert result["num_speakers"] == 2
    assert [row["speaker"] for row in result["segments"]] == [
        "SPEAKER_00",
        "SPEAKER_01",
    ]
    assert [(row["start"], row["end"]) for row in result["segments"]] == [
        (0.0, 0.2),
        (0.1, 0.4),
    ]
