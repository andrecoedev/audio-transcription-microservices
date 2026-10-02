"""Rotas de consulta e do fluxo assíncrono oficial de transcrição."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.routing import APIRoute
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..authorization import enforce_transcription_access, is_admin
from ..config import settings
from ..database import get_db
from ..models import Transcription, TranscriptionJob, TranscriptionOwnership
from ..schemas import JobResponse, JobStatusResponse
from ..security import TokenData, require_scope_when
from ..services.audit import append_audit_event
from ..services.transcription_deletion import ActiveTranscriptionError, delete_transcription_data
from ..services.rate_limit import enforce_rate_limit
from ..services.storage_lifecycle import delete_file_idempotently, upload_directory
from ..utils.uploads import UploadValidationError, save_validated_upload
from ..workers.config import get_transcription_queue, is_redis_available

logger = logging.getLogger(__name__)


class UploadLimitedRoute(APIRoute):
    """Enforce the IP upload budget before FastAPI parses multipart bodies."""

    def get_route_handler(self):
        original = super().get_route_handler()

        async def limited(request: Request):
            if request.method == "POST" and request.url.path == "/transcriptions/jobs":
                enforce_rate_limit(request, "upload-ip")
            return await original(request)

        return limited


router = APIRouter(route_class=UploadLimitedRoute)

_UPLOAD_DIRECTORY = upload_directory()


@router.get("/transcriptions")
async def list_transcriptions(
    skip: int = 0,
    limit: int = 10,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Optional[TokenData] = Depends(
        require_scope_when("read_transcriptions", settings.AUTH_PROTECT_READS)
    ),
):
    """Lista transcrições com paginação e filtro opcional de status."""
    query = db.query(Transcription)

    if current_user and not is_admin(current_user):
        query = query.join(
            TranscriptionOwnership,
            TranscriptionOwnership.transcription_id == Transcription.id,
        )
        query = query.filter(
            or_(
                TranscriptionOwnership.user_id == current_user.user_id,
                (
                    TranscriptionOwnership.user_id.is_(None)
                    & (TranscriptionOwnership.owner_sub == current_user.username)
                ),
            )
        )

    if status:
        query = query.filter(Transcription.status == status)

    total = query.count()
    transcriptions = (
        query.order_by(Transcription.created_at.desc()).offset(skip).limit(limit).all()
    )
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "transcriptions": [item.to_dict() for item in transcriptions],
    }


@router.get("/transcriptions/{transcription_id}")
async def get_transcription(
    transcription_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[TokenData] = Depends(
        require_scope_when("read_transcriptions", settings.AUTH_PROTECT_READS)
    ),
):
    """Obtém o resultado e os metadados de uma transcrição."""
    transcription = db.get(Transcription, transcription_id)
    if not transcription:
        raise HTTPException(status_code=404, detail="Transcription not found")

    enforce_transcription_access(db, transcription_id, current_user, write=False)
    return transcription.to_dict()


@router.delete("/transcriptions/{transcription_id}")
async def delete_transcription(
    transcription_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[TokenData] = Depends(
        require_scope_when("delete_transcriptions", settings.AUTH_PROTECT_PROCESSING)
    ),
):
    """Remove a transcrição e os registros locais associados."""
    transcription = db.get(Transcription, transcription_id)
    if not transcription:
        raise HTTPException(status_code=404, detail="Transcription not found")

    enforce_transcription_access(db, transcription_id, current_user, write=True)

    try:
        delete_transcription_data(
            db, transcription, current_user.user_id if current_user else None
        )
    except ActiveTranscriptionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    logger.info("Transcription %s deleted", transcription_id)
    return {"message": "Transcription deleted successfully"}


@router.get("/stats")
async def get_statistics(
    db: Session = Depends(get_db),
    current_user: Optional[TokenData] = Depends(
        require_scope_when("read_transcriptions", settings.AUTH_PROTECT_READS)
    ),
):
    """Obtém estatísticas gerais do sistema."""
    query = db.query(Transcription)
    if current_user and not is_admin(current_user):
        query = query.join(TranscriptionOwnership).filter(
            or_(
                TranscriptionOwnership.user_id == current_user.user_id,
                (
                    TranscriptionOwnership.user_id.is_(None)
                    & (TranscriptionOwnership.owner_sub == current_user.username)
                ),
            )
        )
    total = query.count()
    completed = query.filter(Transcription.status == "completed").count()
    failed = query.filter(Transcription.status == "failed").count()
    processing = query.filter(Transcription.status == "processing").count()
    return {
        "total_transcriptions": total,
        "completed": completed,
        "failed": failed,
        "processing": processing,
    }


@router.post("/transcriptions/jobs", response_model=JobResponse, status_code=202)
async def create_transcription_job(
    request: Request,
    file: UploadFile = File(...),
    use_diarization: bool = Form(False),
    transcription_model: str = Form("whisper"),
    db: Session = Depends(get_db),
    current_user: Optional[TokenData] = Depends(
        require_scope_when("transcribe", settings.AUTH_PROTECT_PROCESSING)
    ),
):
    """Valida o upload, persiste o job e o enfileira no RQ."""
    enforce_rate_limit(request, "job-user", str(current_user.user_id if current_user else "anonymous"))
    if transcription_model not in {"whisper", "assemblyai"}:
        await file.close()
        raise HTTPException(status_code=400, detail="Invalid transcription model")

    try:
        queue = get_transcription_queue()
    except Exception as exc:
        await file.close()
        logger.error("Unable to configure Redis queue (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Job queue is temporarily unavailable",
        )
    if not is_redis_available(queue.connection):
        await file.close()
        logger.error("Job creation rejected because Redis is unavailable")
        raise HTTPException(status_code=503, detail="Job queue is temporarily unavailable")

    saved_upload = None
    transcription = None
    job = None

    try:
        saved_upload = await save_validated_upload(
            file,
            destination=_UPLOAD_DIRECTORY,
            allowed_extensions=settings.allowed_extensions_list,
            max_size_bytes=settings.max_upload_size_bytes,
        )

        transcription = Transcription(
            filename=saved_upload.path.name,
            original_filename=saved_upload.original_filename,
            file_size_mb=saved_upload.size_bytes / (1024 * 1024),
            duration_seconds=0.0,
            transcription_model=transcription_model,
            use_diarization=use_diarization,
            segments=[],
            status="queued",
        )
        db.add(transcription)
        db.flush()

        job = TranscriptionJob(
            transcription_id=transcription.id,
            input_path=str(saved_upload.path),
            use_diarization=use_diarization,
            transcription_model=transcription_model,
            status="queued",
        )
        db.add(job)
        if not current_user or current_user.user_id is None or not current_user.username:
            raise RuntimeError("Persistent authenticated identity is required")
        db.add(
            TranscriptionOwnership(
                transcription_id=transcription.id,
                owner_sub=current_user.username,
                user_id=current_user.user_id,
            )
        )
        append_audit_event(
            db,
            event="transcription.created",
            actor_user_id=current_user.user_id,
            resource_type="transcription",
            resource_id=transcription.id,
            metadata={
                "provider": transcription_model,
                "diarization": use_diarization,
            },
        )
        db.commit()

        try:
            queue.enqueue(
                "src.workers.transcription_worker.process_transcription_job_sync",
                transcription.id,
                job_id=f"transcription_{transcription.id}",
            )
        except Exception as exc:
            logger.error(
                "Redis enqueue failed for transcription %s (%s)",
                transcription.id,
                type(exc).__name__,
            )
            transcription.status = "failed"
            transcription.error_message = "Job queue is temporarily unavailable"
            job.status = "failed"
            job.error_message = transcription.error_message
            append_audit_event(
                db,
                event="transcription.failed",
                actor_type="system",
                resource_type="transcription",
                resource_id=transcription.id,
                metadata={"stage": "enqueue"},
            )
            db.commit()
            delete_file_idempotently(saved_upload.path)
            raise HTTPException(
                status_code=503,
                detail="Job queue is temporarily unavailable",
            )

        logger.info("Transcription job %s created and queued", transcription.id)
        return JobResponse(
            id=transcription.id,
            transcription_id=transcription.id,
            status_url=f"/transcriptions/jobs/{transcription.id}/status",
            result_url=f"/transcriptions/{transcription.id}",
            message="Transcription job queued successfully",
        )
    except UploadValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        if saved_upload:
            delete_file_idempotently(saved_upload.path)
        logger.error(
            "Unexpected error while creating transcription job (%s)",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="Unable to create transcription job",
        )
    finally:
        await file.close()


@router.get(
    "/transcriptions/jobs/{transcription_id}/status",
    response_model=JobStatusResponse,
)
@router.get(
    "/transcriptions/{transcription_id}/status",
    response_model=JobStatusResponse,
)
async def get_job_status(
    transcription_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[TokenData] = Depends(
        require_scope_when("read_transcriptions", settings.AUTH_PROTECT_READS)
    ),
):
    """Obtém o status persistido; o primeiro caminho preserva o contrato React."""
    transcription = db.get(Transcription, transcription_id)
    job = (
        db.query(TranscriptionJob)
        .filter(TranscriptionJob.transcription_id == transcription_id)
        .first()
    )
    if not transcription or not job:
        raise HTTPException(status_code=404, detail="Transcription job not found")

    enforce_transcription_access(db, transcription_id, current_user, write=False)

    queue_size = 0
    try:
        queue = get_transcription_queue()
        if is_redis_available(queue.connection):
            queue_size = len(queue)
    except Exception:
        logger.warning("Unable to read Redis queue size")

    return JobStatusResponse(
        transcription_id=transcription_id,
        transcription_status=transcription.status,
        job_status=job.status,
        queue_size=queue_size,
        error_message=transcription.error_message or job.error_message,
        processing_time_seconds=transcription.processing_time_seconds,
        word_count=transcription.word_count,
        num_speakers=transcription.num_speakers,
    )
