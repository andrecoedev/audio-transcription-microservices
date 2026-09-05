"""
Router principal de transcrição de áudio.

As chamadas síncronas de ML (diarize, transcribe_segment) são despachadas para
o thread-pool padrão do asyncio via loop.run_in_executor, liberando o event
loop para responder a outros requests durante o processamento.

Leituras dos engines (is not None) não precisam do mutation_lock — são operações
atômicas no nível do GIL.  Apenas POST /api-keys muta os engines.
"""

import asyncio
import logging
import time
import uuid
from functools import partial
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import engine_registry
from ..authorization import create_transcription_owner
from ..config import settings
from ..database import get_db
from ..models import Transcription
from ..security import TokenData, require_scope_when
from ..utils.audio import convert_to_wav, remove_temp_file_with_retry
from ..utils.uploads import UploadValidationError, save_validated_upload

logger = logging.getLogger(__name__)

router = APIRouter()

_TEMP_DIRECTORY = Path(__file__).resolve().parents[2] / "temp"


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    use_diarization: bool = Form(False),
    transcription_model: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: Optional[TokenData] = Depends(
        require_scope_when("transcribe", settings.AUTH_PROTECT_PROCESSING)
    ),
):
    """
    Transcreve um arquivo de áudio usando os engines integrados.

    Args:
        file:               Arquivo de áudio.
        use_diarization:    Se deve usar diarização de falantes (Pyannote).
        transcription_model: Modelo de transcrição ("whisper" ou "assemblyai").

    Returns:
        Resultado da transcrição com segmentos e metadados.
    """
    start_time = time.time()
    temp_input_path: Optional[str] = None
    temp_wav_path: Optional[str] = None

    try:
        saved_upload = await save_validated_upload(
            file,
            destination=_TEMP_DIRECTORY,
            allowed_extensions=settings.allowed_extensions_list,
            max_size_bytes=settings.max_upload_size_bytes,
        )
        temp_input_path = str(saved_upload.path)
        file_size_mb = saved_upload.size_bytes / (1024 * 1024)

        # ---- Converter para WAV (I/O-bound via pydub/ffmpeg, em executor) ----
        wav_output_path = str(_TEMP_DIRECTORY / f"wav_{uuid.uuid4()}.wav")
        loop = asyncio.get_event_loop()
        temp_wav_path, duration = await loop.run_in_executor(
            None, convert_to_wav, temp_input_path, wav_output_path
        )

        logger.info(
            "Processing validated upload %s (%.2f MB, %.2fs)",
            saved_upload.original_filename,
            file_size_mb,
            duration,
        )

        # ---- Selecionar modelo ----
        if not transcription_model:
            transcription_model = "whisper" if engine_registry.whisper_engine else "assemblyai"

        # ---- Criar registro inicial no banco ----
        transcription_record = Transcription(
            filename=saved_upload.path.name,
            original_filename=saved_upload.original_filename,
            file_size_mb=file_size_mb,
            duration_seconds=duration,
            transcription_model=transcription_model,
            use_diarization=use_diarization,
            status="processing",
            segments=[],
        )
        db.add(transcription_record)
        db.commit()
        db.refresh(transcription_record)

        create_transcription_owner(db, transcription_record.id, current_user)

        # ---- Processar áudio ----
        try:
            segments: list = []
            num_speakers: int = 0

            if use_diarization:
                segments, num_speakers = await _process_with_diarization(
                    temp_wav_path, transcription_model, loop
                )
            else:
                segments, num_speakers = await _process_without_diarization(
                    temp_wav_path, duration, transcription_model, loop
                )

            word_count = sum(len(seg["text"].split()) for seg in segments)
            processing_time = time.time() - start_time

            # ---- Persistir resultado ----
            transcription_record.segments = segments
            transcription_record.num_speakers = num_speakers
            transcription_record.word_count = word_count
            transcription_record.processing_time_seconds = processing_time
            transcription_record.status = "completed"
            db.commit()

            logger.info(f"Transcription completed in {processing_time:.2f}s")

            return {
                "id": transcription_record.id,
                "segments": segments,
                "num_speakers": num_speakers,
                "word_count": word_count,
                "duration": duration,
                "model": transcription_model,
                "diarization": use_diarization,
                "processing_time": processing_time,
            }

        except Exception as exc:
            transcription_record.status = "failed"
            transcription_record.error_message = "Transcription processing failed"
            db.commit()
            if isinstance(exc, HTTPException):
                raise
            raise

    except UploadValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    except HTTPException:
        raise

    except Exception:
        logger.exception("Error processing synchronous transcription")
        raise HTTPException(status_code=500, detail="Unable to process transcription")

    finally:
        await file.close()
        await remove_temp_file_with_retry(temp_input_path)
        await remove_temp_file_with_retry(temp_wav_path)


