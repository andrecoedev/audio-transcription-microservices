"""
Registro centralizado dos engines de ML.

Responsabilidades
-----------------
* Guardar as instâncias singleton dos engines (Pyannote, Whisper, AssemblyAI, Gemini).
* Definir os Protocols mínimos dos engines usados pelo processamento.
* Guardar instâncias reutilizadas exclusivamente pelo processo RQ worker.

Regra de uso
------------
SEMPRE acesse os engines via atributo do módulo:
    import engine_registry
    engine_registry.whisper_engine.transcribe_segment(...)

NUNCA use `from .engine_registry import whisper_engine` – isso cria uma cópia local
do valor None que não é atualizada quando o engine é carregado no startup.
"""

from typing import Optional, runtime_checkable, Protocol


# ---------------------------------------------------------------------------
# Protocols – contratos mínimos dos engines
# ---------------------------------------------------------------------------

@runtime_checkable
class TranscriptionEngineProtocol(Protocol):
    """Contrato mínimo que qualquer engine de transcrição deve satisfazer."""

    def transcribe_segment(
        self,
        audio_path: str,
        start: float = 0.0,
        end: Optional[float] = None,
    ) -> str:
        ...

    def get_device(self) -> str:
        ...


@runtime_checkable
class DiarizationEngineProtocol(Protocol):
    """Contrato mínimo que qualquer engine de diarização deve satisfazer."""

    def diarize(
        self,
        audio_path: str,
        min_duration: Optional[float] = None,
        silence_threshold: Optional[float] = None,
    ) -> dict:
        ...

    def get_device(self) -> str:
        ...


@runtime_checkable
class MeetingMinutesGeneratorProtocol(Protocol):
    """Contrato mínimo que qualquer gerador de atas deve satisfazer."""

    def generate_minutes(
        self,
        transcription: str,
        meeting_context: Optional[dict] = None,
    ) -> dict:
        ...


# ---------------------------------------------------------------------------
# Singletons dos engines (inicialmente None)
# ---------------------------------------------------------------------------

diarization_engine: Optional[DiarizationEngineProtocol] = None
whisper_engine: Optional[TranscriptionEngineProtocol] = None
assemblyai_engine: Optional[TranscriptionEngineProtocol] = None
meeting_minutes_generator: Optional[MeetingMinutesGeneratorProtocol] = None
