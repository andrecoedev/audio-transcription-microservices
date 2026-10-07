"""Job RQ de geração de atas; nunca importado pela aplicação HTTP."""

import logging
from uuid import uuid4

from .. import engine_registry
from ..database import SessionLocal
from ..models import Transcription, TranscriptionOwnership
from ..config import settings
from ..services.usage_metering import UsageRecorder

logger = logging.getLogger(__name__)


def process_meeting_minutes_sync(
    transcription_id: int,
    context: dict,
) -> dict:
    db = SessionLocal()
    usage = None
    generator = None
    terminal_status = "failed"
    try:
        generator = engine_registry.meeting_minutes_generator
        if generator is None:
            from ..services.intelligence_provider import get_provider
            get_provider()
            generator = engine_registry.meeting_minutes_generator
        transcription = db.get(Transcription, transcription_id)
        if not transcription:
            raise RuntimeError("Transcription not found")
        if transcription.status != "completed":
            raise RuntimeError("Transcription is not completed")
        owner = db.query(TranscriptionOwnership).filter_by(transcription_id=transcription_id).first()
        # This compatibility flow has no durable revision/automatic retries.
        # A new execution really calls the provider again, so it is a new attempt.
        usage = UsageRecorder(operation_id=str(uuid4()),
            user_id=owner.user_id if owner else None, guest_session_id=owner.guest_session_id if owner else None,
            resource_type="meeting", resource_id=transcription_id, operation="legacy_minutes",
            provider="gemini", credential_source="platform", model=settings.GEMINI_MODEL, session_factory=SessionLocal)
        if hasattr(generator, "set_usage_observer"):
            generator.set_usage_observer(usage.provider_response)
        db.rollback()  # No open domain transaction while the provider executes.
        usage.record("attempt", "attempt", 1, phase="started", status="started")
        usage.record("external_call", "call", 1, phase="submitted", status="unknown")

        transcript = "\n".join(
            f"{segment.get('speaker', 'SPEAKER')}: {segment.get('text', '')}"
            for segment in transcription.segments
        )
        logger.info("Meeting minutes processing started for %s", transcription_id)
        minutes = generator.generate_minutes(
            transcription=transcript,
            meeting_context={key: value for key, value in context.items() if value},
        )
        logger.info("Meeting minutes processing completed for %s", transcription_id)
        terminal_status = "completed"
        return {
            "transcription_id": transcription_id,
            "meeting_info": {
                "title": context.get("title"),
                "date": context.get("date"),
                "participants": context.get("participants"),
                "duration": transcription.duration_seconds,
                "word_count": transcription.word_count,
            },
            "minutes": minutes,
        }
    except Exception as exc:
        logger.error(
            "Meeting minutes processing failed for %s (%s)",
            transcription_id,
            type(exc).__name__,
        )
        raise RuntimeError("Meeting minutes processing failed") from None
    finally:
        if generator is not None and hasattr(generator, "set_usage_observer"):
            generator.set_usage_observer(None)
        if usage is not None:
            usage.record("attempt_status", "state", phase="terminal", status=terminal_status)
        db.close()
