"""
Endpoints de compatibilidade com a arquitetura de microserviços anterior.

Expõe /diarize, /whisper/transcribe_segment e /assemblyai/transcribe_segment
como interfaces diretas aos engines, mantendo contrato HTTP já consumido por
clientes legados.
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from .. import engine_registry
from ..config import settings
from ..security import TokenData, require_scope_when
from ..utils.audio import remove_temp_file_with_retry
from ..utils.uploads import UploadValidationError, save_validated_upload

logger = logging.getLogger(__name__)

router = APIRouter()
_TEMP_DIRECTORY = Path(__file__).resolve().parents[2] / "temp"


async def _save_compat_upload(file: UploadFile):
    try:
        return await save_validated_upload(
            file,
            destination=_TEMP_DIRECTORY,
            allowed_extensions=settings.allowed_extensions_list,
            max_size_bytes=settings.max_upload_size_bytes,
        )
    except UploadValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/diarize")
async def diarize_endpoint(
    file: UploadFile = File(...),
    min_duration: float = Form(0.7),
    silence_threshold: int = Form(-30),
    current_user: Optional[TokenData] = Depends(
        require_scope_when("transcribe", settings.AUTH_PROTECT_PROCESSING)
    ),
):
    """
    Endpoint direto de diarização (compatível com pyannote_model.py).

    Args:
        file:              Arquivo de áudio.
        min_duration:      Duração mínima do segmento (segundos).
        silence_threshold: Limiar de silêncio (dB).

    Returns:
        Segmentos com speaker labels.
    """
    if not engine_registry.diarization_engine:
        raise HTTPException(
            status_code=503,
            detail="Diarization engine not loaded. Check HF_TOKEN configuration.",
        )

    temp_path: Optional[str] = None
    temp_wav_path: Optional[str] = None

    try:
        saved_upload = await _save_compat_upload(file)
        temp_path = str(saved_upload.path)
        if saved_upload.extension != "wav":
            temp_wav_path = engine_registry.diarization_engine.convert_to_wav(temp_path)
        else:
            temp_wav_path = temp_path

        result = engine_registry.diarization_engine.diarize(
            temp_wav_path, min_duration, silence_threshold
        )
        return result

    finally:
        await file.close()
        await remove_temp_file_with_retry(temp_path)
        if temp_wav_path and temp_wav_path != temp_path:
            await remove_temp_file_with_retry(temp_wav_path)


@router.post("/whisper/transcribe_segment")
async def whisper_transcribe_segment_endpoint(
    file: UploadFile = File(...),
    start: float = Form(0.0),
    end: Optional[float] = Form(None),
    current_user: Optional[TokenData] = Depends(
        require_scope_when("transcribe", settings.AUTH_PROTECT_PROCESSING)
    ),
):
    """
    Endpoint direto de transcrição Whisper (compatível com whisper_model.py).

    Args:
        file:  Arquivo de áudio.
        start: Tempo de início (segundos).
        end:   Tempo de fim (segundos, None = até o final).

    Returns:
        Texto transcrito.
    """
    if not engine_registry.whisper_engine:
        raise HTTPException(
            status_code=503,
            detail="Whisper engine not loaded. Check HF_TOKEN configuration.",
        )

    temp_path: Optional[str] = None

    try:
        saved_upload = await _save_compat_upload(file)
        temp_path = str(saved_upload.path)
        text = engine_registry.whisper_engine.transcribe_segment(temp_path, start, end)
        return {"transcription": text}

    finally:
        await file.close()
        await remove_temp_file_with_retry(temp_path)


@router.post("/assemblyai/transcribe_segment")
async def assemblyai_transcribe_segment_endpoint(
    file: UploadFile = File(...),
    start: float = Form(0.0),
    end: Optional[float] = Form(None),
    current_user: Optional[TokenData] = Depends(
        require_scope_when("transcribe", settings.AUTH_PROTECT_PROCESSING)
    ),
):
    """
    Endpoint direto de transcrição AssemblyAI (compatível com assemblyai_model.py).

    Args:
        file:  Arquivo de áudio.
        start: Tempo de início (segundos).
        end:   Tempo de fim (segundos, None = até o final).

    Returns:
        Texto transcrito.
    """
    if not engine_registry.assemblyai_engine:
        raise HTTPException(
            status_code=503,
            detail="AssemblyAI engine not loaded. Check AAI_API_KEY configuration.",
        )

    temp_path: Optional[str] = None

    try:
        saved_upload = await _save_compat_upload(file)
        temp_path = str(saved_upload.path)
        text = engine_registry.assemblyai_engine.transcribe_segment(temp_path, start, end)
        return {"transcription": text}

    finally:
        await file.close()
        await remove_temp_file_with_retry(temp_path)
