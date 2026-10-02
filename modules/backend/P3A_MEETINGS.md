# P3-A — reunião persistente

## Auditoria anterior à alteração de schema

| Estado atual | Persistência/contrato |
|---|---|
| `Transcription` | Upload, modelo, status, duração, JSONB `segments` com `start`, `end`, `speaker`, `text`, contagem de speakers/palavras e tempo de processamento. Já contém o transcript completo. |
| `TranscriptionJob` | Um job por transcrição, caminho do input, opções, status e timestamps. O Worker grava resultado e `completed` no mesmo commit. |
| `TranscriptionOwnership` | Um owner por transcrição, `user_id` para dados novos e `owner_sub` como ponte legada. A autorização existente filtra pelo owner; admin tem acesso global. |
| RQ | Fila e estado de execução efêmeros. O retorno do job contém apenas status, `transcription_id`, tempo e palavras; não contém transcript. |
| API | `POST /transcriptions/jobs`, consulta de status/resultado, lista e exclusão; `/meeting-minutes` é outro fluxo e não é a entidade persistente solicitada. |
| React | Cria job, consulta `/transcriptions/jobs/{id}/status` e `/transcriptions/{id}`; lista e detalhes usam os endpoints de transcrição. |

Decisão: `Meeting` referencia 1:1 a `Transcription` com chave primária compartilhada.
Owner, status, duração, segmentos e métricas continuam na transcrição existente;
a reunião os projeta na API, sem copiar o transcript. `Meeting` guarda apenas
título, idioma e data de criação próprios. `MeetingSpeaker` guarda identificador
estável na reunião e nome editável. Os segmentos permanecem no JSONB da
transcrição, ordenados deterministicamente e expostos com índice `order`.

## Contrato e operação

- `Meeting.id` é a PK e FK para `Transcription.id`. A reunião é criada apenas
  após processamento bem-sucedido. `TranscriptionOwnership` é a fonte única de
  ownership; `TranscriptionJob` mantém os dados de execução. Remover a
  transcrição remove em cascata a reunião e os speakers.
- O Worker ordena os segmentos por início, fim e posição original, grava
  `order` no JSONB e, no mesmo commit, grava a reunião, os IDs estáveis dos
  speakers, status `completed` do job e eventos de auditoria. Em erro,
  rollback e marcação `failed` usam a transação de falha existente.
- `GET /meetings` lista somente metadados do owner; `GET /meetings/{id}`
  inclui speakers e métricas; `GET /meetings/{id}/transcript` lê o JSONB
  persistido, não consulta RQ. `PATCH /meetings/{id}` edita título e
  `PATCH /meetings/{id}/speakers/{speaker_id}` edita display name. `DELETE`
  remove reunião e transcrição conjuntamente; jobs ativos retornam 409.
- A migration `20260930_0003` cria `meetings`/`meeting_speakers` e faz
  backfill dos resultados `completed` já existentes, sem duplicar o texto.
  Para homologação, usar PostgreSQL de teste isolado para
  `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head` e
  `alembic check`. Em banco de desenvolvimento com dados, fazer backup antes
  do upgrade. Nunca executar downgrade no banco com dados reais.
- A integração não requer alterar nem carregar a matriz candidata Pyannote 4.

O smoke de desenvolvimento pode usar `scripts/smoke_http_dev.py --meeting
--diarization --require-segments --drop-rq-job` no container Worker estável,
com `USAGI_SMOKE_PASSWORD` fornecida apenas no ambiente do processo. A opção
`--drop-rq-job` exclui exclusivamente o RQ job acabado que o próprio smoke
criou e verifica que os endpoints de reunião continuam a responder. Executar
somente em stack de desenvolvimento/teste e após backup/migration do banco.

## Validação local (2026-09-30)

- O projeto `p3atest` foi criado com volume PostgreSQL próprio
  `p3atest_postgres_data`; a migration passou por upgrade, downgrade,
  upgrade e `alembic check` sem diferenças. Um resultado `completed`
  sintético foi inserido na revisão anterior e o novo upgrade criou 1
  reunião e 1 speaker, mantendo 1 segmento e o owner inequívoco; os dados
  sintéticos foram removidos depois. A suíte completa na imagem
  Worker da matriz ML estável passou: **116 testes**, incluindo integração
  PostgreSQL/Redis/RQ. A imagem de teste API passou 111 testes; a coleta da
  suíte completa nela não é suportada porque, por desenho, não instala
  `librosa`/Pyannote. Isso não foi contado como teste aprovado.
- Antes de tocar no banco de desenvolvimento, foi confirmado que
  `usagidev-postgres-1` usa exclusivamente `usagidev_postgres_data`, com
  revisão `20260920_0002`, 1 usuário e 0 transcrições/jobs/owners. O backup
  `database/backups/usagidev-pre-p3a-20260930.dump` foi criado com `pg_dump`
  custom format e restaurado com `pg_restore` no volume novo
  `p3abackup_postgres_data`; revisão e contagens conferiram. Nenhum banco de
  terceiros ou SQLite legado foi consultado ou alterado.
- API e Worker foram parados sem jobs ativos; `usagidev` recebeu apenas o
  upgrade `20260920_0002 → 20260930_0003`. A API/Worker voltaram saudáveis,
  `alembic check` passou e importar `src.main` não carregou módulos ML.
- Smoke HTTP real na matriz estável com overlay GPU (`torch.cuda.is_available`
  verdadeiro) e fixture pública PT-BR de dois falantes: login 200, sessão
  200, upload/job 202, estados `queued → processing → completed`, resultado
  200 com 12 segmentos e 2 speakers, reunião e transcript 200. Após excluir
  somente o RQ job do próprio smoke, ambos os endpoints de reunião seguiram
  respondendo 200; renomeação 200, exclusão 200 e leitura posterior 404.
  O banco terminou com 0 transcrições/jobs/reuniões/speakers e 1 usuário.
- Frontend: lint e build passaram, 11 testes passaram. Compilação Python,
  `git diff --check` e `docker compose config --quiet` passaram. Warnings
  de depreciação de Starlette/httpx, RQ e Matplotlib permanecem; não houve
  walkthrough visual no navegador. Esta é validação local de desenvolvimento,
  **não homologação de produção** nem benchmark de qualidade WER/DER.
