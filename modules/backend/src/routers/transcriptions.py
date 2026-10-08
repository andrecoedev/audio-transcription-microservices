"""Rotas de consulta e do fluxo assíncrono oficial de transcrição."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from ..authorization import enforce_transcription_access, is_admin, ownership_filter
from ..config import settings
from ..database import get_db
from ..models import GuestSession, Transcription, TranscriptionJob, TranscriptionOwnership
from ..schemas import JobResponse, JobStatusResponse
from ..security import TokenData, require_scope_when
from ..services.audit import append_audit_event
from ..services.transcription_deletion import ActiveTranscriptionError, delete_transcription_data
from ..services.rate_limit import enforce_rate_limit
from ..services.provider_policy import require_guest_processing
from ..services.platform_budget import reserve_platform_call
from ..services.provider_credentials import preferences_for, resolve_transcription
from ..services.transcription_entitlements import reserve_transcription
from ..services.storage_lifecycle import upload_directory
from ..services.audio_storage import get_audio_storage, schedule_audio_cleanup, cleanup_after_commit
from ..services.object_storage import StorageError
from ..utils.uploads import UploadValidationError, store_validated_upload
from ..utils.http_limits import BodyLimitedRoute
from ..workers.config import get_transcription_queue, is_redis_available

logger = logging.getLogger(__name__)


class UploadLimitedRoute(BodyLimitedRoute):
    """Enforce the IP upload budget before FastAPI parses multipart bodies."""

    def get_route_handler(self):
        original = super().get_route_handler()

        async def limited(request: Request):
            if request.method == "POST" and request.url.path == "/guest/transcriptions/jobs":
                require_guest_processing()  # Reject before Redis, parsing or spooling.
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
            ownership_filter(current_user.user_id, current_user.username, current_user.registration_source)
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
            ownership_filter(current_user.user_id, current_user.username, current_user.registration_source)
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
    use_diarization: bool | None = Form(None),
    transcription_model: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: Optional[TokenData] = Depends(
        require_scope_when("transcribe", settings.AUTH_PROTECT_PROCESSING)
    ),
):
    """Valida o upload, persiste o job e o enfileira no RQ."""
    if use_diarization is None:
        use_diarization = preferences_for(db, current_user.user_id)["use_diarization"]
    return await enqueue_transcription(request, file, use_diarization, transcription_model, db, current_user)


async def enqueue_transcription(request, file, use_diarization, transcription_model, db, current_user,
                                *, guest_session: GuestSession | None = None):
    """One durable upload/queue path, with ownership supplied by verified context."""
    public = guest_session is not None or current_user.registration_source == "public"
    enforce_rate_limit(request, "job-user", str(current_user.user_id if current_user else "anonymous"))
    if public and guest_session is None:
        enforce_rate_limit(request, "public-job")
    if transcription_model not in {None, "automatic", "whisper", "assemblyai"}:
        await file.close()
        raise HTTPException(status_code=400, detail="Invalid transcription model")
    if guest_session is not None:
        if transcription_model != "assemblyai":
            raise HTTPException(403, "Visitor processing supports only AssemblyAI; no local fallback")
        require_guest_processing()
        selection = {"credential_source": "platform", "credential_id": None, "credential_user_id": None}
    else:
        selection = resolve_transcription(db, current_user, transcription_model)
        transcription_model = selection["provider"]

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
    storage = None

    try:
        storage = get_audio_storage(_UPLOAD_DIRECTORY)
        saved_upload = await store_validated_upload(
            file,
            storage=storage,
            allowed_extensions=settings.allowed_extensions_list,
            max_size_bytes=min(settings.max_upload_size_bytes, settings.PUBLIC_MAX_UPLOAD_MB * 1024 * 1024) if public else settings.max_upload_size_bytes,
        )

        transcription = Transcription(
            filename=saved_upload.key,
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
            input_path="",
            input_object_key=saved_upload.key,
            use_diarization=use_diarization,
            transcription_model=transcription_model,
            status="queued",
        )
        db.add(job)
        for name in ("credential_source", "credential_id", "credential_user_id"):
            setattr(job, name, selection[name])
        if public:
            job.max_duration_seconds = settings.PUBLIC_MAX_AUDIO_SECONDS
            job.timeout_seconds = settings.PUBLIC_JOB_TIMEOUT_SECONDS
        if transcription_model == "assemblyai":
            job.max_duration_seconds = min(job.max_duration_seconds or settings.AAI_MAX_AUDIO_SECONDS,
                                           settings.AAI_MAX_AUDIO_SECONDS)
            if selection["credential_source"] == "platform":
                reserve_platform_call(db, transcription.id, "guest" if guest_session else "local")
        if guest_session is not None:
            db.add(TranscriptionOwnership(transcription_id=transcription.id,
                   owner_sub=f"guest:{guest_session.id}", guest_session_id=guest_session.id))
        elif not current_user or current_user.user_id is None or not current_user.username:
            raise RuntimeError("Persistent authenticated identity is required")
        else:
            db.add(TranscriptionOwnership(
                transcription_id=transcription.id,
                owner_sub=current_user.username,
                user_id=current_user.user_id,
            ))
        if guest_session is None:
            reservation = reserve_transcription(db, current_user.user_id, transcription.id, selection,
                saved_upload.size_bytes, "object:" + saved_upload.key)
            job.max_duration_seconds = min(job.max_duration_seconds or int(reservation.reserved_seconds),
                                           int(reservation.reserved_seconds))
        append_audit_event(
            db,
            event="transcription.created",
            actor_user_id=current_user.user_id if current_user else None,
            resource_type="transcription",
            resource_id=transcription.id,
            metadata={
                "provider": transcription_model,
                "diarization": use_diarization,
                "context": "guest" if guest_session else ("public" if public else "local"),
            },
        )
        db.commit()

        from ..services.usage_storage import record_object_put
        record_object_put(db, "object:" + saved_upload.key, saved_upload.size_bytes,
            resource_id=transcription.id, user_id=current_user.user_id if current_user else None,
            guest_session_id=guest_session.id if guest_session else None)
        try:
            queue.enqueue(
                "src.workers.transcription_worker.process_transcription_job_sync",
                transcription.id,
                job_id=f"transcription_{transcription.id}",
                **({"job_timeout": job.timeout_seconds} if job.timeout_seconds else {}),
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
            # Enqueue failure can be ambiguous; never refund automatically. A
            # published message still must pass the atomic terminal DB claim.
            from ..services.transcription_entitlements import reservation_for
            reservation_for(db, transcription.id).state = "unknown"
            append_audit_event(
                db,
                event="transcription.failed",
                actor_type="system",
                resource_type="transcription",
                resource_id=transcription.id,
                metadata={"stage": "enqueue"},
            )
            schedule_audio_cleanup(db, "object:" + saved_upload.key)
            db.commit()
            cleanup_after_commit(db, ["object:" + saved_upload.key], storage=storage)
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
        db.rollback()
        if saved_upload:
            schedule_audio_cleanup(db, "object:" + saved_upload.key)
            db.commit()
            cleanup_after_commit(db, ["object:" + saved_upload.key], storage=storage)
        raise
    except Exception as exc:
        db.rollback()
        if saved_upload:
            # On a DB outage, an unreferenced upload is caught by age-based
            # reconciliation. Never leak the storage exception to HTTP/RQ.
            try:
                schedule_audio_cleanup(db, "object:" + saved_upload.key)
                db.commit()
                cleanup_after_commit(db, ["object:" + saved_upload.key], storage=storage)
            except Exception:
                db.rollback()
                logger.warning("Upload cleanup deferred to reconciliation")
        logger.error(
            "Unexpected error while creating transcription job (%s)",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503 if isinstance(exc, StorageError) else 500,
            detail="Audio storage is temporarily unavailable" if isinstance(exc, StorageError) else "Unable to create transcription job",
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
