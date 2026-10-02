from types import SimpleNamespace

from src.services.diarization_compat import pipeline_config, speaker_turns


class Annotation:
    def itertracks(self, *, yield_label):
        assert yield_label is True
        yield SimpleNamespace(start=1.0, end=2.0), "track-1", "SPEAKER_00"
        yield SimpleNamespace(start=2.0, end=3.0), "track-2", "SPEAKER_01"


def test_pyannote_4_uses_community_1_token_keyword():
    assert pipeline_config("4.0.7", "test-token") == (
        "pyannote/speaker-diarization-community-1",
        {"token": "test-token"},
    )


def test_pyannote_3_compatibility_is_preserved():
    assert pipeline_config("3.3.2", "test-token") == (
        "pyannote/speaker-diarization-3.1",
        {"use_auth_token": "test-token"},
    )


def test_pyannote_4_pipeline_output_returns_annotation_speakers():
    output = SimpleNamespace(speaker_diarization=Annotation())
    assert [(turn.start, turn.end, speaker) for turn, speaker in speaker_turns(output)] == [
        (1.0, 2.0, "SPEAKER_00"),
        (2.0, 3.0, "SPEAKER_01"),
    ]


def test_pyannote_3_annotation_remains_supported():
    assert len(list(speaker_turns(Annotation()))) == 2


def test_pyannote_4_adapter_preserves_overlapping_tracks_and_speakers():
    class OverlappingAnnotation:
        def itertracks(self, *, yield_label):
            assert yield_label is True
            yield SimpleNamespace(start=1.0, end=2.0), "a", "SPEAKER_00"
            yield SimpleNamespace(start=1.5, end=2.5), "b", "SPEAKER_01"
            yield SimpleNamespace(start=2.0, end=3.0), "c", "SPEAKER_00"

    output = SimpleNamespace(speaker_diarization=OverlappingAnnotation())
    assert [
        (turn.start, turn.end, speaker) for turn, speaker in speaker_turns(output)
    ] == [
        (1.0, 2.0, "SPEAKER_00"),
        (1.5, 2.5, "SPEAKER_01"),
        (2.0, 3.0, "SPEAKER_00"),
    ]
