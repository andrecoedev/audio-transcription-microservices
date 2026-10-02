"""Job RQ de geração de atas; nunca importado pela aplicação HTTP."""

import logging

from .. import engine_registry
from ..config import settings
from ..database import SessionLocal
from ..models import Transcription

logger = logging.getLogger(__name__)


def process_meeting_minutes_sync(
    transcription_id: int,
    context: dict,
) -> dict:
    db = SessionLocal()
    try:
        generator = engine_registry.meeting_minutes_generator
        if generator is None:
            from ..services.meeting_minutes import MeetingMinutesGenerator
            engine_registry.meeting_minutes_generator = MeetingMinutesGenerator(settings.GEMINI_API_KEY)
            generator = engine_registry.meeting_minutes_generator
        transcription = db.get(Transcription, transcription_id)
        if not transcription:
            raise RuntimeError("Transcription not found")
        if transcription.status != "completed":
            raise RuntimeError("Transcription is not completed")

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
        db.close()
