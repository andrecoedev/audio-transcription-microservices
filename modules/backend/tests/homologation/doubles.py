"""Only external boundaries are simulated; admission, FFmpeg and persistence run."""
import io
import json
import time
import wave

from fastapi import HTTPException

PROJECT = "usagi-beta-e2e"
PERSONAS = {name: f"{name}@example.invalid" for name in ("member", "mobile", "other", "admin", "google")}
SEGMENTS = [
    {"start": 0.0, "end": 10.0, "speaker": "SPEAKER_00",
     "text": "Decidimos publicar o guia de integração em português."},
    {"start": 10.0, "end": 20.0, "speaker": "SPEAKER_01",
     "text": "Pessoa Azul vai revisar o guia até 20/10/2026."},
    {"start": 20.0, "end": 30.0, "speaker": "SPEAKER_00",
     "text": "Precisamos conferir os 2.500 exemplos, ainda sem responsável ou prazo."},
    {"start": 30.0, "end": 40.0, "speaker": "SPEAKER_01",
     "text": "Qual será o canal de publicação? Isso ainda precisa ser discutido."},
]
RESULT = {"schema_version": "1", "summary": "O grupo decidiu publicar um guia de integração em português e definiu sua revisão. O canal de publicação continua em aberto.",
    "topics": [{"description": "Guia de integração", "evidence": [{"segment_order": 0, "quote": SEGMENTS[0]["text"]}]}],
    "decisions": [{"description": "Publicar o guia de integração em português.", "evidence": [{"segment_order": 0, "quote": SEGMENTS[0]["text"]}]}],
    "action_items": [
        {"description": "Revisar o guia.", "assignee": "Pessoa Azul", "due_date": "20/10/2026",
         "evidence": [{"segment_order": 1, "quote": SEGMENTS[1]["text"]}]},
        {"description": "Conferir os 2.500 exemplos.", "assignee": None, "due_date": None,
         "evidence": [{"segment_order": 2, "quote": SEGMENTS[2]["text"]}]},
    ],
    "open_questions": [{"description": "Qual será o canal de publicação?", "evidence": [{"segment_order": 3, "quote": SEGMENTS[3]["text"]}]}]}


def audio_bytes(seconds=40):
    """A real decodable, silent WAV; not ASR quality evidence."""
    data = io.BytesIO()
    with wave.open(data, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * (8000 * seconds))
    return data.getvalue()


def firebase_claims(token):
    # Exact fixture allowlist, not arbitrary UID/email supplied by the caller.
    name = next((name for name in PERSONAS if token == f"beta-e2e-{name}"), None)
    if name is None:
        raise HTTPException(401, "Could not validate credentials")
    now = int(time.time())
    return {"uid": name, "sub": name, "aud": PROJECT,
        "iss": f"https://securetoken.google.com/{PROJECT}", "auth_time": now,
        "email": PERSONAS[name], "email_verified": True, "name": f"Teste {name}",
        "firebase": {"sign_in_provider": "google.com" if name == "google" else "password"}}


class AssemblyDouble:
    model = "universal-3-5-pro"

    def __init__(self, *, delay=0, failure=None):
        self.delay, self.failure = delay, failure
        self.execution_observer = self.usage_observer = None
        self.calls = 0

    def set_execution_observer(self, callback):
        self.execution_observer = callback

    def set_usage_observer(self, callback):
        self.usage_observer = callback

    def get_metadata(self):
        return {"model": self.model, "implementation": "synthetic-e2e"}

    def transcribe_file(self, _path, *, duration_seconds, use_diarization):
        assert use_diarization is True
        self.calls += 1
        event = {"phase": "accepted", "status": "queued", "provider_id": "synthetic-e2e-remote",
            "model": self.model, "use_diarization": True}
        if self.execution_observer:
            self.execution_observer(event)
        time.sleep(self.delay)
        if self.failure:
            raise TimeoutError("Synthetic provider timeout")
        event = {**event, "phase": "polled", "status": "completed", "audio_duration_seconds": duration_seconds}
        for observer in (self.usage_observer, self.execution_observer):
            if observer:
                observer(event)
        return {"segments": SEGMENTS, "num_speakers": 2}


class IntelligenceDouble:
    def __init__(self, *, delay=0):
        self.delay = delay
        self.calls = 0
        self.observer = None

    def set_usage_observer(self, callback):
        self.observer = callback

    def generate(self, _context):
        self.calls += 1
        time.sleep(self.delay)
        return json.dumps(RESULT, ensure_ascii=False)


def install(monkeypatch, *, delay=0):
    from src.config import settings
    from src.services import firebase_identity
    from src.services.transcription_processing_service import TranscriptionProcessingService
    from src.workers import transcription_worker, meeting_intelligence_worker
    from tests.platform_helpers import configure_platform
    configure_platform(monkeypatch)
    for key, value in {"FIREBASE_AUTH_ENABLED": True, "FIREBASE_PASSWORD_ENABLED": True,
        "FIREBASE_PROJECT_ID": PROJECT, "GEMINI_API_KEY_CONFIGURED": True,
        "PLAN_POLICIES_JSON": json.dumps({"beta": {"monthly_usagi_seconds": 0,
            "max_audio_seconds": 600, "max_stored_bytes": 100000000,
            "max_queued_jobs": 2, "max_processing_jobs": 1}})}.items():
        monkeypatch.setattr(settings, key, value)
    monkeypatch.setattr(firebase_identity, "_verify_with_sdk", firebase_claims)
    assembly, intelligence = AssemblyDouble(delay=delay), IntelligenceDouble(delay=delay)
    monkeypatch.setattr(transcription_worker, "get_cloud_processing_service",
        lambda: TranscriptionProcessingService(cloud_engine=assembly))
    monkeypatch.setattr(meeting_intelligence_worker, "get_provider", lambda **_kwargs: intelligence)
    return assembly, intelligence


def prepare_policy(db):
    """Synthetic funding, not an observation of any external account."""
    from src.services.beta_settings import read_policy, update_policy
    from tests.platform_helpers import confirm_test_balance
    confirm_test_balance(db)
    row, _ = read_policy(db)
    update_policy(db, section="limits", changes={"limits.max_stored_bytes": 100000000},
        version=row.configuration_version, confirmed=True, actor_user_id=None)
    db.commit()
