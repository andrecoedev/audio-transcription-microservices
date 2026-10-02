# Arquitetura atual

## Fronteiras

React → FastAPI → PostgreSQL + Redis/RQ → Worker supervisionado → PostgreSQL.

A API cuida de HTTP, autenticação/autorização, validação/upload, criação de jobs,
consultas e health. Não importa nem inicializa Torch, CUDA, Whisper, Pyannote,
AssemblyAI ou Gemini. O frontend oficial está em `modules/frontendv2`.
O Streamlit em `modules/frontend` é uma interface alternativa legada, não
incluída no Compose suportado; foi preservado por ser um entrypoint independente.

PostgreSQL é a fonte de verdade. RQ contém coordenação/execução efêmera, não
transcripts nem resultados persistentes de Meeting Intelligence.

## Persistência e transações

- Transcription contém metadados, status, métricas e segmentos JSONB.
- TranscriptionJob contém opções, input path e estado durável da execução.
- TranscriptionOwnership liga a transcrição ao user_id; owner_sub é ponte legada.
- User contém identidade persistente e hash bcrypt, nunca senha em texto.
- Meeting referencia Transcription 1:1 com PK compartilhada: não duplica transcript.
- MeetingSpeaker contém ID estável e display name editável.
- MeetingIntelligence contém revisões/resultados JSONB e provenance.
- AuditEvent registra eventos mínimos, sem transcript, secrets ou IP.

Requests usam uma Session curta, rollback em falha e fechamento garantido.
Job/transcrição/owner são commitados antes do enqueue. Não há transação distribuída:
recovery reconcilia PostgreSQL/RQ. Claim condicional queued → processing impede
duas entregas de reivindicarem o mesmo job. Inferência ocorre sem transação aberta.
Conclusão grava segmentos ordenados, Meeting, speakers e completed atomicamente.

## Ciclo de vida RQ/CUDA

`run_worker.py` usa RecoveringWorker, derivado do Worker padrão do RQ.
O supervisor não carrega ML; cada work-horse filho inicializa engines depois do
fork e do claim. O filho descarta o pool SQL herdado com `dispose(close=False)`.
As instâncias são reutilizadas dentro do job, não entre filhos de jobs distintos.

Nomes únicos permitem reinício imediato. Heartbeat e timeout são supervisionados.
Falhas persistidas são levantadas como exceção sanitizada para RQ: PostgreSQL
failed não deve coexistir com RQ finished por erro absorvido silenciosamente.
Maintenance normal executa reconciliation a cada 60s; worker TTL é 75s.
Timeout padrão é 3600s, configurável, mínimo 60s.

Não republicar execução ainda started: pode haver inferência viva. Após kill,
a recuperação espera RQ reconhecer abandono; pode levar timeout + intervalo
de maintenance. Não há promessa de exactly-once para efeitos de providers externos.
Recarga de modelos por job é custo aceito para supervisão/CUDA segura.

## Compatibilidade

- Removidos os HTTP síncronos sem consumidores: /transcribe, /diarize,
  /whisper/transcribe_segment, /assemblyai/transcribe_segment.
- /system/gpu é resposta leve depreciada; Settings usa apenas /health e não
  apresenta o aviso dessa rota como diagnóstico real de GPU.
- GET /api-keys retorna booleans administrativos; POST retorna 410.
- /meeting-minutes continua ativo na Sidebar/React e mantém contrato legado
  de espera HTTP/resultado RQ. Não é substituído automaticamente por intelligence.
- SimpleWorker permanece apenas como harness de integração mockado e comparação
  operacional isolada. Não é entrypoint suportado.
- Não há asyncio.Queue, worker HTTP local ou nova fila/serviço.

Ver [operações](operations.md), [segurança](security.md) e
[reuniões/intelligence](meetings.md).
