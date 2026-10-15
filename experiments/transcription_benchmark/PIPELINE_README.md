# Homologação do pipeline CPU: execução isolada

Este harness complementa o PR #18. Não habilita transcrição do Free, altera planos,
providers ou limites de produção. Não é deploy, nem prova de capacidade de VPS.
Card único: <https://trello.com/c/iDDtYreC>.

## Fronteiras e segurança

- `compose.cpu.yaml` é **outro projeto**, não um overlay da stack do produto.
  PostgreSQL `usagi_whisper_benchmark`, Redis e volumes novos; rede interna;
  nenhuma porta publicada, credencial real, socket Docker montado ou volume externo.
- Use somente `.env.benchmark` gerado pelo `prepare_pipeline.py`, nunca `.env`
  do produto. Secrets sintéticos são gerados em runtime e não são impressos.
  Linux usa 0600/0700; em Windows use o usuário do Docker Desktop e confira ACLs.
- Os dois flags de disponibilidade local são verdadeiros **apenas no teste** para
  atravessar admission. Isso não significa `LOCAL_TRANSCRIPTION_HOMOLOGATED` real.
  Uma conta sintética Free recebe concessão beta local explícita de 24h pelo endpoint
  administrativo. Nenhuma conta existente é promovida ou alterada.
- Imagens verificadas pelo operador; monte apenas src/alembic/run_worker/harness,
  cache autorizado e fixtures. Não monte a raiz com `.env` ou credenciais.
  Rede interna + offline + ausência de keys impedem chamadas pagas. Os scripts
  recusam outros bancos/Redis e configuração de credenciais externas.
- Resultados privados, áudio, hipóteses, traces e `.env.benchmark` ficam em
  `.local-artifacts/`, ignorada. Publicação aceita somente IDs públicos exatos e
  campos de métricas; não exporta transcript, path, nome, domínio/UID ou segredo.
- Não execute `down -v` genérico, `prune`, `flushall`, nem use `-p usagidev`.
  Parar somente os serviços do projeto gerado preserva seus volumes/evidências.

## Preparar Linux/VPS (ainda exige VPS real)

1. Checkout da branch/commit aprovado. Registrar CPU/modelo/vCPUs, compartilhada
   ou dedicada, RAM/limites cgroup, disco, kernel, imagens imutáveis, pacotes,
   workloads concorrentes e preço/contrato do servidor. Não usar RTF do Ryzen.
2. Construir/verificar imagens com os Dockerfiles API/Worker existentes; preservar
   matriz ML estável. O Worker ainda usa base CUDA mesmo em CPU: não requer GPU,
   mas ocupa disco. Não resolver upgrades de Torch isolados. Registrar versões
   efetivamente instaladas; manifests transitivos não são lock completo.
3. Obter **antes da medição** Systran/faster-whisper-small público, registrar
   revisão/hashes (`provenance.py`). Separar tempo e bytes de download do load.
   Pyannote somente cache de modelos já autorizado; não aceitar termos, gerar
   tokens ou baixar modelos gated implicitamente. Nunca copiar tokens do cache.
4. Preparar fixtures conforme `modules/backend/benchmarks/fixtures/README.md`;
   áudio/referência/RTTM ficam separados e privados quando necessário. Registrar
   licença/autorização, duração, hashes públicos, categoria, idioma, revisão humana.
   Não fabricar referência com Whisper; silêncio/TTS servem só para smoke.
5. Gerar configuração privada (exemplo Linux, imagens substituídas por IDs reais):

```sh
python experiments/transcription_benchmark/prepare_pipeline.py \
  --directory .local-artifacts/vps-run --models /private/authorized-models \
  --fixtures /private/authorized-fixtures \
  --api-image usagi-api:benchmark --worker-image usagi-worker:stable
docker compose --env-file .local-artifacts/vps-run/.env.benchmark \
  -f experiments/transcription_benchmark/compose.cpu.yaml config --quiet
docker compose --env-file .local-artifacts/vps-run/.env.benchmark \
  -f experiments/transcription_benchmark/compose.cpu.yaml up -d
docker compose --env-file .local-artifacts/vps-run/.env.benchmark \
  -f experiments/transcription_benchmark/compose.cpu.yaml run --rm --no-deps driver \
  --audio /fixtures/fleurs-ptbr-quality-1m.wav \
  --reference /fixtures/fleurs-ptbr-quality-1m.reference.txt \
  --fixture-id fleurs-quality --environment vps_cpu --repetitions 3 \
  --invalidate-terminal-rq --output /evidence/quality-1m.json
```

