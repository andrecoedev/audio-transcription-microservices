"""Disposable HTTP/RQ journey runtime, never a production launch command."""
import os
import sys

from sqlalchemy.engine import make_url


def main():
    # Fail before loading the app, models or performing any database mutation.
    url = os.environ.get("DATABASE_URL", "")
    if (os.getenv("APP_ENV") != "test" or make_url(url).get_backend_name() != "postgresql"
        or make_url(url).database != "usagi_beta_e2e_test"):
        raise RuntimeError("This harness requires the dedicated disposable Beta E2E database")
    if any(os.getenv(key) for key in ("AAI_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY",
        "HF_TOKEN", "GOOGLE_APPLICATION_CREDENTIALS")):
        raise RuntimeError("The synthetic harness must not receive external credentials")
    from pytest import MonkeyPatch
    from tests.homologation.doubles import install, prepare_policy
    patch = MonkeyPatch()
    install(patch, delay=4)
    mode = sys.argv[1]
    if mode == "seed":
        from src.database import SessionLocal
        from src.models import User, PlatformProviderBudget
        from src.security import get_password_hash
        with SessionLocal() as db:
            if db.query(User).count() or db.query(PlatformProviderBudget).count():
                raise RuntimeError("Seed requires an empty disposable database; never overwrites")
            db.add(User(username="synthetic-admin", email="admin-local@example.invalid",
                hashed_password=get_password_hash("Synthetic-only-passphrase!"), is_superuser=True))
            db.commit()
            prepare_policy(db)
        print("Synthetic administrator and simulated policy prepared; no real grants or provider calls")
    elif mode == "api":
        import uvicorn
        from src.main import app
        uvicorn.run(app, host="0.0.0.0", port=2020, access_log=False)
    elif mode == "worker":
        from src.workers.config import get_transcription_queue
        from src.workers.transcription_worker import recover_pending_jobs
        from src.workers.meeting_intelligence_worker import recover_intelligence_jobs
        from rq import Worker
        queue = get_transcription_queue()
        recover_pending_jobs(queue)
        recover_intelligence_jobs(queue)
        Worker([queue], connection=queue.connection).work(logging_level="WARNING")
    elif mode in {"presentation", "verify", "erase-rq"}:
        from src.database import SessionLocal
        from src.models import (User, FirebaseIdentity, Transcription, TranscriptionOwnership,
            Meeting, MeetingSpeaker, MeetingIntelligence, MeetingActionItem)
        with SessionLocal() as db:
            binding = db.get(FirebaseIdentity, ("usagi-beta-e2e", "member"))
            if binding is None:
                raise RuntimeError("Complete the synthetic member journey first")
            completed = db.query(Transcription).filter_by(original_filename="Reunião sintética – integração.wav", status="completed").one()
            assert db.get(Meeting, completed.id) is not None
            assert db.query(MeetingIntelligence).filter_by(meeting_id=completed.id, status="completed").count() == 1
            assert db.query(MeetingActionItem).filter_by(meeting_id=completed.id).count() == 1
            if mode == "presentation":
                from tests.homologation.doubles import SEGMENTS
                for label, status, segments in (
                    ("longa", "completed", [{**SEGMENTS[i % 4], "start": float(i * 10), "end": float(i * 10 + 10)} for i in range(200)]),
                    ("silêncio", "completed", []), ("falha", "failed", []),
                ):
                    title = f"Fixture sintética {label}.wav"
                    existing = db.query(Transcription).filter_by(original_filename=title).first()
                    if existing:
                        if label == "longa":
                            meeting = db.get(Meeting, existing.id)
                            known = {speaker.speaker_id for speaker in meeting.speakers}
                            for speaker_id in ("SPEAKER_00", "SPEAKER_01"):
                                if speaker_id not in known:
                                    meeting.speakers.append(MeetingSpeaker(speaker_id=speaker_id))
                        continue
                    row = Transcription(filename="synthetic-presentation", original_filename=title,
                        file_size_mb=0, duration_seconds=2000 if label == "longa" else 40,
                        transcription_model="assemblyai", use_diarization=True, status=status,
                        segments=segments, num_speakers=2 if segments else 0,
                        word_count=sum(len(s["text"].split()) for s in segments),
                        error_message="Transcription processing failed" if status == "failed" else None)
                    db.add(row)
                    db.flush()
                    db.add(TranscriptionOwnership(transcription_id=row.id, user_id=binding.user_id,
                        owner_sub=db.get(User, binding.user_id).username))
                    if status == "completed":
                        meeting = Meeting(id=row.id, title=title, language="pt")
                        if segments:
                            meeting.speakers = [MeetingSpeaker(speaker_id=s) for s in ("SPEAKER_00", "SPEAKER_01")]
                        db.add(meeting)
                db.commit()
            if mode == "erase-rq":
                from src.workers.config import get_transcription_queue
                queue = get_transcription_queue()
                ids = [f"transcription_{completed.id}"] + [f"meeting_intelligence_{r.id}" for r in db.query(MeetingIntelligence).filter_by(meeting_id=completed.id)]
                for job_id in ids:
                    job = queue.fetch_job(job_id)
                    if job:
                        assert job.get_status() == "finished"
                        job.delete()
            print("Synthetic PostgreSQL results verified; mode:", mode)
    else:
        raise ValueError("Expected seed, api, worker, presentation, verify or erase-rq")


if __name__ == "__main__":
    main()
