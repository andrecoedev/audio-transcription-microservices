# P1-A: fronteira entre API e processamento

## Auditoria anterior à mudança

| Arquivo | Importação/inicialização anterior | Usado por | Deve permanecer na API? |
| --- | --- | --- | --- |
| `src/main.py` | `DiarizationEngine`, `WhisperEngine`, `AssemblyAIEngine`, `MeetingMinutesGenerator`, registro global e utilitários CUDA | startup FastAPI | Não |
| `src/routers/transcribe.py` | registro de engines e conversão WAV; chamava diarização/transcrição | `/transcribe` e `/diarize` | Não; router removido |
| `src/routers/compat.py` | registro de engines; inferência direta por segmento | endpoints Whisper/AssemblyAI legados | Não; router removido |
| `src/routers/api_keys.py` | classes dos quatro engines; recarga dentro do request | configuração de chaves | Não; agora apenas persiste configuração |
| `src/routers/health.py` | `torch`, CUDA e registro de engines | `/health` e `/system/gpu` | Não; health agora usa banco/Redis/RQ |
| `src/routers/meeting_minutes.py` | registro do cliente Gemini; geração no request | atas do React | Não; agora enfileira no RQ |
| `src/services/transcription_engine.py` | Torch, Transformers, librosa, pydub e AssemblyAI; instancia Whisper | processamento | Sim, mas apenas no runtime do worker |
| `src/services/diarization_engine.py` | Torch, Pyannote, librosa e pydub; instancia pipeline | processamento | Sim, mas apenas no runtime do worker |
| `src/services/meeting_minutes.py` | cliente Google Generative AI | processamento de atas | Sim, mas apenas no runtime do worker |
| `src/utils/gpu_utils.py` | Torch/CUDA | configuração de device | Sim, mas apenas no startup do worker |
| `src/utils/audio.py` | pydub/FFmpeg | conversão de áudio | Sim, mas apenas no serviço de processamento do worker |

Imports indiretos relevantes antes da P1-A eram `main -> router -> service ->
torch/transformers/pyannote` e `main -> gpu_utils -> torch`. Consequentemente,
importar a aplicação web importava Torch, Transformers, Pyannote, librosa,
pydub e clientes externos; o startup instanciava os engines configurados e podia
inicializar CUDA, consumindo RAM/VRAM antes de qualquer job. Os endpoints que
exigiam isso eram os quatro endpoints síncronos, a recarga de chaves, o
diagnóstico GPU e a geração de atas.

## Fronteira atual

`src.main` registra somente HTTP, autenticação, upload, persistência, jobs,
consultas e health leve. `run_worker.py` chama
`initialize_worker_engines()` antes de iniciar o loop do RQ. A inicialização
usa imports tardios, preenche `engine_registry` somente quando uma instância
ainda não existe e cria um único `TranscriptionProcessingService` por processo.

O pipeline pesado está em
`src/services/transcription_processing_service.py`. Ele preserva o fluxo atual
baseado em arquivo/WAV temporário e coordena conversão, diarização,
transcrição e pós-processamento. O job RQ persiste as transições e o resultado.

## Endpoints legados

| Endpoint | Antes | Depois | Motivo |
| --- | --- | --- | --- |
| `POST /transcribe` | inferência síncrona na FastAPI | removido | sem consumidor React; Streamlit migrado para jobs |
| `POST /diarize` | Pyannote síncrono na FastAPI | removido | nenhum consumidor ativo |
| `POST /whisper/transcribe_segment` | Whisper síncrono na FastAPI | removido | nenhum consumidor ativo |
| `POST /assemblyai/transcribe_segment` | chamada síncrona na FastAPI | removido | nenhum consumidor ativo |
| `GET /system/gpu` | importava Torch/CUDA na API | depreciado; informa que o diagnóstico pertence ao worker | preserva uma resposta compatível sem ML |
| `POST /meeting-minutes/generate` | Gemini no request | contrato HTTP preservado; trabalho executado por job RQ | consumidor React ativo |

## Execução separada

API local (banco e Redis devem estar acessíveis):

```powershell
pip install -r requirements.api.txt
python -m uvicorn src.main:app --host 0.0.0.0 --port 2020
```

Worker local (requer as dependências completas e FFmpeg):

```powershell
pip install -r requirements.txt
python run_worker.py
```

Com containers, `Dockerfile.api` instala apenas `requirements.api.txt`, enquanto
`Dockerfile.worker` instala a stack completa. `docker-compose.yml` usa as duas
imagens e continua permitindo SQLite por configuração; PostgreSQL não se tornou
obrigatório.

## Compatibilidade e dívida mantida

- A transcrição oficial continua em `POST /transcriptions/jobs`, polling de
  status e `GET /transcriptions/{id}`.
- Chaves salvas pela API passam a valer após reiniciar o worker.
- Whisper continua sendo o engine Hugging Face existente; Faster-Whisper não
  foi introduzido.
- O processamento ainda usa arquivos e WAV temporário.
- O banco pode continuar SQLite; migração e Alembic não fazem parte desta fase.
