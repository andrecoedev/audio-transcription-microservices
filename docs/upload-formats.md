# Upload formats

The backend allowlist is defined in `modules/backend/src/utils/upload_formats.py`.
`ALLOWED_EXTENSIONS` can reduce that allowlist for a deployment; invalid or
unknown values fail configuration validation instead of silently accepting a
format the upload validator cannot recognize. The default list is:

`mp3, wav, mp4, mpeg, m4a, flac, ogg, opus`

The `mpeg` extension remains as a legacy alias for MPEG audio. It does not add
MPEG video or transport-stream support.

`GET /guest/policy` returns the active `allowed_extensions` list along with
Guest limits. Clients may use that field for the accepted file suffixes in any
account context; Guest size and duration limits in the same response remain
Guest-specific.

## Validation and processing

The API checks the extension against `ALLOWED_EXTENSIONS` and a short binary
signature. It does not trust the browser MIME type. The signature identifies a
container or format family; it does not prove that the whole file is valid, that
its suffix describes its codec, or that it contains an audio stream.

The Worker performs the decode. FFmpeg selects the first audio stream, drops
video, and converts audio to mono 16 kHz signed PCM WAV before either local
transcription or AssemblyAI. A file with no decodable audio stream, including a
video-only MP4, fails in Worker processing. Local decoder support depends on the
FFmpeg build used by the Worker. The original upload is not sent directly to
AssemblyAI by this application; the adapter receives the normalized WAV. The
provider's accepted source formats are documented in its [supported audio and
video formats](https://support.assemblyai.com/articles/2616970375-what-audio-and-video-file-types-are-supported-by-your-api).

| Extension | Signature family checked by API | Worker requirement |
| --- | --- | --- |
| `.mp3`, `.mpeg` | Valid MPEG audio frame header or a structurally valid ID3v2 header | FFmpeg must decode an audio stream |
| `.wav` | `RIFF` + `WAVE`, or `RF64` + `WAVE` + `ds64` | FFmpeg must decode the WAVE codec; RF64 support is not universal outside compatible readers |
| `.flac` | `fLaC` stream marker | FFmpeg must decode the FLAC stream |
| `.ogg`, `.opus` | Ogg capture pattern `OggS` and version 0 | FFmpeg must find and decode an audio stream; the API checks the Ogg container, not Vorbis-versus-Opus codec identity |
| `.mp4`, `.m4a` | ISO Base Media File Format `ftyp` marker | FFmpeg must find and decode an audio stream; these suffixes share a container signature |

The MPEG audio detector uses the 11-bit frame sync and validates version, layer,
bitrate index, and sample-rate index. ID3v2 tags are common at the beginning
of MP3 files, so a structurally valid ID3v2 header is also recognized. This is
an upload gate, not a full media parser; FFmpeg remains the decode check.

RF64 is the WAVE-family form used for files larger than the 4 GiB RIFF size
limit. The API recognizes the RF64 preamble and required `ds64` chunk marker;
normal configured upload size limits still apply. FFmpeg documents RF64 support
and notes that it is less universally supported than RIFF in
[its WAV format documentation](https://ffmpeg.org/ffmpeg-formats.html#wav).

## Test coverage

The PR #17 investigation reproduced rejection of RF64 WAV by the previous
detector; RF64 is now recognized. FLAC, regular WAV, MP3 and the other generated
containers were already recognized by that detector; no FLAC defect is claimed.
An existing deployment allowed only MP3/WAV/MP4/MPEG/M4A/FLAC while the UI
advertised OGG/OPUS as well; the UI now derives its list from the active policy.
M4A uploads with a browser `video/mp4` MIME type are accepted based on their
allowed suffix and validated content, not rejected solely for that MIME label.

`tests/test_upload_formats.py` covers signature families, unsupported
configuration, and the policy response. `tests/test_upload_formats_ffmpeg.py`
generates short MP3, MPEG-1/2/2.5, MPEG Layer II, WAV/RF64, FLAC, Ogg/Vorbis, Opus, M4A, and MP4
samples with FFmpeg, then exercises upload validation and Worker normalization.
That file skips when FFmpeg is unavailable, so API-only test images do not need
the Worker binary. CI explicitly installs FFmpeg to run this integration test.
It performs no model inference or external provider calls.
