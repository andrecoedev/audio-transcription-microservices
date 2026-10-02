"""The operational smoke respects transcript validation before provider health."""

import sys

import pytest

from scripts import smoke_http_dev


@pytest.mark.parametrize("text,expected_status", [("", 422), ("Discussão de teste", 503)])
def test_meeting_smoke_unconfigured_provider(monkeypatch, capsys, text, expected_status):
    segments = [{"text": text, "start": 0, "end": 1, "speaker": "SPEAKER_00"}]

    class Response:
        def __init__(self, status, data=None):
            self.status_code = status
            self.data = data

        def json(self):
            return self.data

        def raise_for_status(self):
            assert self.status_code < 400

    class Session:
        headers = {}
        deleted = False

        def post(self, url, **kwargs):
            if url.endswith("/auth/login"):
                return Response(200, {"access_token": "synthetic-token"})
            if url.endswith("/transcriptions/jobs"):
                return Response(202, {"transcription_id": 7})
            assert url.endswith("/meetings/7/intelligence")
            return Response(expected_status)

        def get(self, url, **kwargs):
            if url.endswith("/auth/me"):
                return Response(200)
            if url.endswith("/transcriptions/jobs/7/status"):
                return Response(200, {"job_status": "completed"})
            if url.endswith("/transcriptions/7"):
                return Response(404 if self.deleted else 200,
                                {"status": "completed", "segments": segments, "num_speakers": 1})
            if url.endswith("/meetings/7/intelligence/status"):
                return Response(200, {"configured": False})
            if url.endswith("/meetings/7/transcript"):
                return Response(200, {"segments": segments})
            assert url.endswith("/meetings/7")
            return Response(200, {"transcription_id": 7})

        def delete(self, url, **kwargs):
            assert url.endswith("/meetings/7")
            self.deleted = True
            return Response(200)

    session = Session()
    monkeypatch.setenv("USAGI_SMOKE_PASSWORD", "synthetic-password")
    monkeypatch.setattr(sys, "argv", ["smoke_http_dev", "--meeting"])
    monkeypatch.setattr(smoke_http_dev.requests, "Session", lambda: session)
    monkeypatch.setattr(smoke_http_dev, "_sample_wav", lambda: b"synthetic-audio")
    smoke_http_dev.main()
    assert session.deleted
    assert f"intelligence_unconfigured_http={expected_status}" in capsys.readouterr().out
