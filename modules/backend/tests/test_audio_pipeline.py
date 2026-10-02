from pathlib import Path

import pytest

from src import engine_registry
from src.services import transcription_processing_service as processing_module
from src.services.transcription_processing_service import (
    TranscriptionProcessingService,
)


class RecordingWhisper:
    def __init__(self, text="texto", error=None):
        self.calls = []
        self.text = text
        self.error = error

    def transcribe_segment(self, path, start=0.0, end=None):
        self.calls.append((path, start, end))
        if self.error:
            raise self.error
        return self.text

    def get_metadata(self):
        return {
            "engine": "faster-whisper",
            "model": "large-v3",
            "device": "cpu",
            "compute_type": "int8",
        }


def _fake_conversion(source, destination):
    Path(destination).write_bytes(b"normalized-wav")
    return destination, 10.0


def test_processing_service_uses_one_normalized_file_and_cleans_it(
    monkeypatch, tmp_path
):
    engine = RecordingWhisper()
    monkeypatch.setattr(engine_registry, "whisper_engine", engine)
    monkeypatch.setattr(processing_module, "_TEMP_DIRECTORY", tmp_path)
    monkeypatch.setattr(processing_module, "convert_to_wav", _fake_conversion)

    result = TranscriptionProcessingService().process_transcription(
        "input.mp3", False, "whisper"
    )

    assert result.temporary_files == 1
    assert result.temporary_bytes == len(b"normalized-wav")
    assert list(tmp_path.iterdir()) == []
    assert engine.calls[0][1:] == (0.0, 10.0)


def test_explicit_local_provider_never_calls_cloud_engine(monkeypatch, tmp_path):
    class ForbiddenCloud:
        def transcribe_segment(self, *_args, **_kwargs):
            raise AssertionError("local provider attempted a cloud call")

    local = RecordingWhisper()
    monkeypatch.setattr(engine_registry, "whisper_engine", local)
    monkeypatch.setattr(engine_registry, "assemblyai_engine", ForbiddenCloud())
    monkeypatch.setattr(processing_module, "_TEMP_DIRECTORY", tmp_path)
    monkeypatch.setattr(processing_module, "convert_to_wav", _fake_conversion)

    result = TranscriptionProcessingService().process_transcription(
        "input.mp3", False, "whisper"
    )
    assert result.engine_metadata["engine"] == "faster-whisper"
    assert len(local.calls) == 1


def test_normalized_file_is_cleaned_when_transcription_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(
        engine_registry,
        "whisper_engine",
        RecordingWhisper(error=RuntimeError("inference failed")),
    )
    monkeypatch.setattr(processing_module, "_TEMP_DIRECTORY", tmp_path)
    monkeypatch.setattr(processing_module, "convert_to_wav", _fake_conversion)

    with pytest.raises(RuntimeError, match="inference failed"):
        TranscriptionProcessingService().process_transcription(
            "input.mp3", False, "whisper"
        )

    assert list(tmp_path.iterdir()) == []


def test_diarization_sorts_clamps_and_preserves_speakers(monkeypatch, tmp_path):
    class Diarization:
        def diarize(self, _path):
            return {
                "segments": [
                    {"start": 8.0, "end": 12.0, "speaker": "SPEAKER_01"},
                    {"start": -1.0, "end": 2.0, "speaker": "SPEAKER_00"},
                    {"start": 7.0, "end": 6.0, "speaker": "SPEAKER_02"},
                ],
                "num_speakers": 3,
            }

    engine = RecordingWhisper()
    monkeypatch.setattr(engine_registry, "whisper_engine", engine)
    monkeypatch.setattr(engine_registry, "diarization_engine", Diarization())
    monkeypatch.setattr(processing_module, "_TEMP_DIRECTORY", tmp_path)
    monkeypatch.setattr(processing_module, "convert_to_wav", _fake_conversion)

    result = TranscriptionProcessingService().process_transcription(
        "input.mp3", True, "whisper"
    )

    assert [(item["start"], item["end"], item["speaker"]) for item in result.segments] == [
        (0.0, 2.0, "SPEAKER_00"),
        (8.0, 10.0, "SPEAKER_01"),
    ]
    assert result.num_speakers == 3
    assert all(0 <= item["start"] < item["end"] <= 10.0 for item in result.segments)


def test_diarization_overlap_preserves_both_tracks_and_transcribes_both(
    monkeypatch, tmp_path
):
    class Diarization:
        def diarize(self, _path):
            return {
                "segments": [
                    {"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"},
                    {"start": 1.0, "end": 3.0, "speaker": "SPEAKER_01"},
                ],
                "num_speakers": 2,
            }

    engine = RecordingWhisper()
    monkeypatch.setattr(engine_registry, "whisper_engine", engine)
    monkeypatch.setattr(engine_registry, "diarization_engine", Diarization())
    monkeypatch.setattr(processing_module, "_TEMP_DIRECTORY", tmp_path)
    monkeypatch.setattr(processing_module, "convert_to_wav", _fake_conversion)

    result = TranscriptionProcessingService().process_transcription(
        "input.mp3", True, "whisper"
    )

    assert engine.calls == [
        (engine.calls[0][0], 0.0, 2.0),
        (engine.calls[0][0], 1.0, 3.0),
    ]
    assert [row["speaker"] for row in result.segments] == [
        "SPEAKER_00",
        "SPEAKER_01",
    ]
