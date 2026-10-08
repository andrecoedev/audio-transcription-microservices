import shutil
import subprocess
from io import BytesIO
from pathlib import Path

import pytest
from starlette.datastructures import UploadFile

from src.models import Transcription
from src.services.object_storage import LocalObjectStorage
from src.utils.audio import AudioProcessingError, convert_to_wav
from src.utils.upload_formats import DEFAULT_ALLOWED_EXTENSIONS
from src.utils.uploads import store_validated_upload


pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg is only available in the Worker image"
)


def _generate(ffmpeg, destination, *output_options, sample_rate=16000):
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:duration=0.25",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            *output_options,
            "-y",
            str(destination),
        ],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def ffmpeg_audio_fixtures(tmp_path):
    ffmpeg = shutil.which("ffmpeg")
    fixtures = {}
    outputs = {
        "tagged.mp3": ["-c:a", "libmp3lame"],
        "raw.mp3": ["-c:a", "libmp3lame", "-write_id3v2", "0", "-write_id3v1", "0"],
        "legacy.mpeg": ["-c:a", "libmp3lame", "-f", "mp3"],
        "layer2.mpeg": ["-c:a", "mp2", "-f", "mp2"],
        "sample.wav": ["-c:a", "pcm_s16le"],
        "sample-rf64.wav": ["-c:a", "pcm_s16le", "-rf64", "always"],
        "sample.flac": ["-c:a", "flac"],
        "sample.ogg": ["-c:a", "libvorbis"],
        "sample.opus": ["-c:a", "libopus"],
        "sample.m4a": ["-c:a", "aac"],
    }
    for name, options in outputs.items():
        source = tmp_path / name
        _generate(ffmpeg, source, *options)
        fixtures[name] = source

    for name, sample_rate in (("mpeg1.mp3", 44100), ("mpeg2_5.mp3", 11025)):
        source = tmp_path / name
        _generate(
            ffmpeg,
            source,
            "-c:a",
            "libmp3lame",
            "-write_id3v2",
            "0",
            "-write_id3v1",
            "0",
            sample_rate=sample_rate,
        )
        fixtures[name] = source

    mp4_source = tmp_path / "sample.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=64x64:rate=2:duration=0.25",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:duration=0.25",
            "-c:v",
            "mpeg4",
            "-c:a",
            "aac",
            "-shortest",
            "-y",
            str(mp4_source),
        ],
        check=True,
        capture_output=True,
    )
    fixtures[mp4_source.name] = mp4_source
    return fixtures


@pytest.mark.asyncio
async def test_ffmpeg_generated_formats_upload_and_normalize_in_worker(
    ffmpeg_audio_fixtures, tmp_path, db_context, auth_headers
):
    storage = LocalObjectStorage(tmp_path / "objects")

    for name, source in ffmpeg_audio_fixtures.items():
        result = await store_validated_upload(
            UploadFile(filename=name, file=BytesIO(source.read_bytes())),
            storage,
            DEFAULT_ALLOWED_EXTENSIONS,
            max_size_bytes=1024 * 1024,
        )
        assert result.original_filename == name

        response = db_context["client"].post(
            "/transcriptions/jobs",
            files={"file": (name, source.read_bytes(), "application/octet-stream")},
            headers=auth_headers(),
        )
        assert response.status_code == 202
        db = db_context["session_factory"]()
        try:
            transcription = db.get(Transcription, response.json()["id"])
            assert transcription.original_filename == name
        finally:
            db.close()

        normalized = tmp_path / f"{source.stem}.normalized.wav"
        _, duration = convert_to_wav(str(source), str(normalized))
        assert duration > 0
        assert normalized.read_bytes().startswith(b"RIFF")


def test_video_without_audio_is_rejected_by_worker_decode(tmp_path):
    source = tmp_path / "silent.mp4"
    destination = tmp_path / "normalized.wav"
    subprocess.run([
        shutil.which("ffmpeg"), "-v", "error", "-f", "lavfi", "-i",
        "testsrc=size=64x64:rate=2:duration=0.25", "-c:v", "mpeg4", "-an",
        "-y", str(source),
    ], check=True, capture_output=True)
    with pytest.raises(AudioProcessingError, match="Unable to convert"):
        convert_to_wav(str(source), str(destination))
    assert not destination.exists()
