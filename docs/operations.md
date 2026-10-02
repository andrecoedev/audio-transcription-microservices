# Operação e persistência

## Runtime suportado

Execute da raiz, escolhendo explicitamente o projeto e o destino. Não use
containers/volumes desconhecidos nem consulte bancos de terceiros.

```powershell
docker compose -p usagidev --env-file modules/backend/.env up --build -d
docker compose -p usagidev --env-file modules/backend/.env -f compose.gpu.yaml up --build -d
```

Use um comando por vez. O segundo habilita GPU e CUDA/FP16; ambos usam a matriz
estável. Os arquivos da raiz incluem o Compose existente do backend, sem duplicar
seus serviços. O nome `usagidev` preserva a associação aos volumes deste projeto.
Configure secrets localmente a partir dos exemplos; não publique .env, saída
expandida de Compose/inspect nem credenciais em argumentos.

Serviços: frontend, postgres, redis, migrate (one-shot), api e worker. API/Worker aguardam
Alembic. PostgreSQL não publica porta host. Volumes de banco, uploads e cache de
modelos são separados. Dockerfiles suportados: API, Worker, test e frontend.
O frontend é servido pelo Nginx em localhost:3000, publicado apenas na interface
local por padrão. `/api` aponta para o serviço
`api` na rede Compose; a imagem React usa Node 22 somente na etapa de build.
API instala requirements.api.txt; Worker instala requirements.txt.
Windows executa o Worker no container Linux/WSL, pois o supervisor faz fork.

Para processos locais, migre PostgreSQL antes de iniciar:
```powershell
cd modules/backend
alembic upgrade head
python -m uvicorn src.main:app --host 0.0.0.0 --port 2020
# Em outro terminal Linux/WSL, no mesmo diretório:
python run_worker.py
```

## Schema e ownership

Schema nunca é criado no import/startup HTTP. Cadeia aplicada preservada:
20260909_0001 → 20260920_0002 → 20260930_0003 → 20261001_0004.
Use `alembic current`, `history`, `upgrade head` e `check`.
Downgrade é destrutivo e deve ser ensaiado apenas em banco sintético isolado.

Pooling PostgreSQL padrão por processo: 5 conexões + 5 overflow, checkout 30s,
recycle 1800s e pre_ping. Timestamps são UTC com timezone; JSONB preserva
segmentos/Unicode. FKs fazem cascade de jobs/ownership/reunião/revisões;
actor de audit usa SET NULL.

Novos owners usam users.id. Audite sem dados pessoais:
```powershell
python -m scripts.report_unresolved_ownership
```
Usuários locais podem ser criados por `python -m scripts.create_local_user`.
Export/erasure são CLIs internas `python -m scripts.manage_user_data`; conferem
owner, preservam audit sem identidade após erasure e protegem jobs ativos.
`--apply-exact` só é permitido depois de conferir backup/destino e correspondências
inequívocas com username único. Unknowns, conflitos e órfãos não são atribuídos
por aproximação. Não remover owner_sub enquanto houver registros não resolvidos.

## SQLite legado

O desenvolvimento identificado é usagidev / transcription_db /
usagidev_postgres_data. O SQLite legado contém um job processing sem áudio e
sem ownership. Ele **não foi importado nem atribuído ao administrador**.
Cópias byte-exact e lógicas com metadados ficam em database/backups, ignoradas.

Ferramentas permanentes:
- inspect_legacy_sqlite: inventário read-only sem transcript.
- backup_legacy_sqlite: backup com integridade/contagens/metadados; não sobrescreve destino.
- migrate_sqlite_to_postgres: import explícito para target vazio, FK-safe,
  transação única, preservação de IDs/JSON, validação e reset de sequences.

O importador continua testado, mas não constitui autorização para importar o
registro legado incompleto. Pare writers e apresente plano antes de migrar
qualquer dado real. Nunca copiar banco automaticamente.

## Backup e restore

Use pg_dump custom format e guarde o arquivo em diretório privado ignorado.
Credenciais ficam no ambiente do serviço, não no comando. Exemplo no projeto
identificado; adapte o usuário de conexão à configuração local:
```powershell
docker compose -p usagidev --env-file modules/backend/.env -f modules/backend/docker-compose.yml exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/transcription.dump'
docker compose -p usagidev --env-file modules/backend/.env -f modules/backend/docker-compose.yml cp postgres:/tmp/transcription.dump ./modules/backend/database/backups/transcription.dump
```

Confirme banco/volume de destino **isolado, novo e vazio** antes de pg_restore
com --no-owner --exit-on-error. Não usar --clean contra desenvolvimento ou
produção como drill. Compare revisão Alembic, contagens de todas as tabelas,
FKs/órfãos, ownership, JSONB e audit events. Dumps contêm dados privados.

tests/fixtures/p2c1_restore_seed.sql e p2c1_restore_verify.sql são fixtures
sintéticas permanentes do drill na revisão **20260920_0002**, com 4 FKs e
user_id legado NULL intencional. Não aplicá-las diretamente ao head atual.
Para esse drill, migre um target isolado até aquela revisão, carregue seed,
faça dump/restore em outro target vazio e rode verify com ON_ERROR_STOP=1.
Os testes PostgreSQL complementam com schema head, migrations e cascades.

## Retenção e reconciliação

Originais são apagados no finally do Worker depois de completed/failed; WAV
normalizado também é removido. Em queued/processing, input deve permanecer
disponível para recovery. Falha de filesystem é registrada sem path e retentada
pela reconciliação. Exclusão HTTP de job ativo retorna 409.

Padrões: uploads órfãos após 24h; retenção de transcrições/audit = 0 (indefinida).
Preview primeiro, verifique counts e só então use --apply:
```powershell
docker compose -p usagidev --env-file modules/backend/.env -f modules/backend/docker-compose.yml --profile maintenance run --rm maintenance
docker compose -p usagidev --env-file modules/backend/.env -f modules/backend/docker-compose.yml --profile maintenance run --rm maintenance python -m scripts.apply_retention
```
Rotinas são idempotentes, protegem jobs ativos e retornam non-zero em falhas
parciais. Não existe scheduler de exclusão instalado automaticamente.

## Smoke e diagnóstico

smoke_http_dev.py é sintético/public-only: login, sessão, upload, polling,
resultado e exclusão dos próprios dados. Opções --meeting, --diarization,
--intelligence, --require-segments e --drop-rq-job permitem verificar persistência.
USAGI_SMOKE_PASSWORD vai apenas no ambiente. Intelligence real é chamada cobrada:
não ativá-la repetidamente sem necessidade/autorização.
Outputs de review devem permanecer em diretório local ignorado.
O sample padrão é um tom sintético, não uma reunião: pode gerar segmentos vazios.
O smoke diferencia a rejeição de transcript vazio (422) da ausência de provider
para um transcript válido (503). Para verificar fala/diarização use uma fixture
pública real e --require-segments, sem interpretar o tom como teste de qualidade.

probe_simpleworker.py foi preservado como diagnóstico operacional **opcional**:
compara supervisor e SimpleWorker com stub/CUDA, timeout, heartbeat e crash.
Não é runtime nem teste permanente automatizado; usa fila sintética própria.
A advertência de banco vazio exige verificação pelo operador, não deve ser
tratada como uma trava automática. Não executá-lo em produção ou banco ocupado.

Health /health separa API, PostgreSQL, Redis e Worker. Ausência de registro
Worker não prova readiness dos modelos; logs/resultado de job validam processamento.