`--environment vps_cpu` é declaração do operador, não detecção/prova de servidor.
Em Docker Desktop use `local_cpu_container`. Registre a infraestrutura real à parte.
Não publicar paths pessoais ou credentials no relatório.

## O que se mede

`run_pipeline.py` autentica por HTTP, concede beta sintético se necessário, faz
upload real com nome neutro, consulta status/resultado/Meeting e examina somente
seus IDs no banco dedicado e RQ. Não reenvia upload nem repete inferência em erro.
Polling de 503 é limitado pelo deadline; timeout de observação não cancela o job.
Output exclusivo impede sobrescrever coortes antigas.

`worker_probe.py` instala wrappers somente no processo experimental. Executa o
`RecoveringWorker` existente, carrega modelos depois do fork e não muda fila,
claim, authorization, recovery, ledger ou contratos HTTP. Observação de arquivos
que falha não transforma resultado persistido em falha de processamento.

| Métrica | Fronteira / limitação |
|---|---|
| upload_seconds | Roundtrip do POST, inclui validação, objeto, banco, reserva e enqueue; **não** transferência pura |
| queue_seconds | RQ `enqueued_at → started_at`, clocks do servidor; null se ausente/reverso |
| durable_admission_to_claim_seconds | Banco `created_at → started_at`; transação pode começar antes do upload; não é fila pura |
| engine_initialization_seconds | Import/init dos engines, inclui Torch e load, não somente leitura de pesos |
| conversion_seconds | Normalização FFmpeg do `ProcessingResult` |
| asr_seconds | Transcrição e decode dos segmentos; sem inventar tempo exclusivo de kernel |
| diarization_seconds | Pyannote do `ProcessingResult`; zero quando desativado |
| persistence_seconds | `_persist_completed_job`, transação resultado + Meeting + estados; null na falha anterior |
| worker_seconds | Claim, materialização, modelos, processamento, persistência, ledger e cleanup; não somar a suas partes |
| end_to_end_seconds | Antes do POST → resultado + transcript de Meeting HTTP; inclui polling |
| RTF | Worker/duração e HTTP/duração separados; não usar só ASR como RTF da jornada |
| RAM / CPU | RSS pico amostrado 100ms da árvore do work horse / CPU-segundos; pode perder transientes |
| temporary_bytes | WAV normalizado observado pelo serviço; **não** pico de disco da stack ou spool HTTP |
| Docker stats | Escopo container, memória/caches diferente de RSS; CSV pode ser parcial em recriação de containers |
| ledger | Eventos P5-05 existentes, por ID de recurso; duração técnica não é unidade faturável externa |

Configuração real: CPU/INT8, modelo small, idioma pt, beam 1, VAD desligado,
condition_on_previous_text=false, chunks 300s, threads 2 por Worker no harness.
Defaults beam/VAD/contexto/chunks do produto permanecem inalterados. CPU/threads
são configurações **experimentais explícitas**, não defaults comerciais.

Todo job RQ tem novo work horse e recarrega modelos. Não existe modelo residente
entre jobs nesta estratégia: repetições posteriores são **cache de disco quente**,
não warm inference residente. O benchmark `run.py` pode medir residência isolada,
mas não representa o Worker de produto. Não limpar cache do OS ou baixar modelo
em cada repetição para fabricar cold starts.

## Concorrência e recursos

Executar primeiro 1 Worker. `--concurrency 2/3` controla submissões HTTP, não
quantidade de work horses. Para execução simultânea escalar explicitamente Worker
depois de medir headroom, repartindo orçamento de RAM. No ensaio local: 6400m ×1,
2800m ×2, 1800m ×3, 2 CPUs/2 threads por réplica. CPU total também aumenta (2/4/6).
Não extrapolar ganho como comparação com CPU total fixo de uma VPS.

