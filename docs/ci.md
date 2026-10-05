# CI baseline

`.github/workflows/ci.yml` valida PRs para `dev` e o código integrado em pushes
para `dev`. Não faz deploy, não executa em `main` e não configura proteção de
branch. Os checks são **Backend baseline** e **Frontend baseline**.

## Backend

Python 3.11, igual ao runtime API/test; instalação por
`modules/backend/requirements.test.txt`, que inclui o manifest da API e o SDK
AssemblyAI já utilizado pelo Worker. Não instala Torch, CUDA ou modelos.

Em `modules/backend`, com PostgreSQL 16 e Redis 7 **descartáveis**:

```sh
python -m pip install -r requirements.test.txt
python -m pip check
python -m compileall -q src scripts run_worker.py
python -m alembic upgrade head
python -m alembic check
python -m pytest -q --ignore=tests/test_diarization_filter.py
```

`DATABASE_URL` aponta para o banco vazio usado pelo Alembic;
`P2A_TEST_DATABASE_URL` aponta para o mesmo banco e habilita os testes
PostgreSQL. `REDIS_URL` habilita integração RQ. `APP_ENV=test` e `AUTH_MODE=strict`
mantêm a configuração de teste. O conftest gera a chave JWT em runtime e usa
SQLite em memória para testes unitários. Não são necessárias credenciais reais.

**Nunca apontar esses testes para desenvolvimento persistente ou produção.**
As fixtures PostgreSQL executam TRUNCATE e testes de migration exercitam
downgrade. Os services Actions têm dados sintéticos e existem apenas no runner.
Não reutilizar a senha sintética do service em ambientes reais.

Não definir os dois URLs deixa testes de integração ignorados ou sem schema;
isso não representa a validação completa deste baseline.

## Frontend

O frontend oficial é `modules/frontendv2`, confirmado pelo Compose e pelo
`Dockerfile.web` (Node 22). O lockfile usado é o desse diretório, não o da raiz.

```sh
cd modules/frontendv2
npm ci
npm run lint
npm run test
npm run build
```

Vitest usa jsdom e serviços mockados; não precisa de API, Firebase real ou
providers pagos. O build baseline não recebe `.env`, chaves BYOK ou credenciais
administrativas. Os registros de pacotes são necessários para instalar.

## Categorias fora do CI leve

| Categoria | Tratamento |
| --- | --- |
| `tests/test_diarization_filter.py` (5 testes) | Imports globais de librosa/Torch/Pyannote exigem a matriz Worker. Preservado, não convertido em skip. Executar na imagem Worker estável com engines mockados, sem baixar modelos. |
| Demais testes de áudio/Whisper/AssemblyAI/intelligence/Firebase | Incluídos no baseline com modelos/providers/tokens mockados; não exigem GPU ou APIs reais. |
| Benchmarks em `modules/backend/benchmarks/` | Homologação separada com fixtures públicas, referências e matriz ML controlada; não são testes pytest. |
| Inferência CUDA, WER/CER/DER e estabilidade | Gate de release ML em GPU autorizada; fora de runners CI CPU. Não promover Pyannote 4 por este baseline. |
| Smoke HTTP com providers reais / Google login real | Homologação local ou staging explicitamente configurado, com orçamento e autorização. Nunca usar secrets reais de produção em PR. |
| Backup/restore e probes operacionais | Procedimentos em destinos isolados conforme `operations.md`; não rodar probes em volumes desconhecidos. |

O CI leve não substitui a suíte Worker nem homologação ML, factual ou de
produção. Não ocultar falhas da suíte completa modificando assertions.

## Segurança e resultado

Actions oficiais fixadas por SHA; token `contents: read`, checkout sem
persistência de credenciais. Sem `pull_request_target`, deploy, tokens reais ou
permissões de escrita. Services não recebem dados ou volumes do projeto.

Os jobs têm timeout de 15 minutos e execuções obsoletas da mesma referência são
canceladas. Cancelamento não conta como CI aprovado: conferir os runs e jobs
do HEAD atual do PR. Após cada push, o resultado anterior deixa de valer.

Somente propor required checks após observar estabilidade real; configurar
branch protection é uma decisão separada do mantenedor.
