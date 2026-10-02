"""Small compatibility boundary for Pyannote 3 and 4 pipeline contracts."""


def pipeline_config(pyannote_version: str, token: str) -> tuple[str, dict[str, str]]:
    major = int(pyannote_version.split(".", 1)[0])
    if major >= 4:
        return "pyannote/speaker-diarization-community-1", {"token": token}
    return "pyannote/speaker-diarization-3.1", {"use_auth_token": token}


def speaker_turns(output):
    annotation = getattr(output, "speaker_diarization", output)
    for turn, _, speaker in annotation.itertracks(yield_label=True):
        yield turn, speaker