Exemplo: `BENCHMARK_WORKER_MEMORY=2800m docker compose ... up -d --scale worker=2 worker`.
Manter configurações registradas e coortes separadas. Não iniciar pytest/build ou
outra carga durante a homologação final; desenvolvimento local teve cargas
compartilhadas e não fornece capacity planning de produção.

```sh
python experiments/transcription_benchmark/monitor_stack.py \
  --project usagi-whisper-bench-XXXXXXXX --seconds 300 \
  --output .local-artifacts/vps-run/evidence/stack.csv
```

Usar o nome hexadecimal realmente gerado. Encerrar amostragem antes de recriar
containers. Amostras parciais não são prova de ausência de OOM ou utilização máxima.

## Diarização, qualidade e falhas

Para Pyannote offline: `BENCHMARK_OFFLINE_DIARIZATION_MARKER=offline-cache-only`
antes de recriar Worker; o marcador não é token, rede continua bloqueada. Ambos
`HF_HUB_CACHE` e `PYANNOTE_CACHE` apontam para o cache montado. Sem cache completo,
registrar falha; não baixar, trocar modelo ou ignorar detecção de falantes.

WER/CER usam `metrics.py` com referência humana: NFC, minúsculas, tokens sem
pontuação, hífens preservados, CER sem espaços. Isso não valida pontuação,
entidades/números/negações ou speaker correto: revisão humana continua necessária.
Ausência de referência = null. DER exige RTTM humano compatível e protocolo
collar 0.25s, overlap incluído (`diarization.py`/benchmarks existentes). Contagem
de speakers e speaker agreement não são DER. FLEURS alternado não é reunião real.

`prepare_failure_fixtures.py` gera inválido, RIFF truncado e silêncio digital.
`run_pipeline.py` registra HTTP, PostgreSQL, RQ, reserva e tentativas por caso.
Para timeout normal, variar **somente** `BENCHMARK_JOB_TIMEOUT_SECONDS` no ambiente
descartável (mínimo global 60s), restaurando depois; nunca encerrar jobs de usuários reais. Cancelamento,
kill/recovery, Redis/storage ausentes e OOM precisam de protocolo controlado,
amostragem completa e conciliação de reservas unknown; suíte de regressão não
substitui ensaio de falha com inferência no servidor final.

`probe_faults.py` prepara timeout **por job sintético** de 3s ou remove somente o
objeto do próprio upload recém-admitido, com todos os Workers do benchmark parados.
Requer imagem Worker (recovery tem dependências ausentes da imagem API), fixture
readonly e senha sintética via variável de processo, nunca argumento com o valor.
Depois iniciar Worker, aguardar terminal e executar `inspect --transcription-id`
com o ID emitido. Preservar `unknown`; não repetir POST se a mutação falhar.
`redis-unavailable` funciona na imagem API, sem credencial: com Worker parado,
parar somente Redis da stack dedicada, confirmar 503 pré-parsing/sem novo job e
restaurar os serviços imediatamente. Não apagar contadores para contornar 429.

`compare_decode_policy.py` diagnostica diferença entre políticas com mesmos PCM e
pesos; uma execução por política não é benchmark estatístico nem ajuste automático
para melhorar uma fixture. Não promover parâmetros a partir dela.

## Gates para VPS/Beta

Preparação local não aprova Beta. Faltam VPS real, dataset natural PT-BR autorizado
com revisão humana (limpa/reunião/ruído/sotaques/profissional/overlap), critérios
de qualidade/erros críticos e fila acordados, 3 repetições de cold/cache quente,
concorrência com CPU/RAM total fixos, 5/15–30min, falhas reais e preços reais de
VPS/storage/backup/egress. O custo por hora deve incluir ociosidade e uso observado.

Reutilizar `cost_model.py` com Decimal e perfil **medido nessa VPS**, não do Ryzen.
Sem preço/RTF do servidor o custo/capacidade permanece desconhecido. Sem autorização
de custo não chamar AssemblyAI; sem fallback silencioso. Não alterar franquias,
timeouts ou limites comerciais automaticamente. Pyannote 4 permanece não promovido.
