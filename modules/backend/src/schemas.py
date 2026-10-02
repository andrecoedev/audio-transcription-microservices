from typing import List, Optional
from datetime import datetime

from pydantic import BaseModel


class MeetingMinutesRequest(BaseModel):
    transcription_id: int
    title: Optional[str] = None
    date: Optional[str] = None
    participants: Optional[List[str]] = None


class JobResponse(BaseModel):
    """Resposta ao enfileirar um novo job de transcrição."""
    id: int
    transcription_id: int
    status_url: str
    result_url: str
    message: str = "Job enfileirado com sucesso"


class JobStatusResponse(BaseModel):
    """Status atual de um job de transcrição."""
    transcription_id: int
    transcription_status: str  # queued, processing, completed, failed
    job_status: str  # queued, processing, completed, failed
    queue_size: int
    error_message: Optional[str] = None
    processing_time_seconds: Optional[float] = None
    word_count: Optional[int] = None
    num_speakers: Optional[int] = None
