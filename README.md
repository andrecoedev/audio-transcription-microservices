# USAGI Audio Transcription Microservices

![Audio Transcription Microservices](imgs/Inicial.png)

Transcrição de áudio/vídeo com Faster-Whisper ou AssemblyAI, diarização opcional
Pyannote, reuniões persistentes e Meeting Intelligence com Gemini.

## Arquitetura

React → FastAPI → PostgreSQL/Redis → RQ Worker supervisionado → PostgreSQL.

A API não inicializa ML/CUDA. Cada filho do Worker carrega engines depois do fork.
PostgreSQL contém resultados duráveis; RQ contém estado de execução efêmero.
Áudio usa a interface de Object Storage com adapter local privado; exclusões têm
retry durável no PostgreSQL. Veja o [mapa de dados e lifecycle](docs/cloud_data_architecture.md).
O frontend oficial é React; Streamlit permanece como interface legada alternativa.

Consumo técnico usa um ledger privado no PostgreSQL, com journal durável para
reconciliação e catálogo de preços vazio por padrão. Estimativas não são faturas;
BYOK e custos da plataforma permanecem separados. Veja [métricas e custos](docs/usage-metering.md).

## Iniciar desenvolvimento

Use um destino PostgreSQL pertencente ao projeto e configure secrets **localmente**.
Copie modules/backend/.env.example para .env e substitua placeholders.
Não publique .env, valores/fragmentos/hashes de chaves ou saída expandida de Compose.

Da raiz:
```powershell
docker compose -p usagidev --env-file modules/backend/.env up --build -d
```

GPU opcional, mantendo a mesma matriz estável:
```powershell
docker compose -p usagidev --env-file modules/backend/.env -f compose.gpu.yaml up --build -d
```

O Compose da raiz inicia frontend React, PostgreSQL, Redis, Alembic, API e Worker
em containers separados do mesmo projeto. `-p usagidev` mantém os volumes de
desenvolvimento já identificados; não troque o nome do projeto sem verificar
qual banco/volume será usado. O frontend abre em http://localhost:3000 e envia
requisições ao backend pelo proxy `/api`, sem receber segredos.
Não use volume/banco desconhecido. Windows roda Worker no container Linux/WSL.
Não atualizar Torch isoladamente nem instalar uma matriz CUDA alternativa para
contornar um erro sem validação conjunta.

Para desenvolver o frontend fora do Docker, opcionalmente:
```powershell
cd modules/frontendv2
npm ci
npm run dev
```
Use versão Node compatível com o campo engines do Vite instalado e o lockfile.
API: http://localhost:2020; docs: /docs; health: /health.
Frontend: http://localhost:3000.

Login usa identidade persistente e JWT. Providers são configurados somente no
Worker; API recebe flags públicas *_CONFIGURED. Configure
GEMINI_API_KEY_CONFIGURED separadamente da chave. Troca de credencial exige
recriar apenas o serviço que a recebe.
Firebase Google Sign-In é opcional e permanece desabilitado por padrão. Veja
[configuração e homologação de autenticação](docs/authentication.md).

A entrada pública compartilha a interface do app. Guest usa somente AssemblyAI,
com falantes nativos, habilitação explícita e orçamento cumulativo; fica desligado
por padrão e nunca usa fallback local. Veja [operação AssemblyAI](docs/assemblyai.md). Criar conta
não concede acesso às credenciais externas USAGI. Contas podem configurar BYOK e
preferências protegidas em Settings; veja [providers](docs/provider_preferences.md)
e [Guest, contas e limites](docs/guest_and_accounts.md).

## Fluxos oficiais

- POST /transcriptions/jobs → status → GET /transcriptions/{id}.
- GET /meetings e detalhe/transcript; título e display names editáveis.
- POST /meetings/{id}/intelligence → status → resultado persistido.
- Regeneração cria revisão e mantém a última concluída disponível.
- Exclusão protege jobs ativos; resultados privados exigem owner/admin.

Os endpoints síncronos antigos de processamento foram removidos.
/meeting-minutes ainda possui UI/consumidores e foi preservado por compatibilidade.
/system/gpu é resposta depreciada leve; POST /api-keys retorna 410.

## Documentação por assunto

- [Arquitetura e ciclo de jobs](docs/architecture.md)
- [Operação, banco, backup/restore e manutenção](docs/operations.md)
- [Segurança, privacidade e advisories](docs/security.md)
- [Contratos de reuniões e intelligence](docs/meetings.md)
- [Matriz ML, baselines e gates](docs/ml_validation.md)
- [Avaliação factual do Gemini e abstinência](docs/intelligence_validation.md)
- [Higiene e política de artefatos](docs/repository_hygiene.md)
- [Frontend](modules/frontendv2/README.md)
- [Fixtures públicas de benchmark](modules/backend/benchmarks/fixtures/README.md)

Relatórios cronológicos/JSONs brutos e candidata ML foram arquivados localmente
em .local-artifacts/archive; também existem no histórico Git anterior à limpeza.
Não são configuração suportada nem fixtures da suíte permanente.

## Validação

O [baseline de CI](docs/ci.md) valida PRs para `dev` com backend leve,
PostgreSQL/Redis isolados e frontend oficial. A documentação distingue esse
baseline da suíte Worker e da homologação real de modelos/providers.

A suíte completa deve rodar na imagem Worker estável com modelos/providers mockados
e PostgreSQL/Redis/RQ sintéticos isolados. A imagem leve de teste valida API/
persistência/integração, mas não instala dependências dos testes ML.
```powershell
docker compose -p usagitest --env-file modules/backend/.env -f modules/backend/docker-compose.yml --profile test run --rm test
```

Veja a operação para testes de migrations/restore exclusivamente em destinos
isolados e confirme o banco antes de qualquer comando destrutivo.

No frontend: npm run test, npm run lint, npm run build e npm audit.
Python: compileall; Git: git diff --check; Compose: config --quiet.
Não substitua homologação real por testes fake.

## Estado e limites

P3-A e P3-B/P3-B.2 foram validadas/homologadas localmente dentro dos critérios
registrados. Gemini real foi testado; grounding literal sozinho aceitou um prazo
incorreto, e abstinência foi corrigida e reavaliada sobre sources congelados.
Produção **não homologada**. Pyannote 4 **não promovido**.
Revisão humana continua necessária. A limpeza não implementa P3-C.

A matriz estável tem dívida de advisories Torch; PyJWT também tem apontamento
documentado. SDK Gemini legado e warnings permanecem. Não foram feitos upgrades
de versão para esconder resultados do scanner.

## Licença

[MIT](LICENSE.txt).