# ---------------------------------------------------------------------------
# Helpers de processamento (privados)
# ---------------------------------------------------------------------------

async def _process_with_diarization(
    wav_path: str,
    transcription_model: str,
    loop: asyncio.AbstractEventLoop,
) -> tuple[list, int]:
    """Executa diarização e transcrição de cada segmento no thread-pool."""
    if not engine_registry.diarization_engine:
        raise HTTPException(
            status_code=503,
            detail="Diarization engine not loaded. Check HF_TOKEN configuration.",
        )

    # Diarização — síncrona, pesada → thread-pool
    logger.info("Executando diarização...")
    diarization_result = await loop.run_in_executor(
        None, engine_registry.diarization_engine.diarize, wav_path
    )
    diar_segments = diarization_result["segments"]
    num_speakers = diarization_result["num_speakers"]
    logger.info(
        f"Diarização concluída: {len(diar_segments)} segmentos, {num_speakers} falantes"
    )

    # Selecionar função de transcrição
    transcribe_func = _get_transcribe_func(transcription_model)

    # Transcrever cada segmento no thread-pool
    segments: list = []
    for seg in diar_segments:
        try:
            fn = partial(transcribe_func, wav_path, start=seg["start"], end=seg["end"])
            text = await loop.run_in_executor(None, fn)
            segments.append({
                "start": seg["start"],
                "end": seg["end"],
                "speaker": seg["speaker"],
                "text": text,
            })
        except Exception as e:
            logger.warning(
                f"Erro ao transcrever segmento {seg['start']:.2f}-{seg['end']:.2f}: {e}"
            )
            segments.append({
                "start": seg["start"],
                "end": seg["end"],
                "speaker": seg["speaker"],
                "text": "[erro na transcrição]",
            })

    return segments, num_speakers


async def _process_without_diarization(
    wav_path: str,
    duration: float,
    transcription_model: str,
    loop: asyncio.AbstractEventLoop,
) -> tuple[list, int]:
    """Transcreve o arquivo inteiro no thread-pool, sem diarização."""
    transcribe_func = _get_transcribe_func(transcription_model)

    logger.info(f"Transcrevendo com {transcription_model} (sem diarização)...")
    fn = partial(transcribe_func, wav_path)
    text = await loop.run_in_executor(None, fn)

    segments = [{
        "start": 0.0,
        "end": duration,
        "speaker": "SPEAKER_00",
        "text": text,
    }]
    return segments, 1


def _get_transcribe_func(transcription_model: str):
    """Retorna a função de transcrição do engine correto ou levanta HTTPException."""
    if transcription_model == "whisper":
        if not engine_registry.whisper_engine:
            raise HTTPException(
                status_code=503,
                detail="Whisper engine not loaded. Check HF_TOKEN configuration.",
            )
        return engine_registry.whisper_engine.transcribe_segment

    if transcription_model == "assemblyai":
        if not engine_registry.assemblyai_engine:
            raise HTTPException(
                status_code=503,
                detail="AssemblyAI engine not loaded. Check AAI_API_KEY configuration.",
            )
        return engine_registry.assemblyai_engine.transcribe_segment

    raise HTTPException(
        status_code=400,
        detail=f"Unknown transcription model: {transcription_model}",
    )
