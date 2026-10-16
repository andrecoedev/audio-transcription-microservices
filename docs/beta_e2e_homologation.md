# Homologação local da jornada Beta

## Decisão e limites

Observação em **15/10/2026**, base `origin/dev@80cb452` (PR #29 integrado).
**APROVADA COM LIMITAÇÕES para a jornada local simulada**, sujeita à revisão
independente, Security Gate e CI do PR. Não é aprovação de produção, abertura
da rodada, autenticação externa real ou qualidade de ASR/IA.

Nenhum P0/P1 de produto foi comprovado na jornada configurada abaixo. Os
findings P2/P3 permanecem explícitos. Providers reais, credenciais, grants de
pessoas reais, orçamento real e bancos persistentes não foram utilizados.

## Ambiente e persona

- React/Vite real, FastAPI real, PostgreSQL 16 e Redis 7 descartáveis, RQ real.
- Worker do walkthrough: `RecoveringWorker` existente, baseado em `rq.Worker`,
  com execução em processo filho e manutenção; nenhum modelo ML carregado.
  Integrações pytest comuns usam `SimpleWorker` para preservar os doubles em
  processo; o drill de crash usa o `RecoveringWorker` real com fork/SIGKILL.
  Nenhum desses testes alega validar CUDA.
- Banco exclusivo `usagi_beta_e2e_test`; projetos Compose sintéticos separados.
  A suíte pytest roda em outro banco descartável, pois suas fixtures truncam
  tabelas. Nunca executar contra `transcription_db` ou volume de desenvolvimento.
- Identidades `member`, `mobile`, `other`, `google` e admin sintético, somente
  `example.invalid`. Firebase SDK no navegador e verificação Admin SDK no
  servidor são fronteiras simuladas; resolução de User/FirebaseIdentity,
  ownership, grants e autorização do domínio continuam reais.
- Áudio WAV mono gerado em runtime: 40 segundos de silêncio decodificável.
  FFmpeg/conversão reais; as falas vêm de resposta sintética do adapter, não do
  áudio. Não calcular WER/CER/DER ou qualidade do modelo com essa fixture.
- Transcript PT-BR: decisão explícita sobre um guia; tarefa com responsável e
  prazo; tarefa sem ambos; pergunta em aberto. Nenhum dado pessoal real.
- ASR e inteligência simulados, sem SDK pago/rede externa. O navegador bloqueia
  origens externas. Worker/PG/Redis usam rede interna; não recebem `.env` real.

## Auditoria anterior às mudanças

| Etapa | Frontend/HTTP | Persistência real | Situação inicial |
|---|---|---|---|
| Cadastro e login | Login/Firebase → `/auth/firebase`; legado `/auth/login` | User, FirebaseIdentity, auditoria | Testes modulares; faltava jornada vertical |
| Grant | Central/endpoints `/admin/accounts/{id}/beta` | BetaAccessGrant, contador de vagas | API existente; exigia configuração explícita |
| Upload | Nova Transcrição → `/transcriptions/jobs` | Transcription, Job, Ownership, Reservation, ProviderCall | HTTP e Worker testados separadamente |
| Processamento | Polling; Redis/RQ; Worker | Estados e ID remoto | Integrações específicas existentes |
| Resultado | `/transcriptions/{id}` | Segmentos/metadados | Apresentação precisava de execução com API real |
| Reunião | `/meetings/{id}` e `/transcript` | Meeting, MeetingSpeaker | Criação atômica já implementada |
| Resumo/decisões | `/intelligence`, `/status`, `/result` | Revisões JSONB | Sem jornada única com upload anterior |
| Tarefas | `/actions` e sugestões | ActionItem, SuggestionReview | Revisão e origem já implementadas |
| Retorno | Sessão, histórico, reunião por URL | PostgreSQL, não React/RQ | Faltava prova conjunta de logout e reencontro |

## Fluxo executado

Guest explorou a demonstração, sem upload/inferência. Cadastro sintético por
e-mail criou User Free sem grant. O administrador encontrou a conta pela API e
concedeu acesso explicitamente. O usuário selecionou **Transcrição do Beta**,
enviou WAV, recarregou durante processamento, recebeu segmentos/falantes e
abriu a reunião por URL. Gerou resumo, consultou decisão, aceitou tarefa,
saiu, entrou novamente, reencontrou a reunião na lista e recarregou o resultado.

O grant da fixture inclui `transcription.platform` **e**
`intelligence.platform`, exclusivamente no ambiente sintético. A Central atual
concede apenas a primeira: isso não equivale a liberar resumos automaticamente.
O endpoint existente aceita capacidades explícitas; a política real de acesso
a resumos deve ser revisada pelo operador antes de convidar pessoas. Nenhuma
permissão real foi ampliada nesta entrega.

Plano observado na UI após uso: **Free com acesso Beta**, franquia da rodada
**10 horas**, consumo **40 s**, reservado **0 s**, disponível arredondado na UI
para **9 h 59 min**, sem renovação automática. Nenhum Starter automático.

## Matriz de execução

| Item | Resultado/evidência |
|---|---|
| Cadastro, login, logout e refresh | Browser → HTTP → identidade PostgreSQL; sem grant implícito |
| Google | Botão e identidade com double confiável; conta sem Beta; não houve popup/Google real |
| Sessão inválida | Token sintético rejeitado; conteúdo protegido bloqueado; novo login restaura acesso |
| Grant/revogação | HTTP real; 600 min; revogação impede novo upload e preserva resultado; vagas duráveis cobertas pela suíte financeira |
| Platform/BYOK | Platform explícito; chave própria ausente retorna indisponibilidade, sem fallback; BYOK/isolamento cobertos nas regressões existentes |
| Upload | Nome Unicode preservado; WAV na jornada; formatos gerados por FFmpeg na suíte existente: MP3, WAV/RF64, MPEG, MP4, M4A, FLAC, OGG e OPUS |
| Duração/tamanho | Validação e duração FFmpeg reais; testes existentes protegem limites e caps efetivos |
| Estados | HTTP queued → RQ → processing → completed; cenário de falha termina failed no PostgreSQL/RQ |
| Dupla execução | Uma submissão 202 no roteiro; geração repetida reutiliza revisão ativa; aceite de tarefa idempotente; uma Meeting/reserva/tentativa na jornada integrada |
| Timeout/ambiguidade | Provider fake recebe uma chamada; remote ID persistido; erro mantém hold e reentrada não repete submissão |
| Redis indisponível | Redis do walkthrough parado deliberadamente: resultado GET 200, nova submissão 503; restaurado depois |
| Restart/RQ efêmero | Registros RQ concluídos apagados; API/Worker recriados; resumo/tarefa/resultado continuam no banco e navegador. SIGKILL durante chamada aceita e reinício imediato também exercitados; detalhes abaixo |
| Resposta incompleta e retry | Testes existentes rejeitam JSON/schema/referência inválida, preservam revisão e verificam retry/recovery sem duplicar trabalho ativo |
| Longos | Fixture de apresentação com 200 segmentos/33 min 20 s; todos renderizados, scroll limitado; não é medição de processamento |
| Silêncio/vazio | Resultado sem segmentos é acessível e exportação textual fica desabilitada; falta mensagem de vazio mais explícita (P2) |
| Decisões | Persistem na revisão de inteligência; não existe editor independente de decisões |
| Tarefa | Aceite, responsável, prazo revisável, status, origem e exportação exercitados por HTTP/integração; aceite e retorno também no navegador |
| Ownership | A/B/admin: detalhe, ações, resumo e exportação privada negados com 404; listagem/privacidade cobertas pela suíte |
| Desktop/mobile | Jornada completa repetida com contas distintas em 1440×1000 e 390×844, incluindo upload, processamento, resumo, tarefa e retorno; sem overflow horizontal |

### Interrupção durante processamento

O teste `test_worker_killed_after_submission_and_restarted_never_duplicates_call`
executa HTTP, PostgreSQL e Redis reais, com `RecoveringWorker`/workhorse em
processos Linux. A resposta simulada fica deliberadamente bloqueada depois de
persistir o ID remoto. Nesse ponto, job RQ está `started`, heartbeat existe e o
PostgreSQL está `processing`. SIGKILL encerra somente o grupo de processos do
Worker descartável; um novo Worker inicia imediatamente e respeita o lease RQ
anterior, sem segunda chamada.

A expiração do lease é **acelerada explicitamente** pelo argumento `timestamp`
do cleanup real do RQ. Não medimos o tempo natural de detecção de abandono.
Após cleanup, RQ marca `failed`; o hook de manutenção de produção reconcilia o
PostgreSQL como `failed`, mantém reserva `unknown`/hold financeiro e ID remoto,
não cria Meeting e não enfileira outra chamada. Duas reconciliações posteriores
são idempotentes. Um recibo compartilhado entre processos comprova uma única
invocação do double. Isso não homologa crash CUDA nem recuperação de provider
real; trabalho ambíguo continua exigindo reconciliação operacional.

## Evidência/origem

| Capacidade | Classificação | Limite |
|---|---|---|
| Decisão → segmento/quote | EXISTE E FUNCIONA | Referência literal/âncora e conteúdo da revisão; sem editor de decisão |
| Tarefa sugerida → revisão/segmentos | EXISTE E FUNCIONA | Aceite preserva revisão e evidências imutáveis |
| Tarefa manual → evidência automática | NÃO EXISTE | Não inventada nesta Task |
| Decisão → tarefa por vínculo de domínio próprio | NÃO EXISTE | Ambas se relacionam à reunião; não há FK decisão/tarefa |
| Verdade semântica de provider real | NÃO VERIFICADA | Fixture deterministicamente sustentada; não homologa Gemini/Groq |

## Desktop e mobile

Screenshots sintéticas inspecionadas em [docs/design/beta-e2e](design/beta-e2e/).
O workspace mantém transcrição e resultado em áreas com scroll próprio; mobile
empilha essas áreas. A navegação administrativa agora tem divisor e título
separados, somente para admin. Não há seção vazia para Guest/usuário comum;
cada instância mobile/desktop possui identificador acessível único.

## Métricas qualitativas

Execução contínua limpa do roteiro principal: **17 s e 13 cliques instrumentados**.
Valores cumulativos aproximados:

| Etapa | Tempo | Cliques acumulados |
|---|---:|---:|
| Guest demo | 0 s | 0 |
| Cadastro sem grant | 1 s | 1 |
| Grant pela API + escolha explícita | 1 s | 2 |
| Upload e processamento | 2 s | 3 |
| Resultado após refresh | 8 s | 3 |
| Resumo persistido | 16 s | 4 |
| Decisão/tarefa aceita | 16 s | 7 |
| Logout/login/lista/retorno mobile | 17 s | 13 |

A repetição **inteiramente mobile**, desde Guest/cadastro até o retorno, também
levou 17 s/13 cliques, com resultado em 8 s e resumo em 16 s, zero erros JS e
zero respostas HTTP de erro. São duas execuções distintas, não uma projeção do
desktop sobre tela menor.

O contador não inclui digitação, seleção de arquivo, navegação direta por URL,
ações administrativas HTTP ou leitura humana. Doubles aguardam quatro segundos;
esses números não são ETA, benchmark de ASR nem expectativa comercial.

## Findings

### P0 e P1

Nenhum bloqueio P0/P1 comprovado na jornada **explicitamente configurada**.
Erros iniciais do harness (shape da busca, role tab, seletores encontrando texto
em ata recolhida e seed incompleto) foram corrigidos como testes, não mascarados
com mudanças de produto ou permissões.

### P2

- Convite pela Central libera apenas transcrição. Resumos exigem concessão
  adicional pelo endpoint existente e configuração de serviço autorizada;
  documentar isso no runbook de convites, sem ampliar permissões por padrão.
- Automático pode representar processamento local indisponível, embora o Beta
  plataforma esteja disponível. A escolha explícita funciona; evitar recomendar
  Automático ao convidado neste recorte. A UI não faz fallback para a plataforma.
- Silêncio/vazio deixa o corpo da transcrição sem explicação específica.
- Workspace mobile exige scroll da página e do painel; utilizável, mas a
  descoberta de tarefas abaixo das sugestões pode exigir orientação.
- Aceitar sugestão não converte automaticamente uma expressão literal de prazo
  em data. “Editar e aceitar” permite revisão; essa limitação evita inferência de
  datas não confiáveis e preserva a origem.

### P3

- Labels internos de falantes aparecem até o usuário renomeá-los.
- Aviso de bundle frontend >500 kB e deprecações de dependências já existentes.

## Reproduzir com segurança

Requisitos: Docker Linux, Node/dependências frontend e Playwright MCP.
Os comandos abaixo não leem `.env`, não montam credenciais e não usam volumes
do projeto de desenvolvimento. Não combinar este Compose com overlays reais.

```powershell
docker compose -f modules/backend/tests/homologation/compose.yaml build api
docker compose -f modules/backend/tests/homologation/compose.yaml run --rm migrate
docker compose -f modules/backend/tests/homologation/compose.yaml run --rm seed
docker compose -f modules/backend/tests/homologation/compose.yaml up -d api worker
cd modules/frontendv2
npm exec vite -- --config homologation/vite.config.js
```

Abrir `http://127.0.0.1:4180`; API somente loopback `:2029`. Executar no Playwright
MCP `browser_run_code_unsafe` com filename
`modules/frontendv2/homologation/journey.playwright.js`. O seed recusa banco não
vazio; o roteiro principal requer essa execução limpa. Para repetir sem apagar
dados, parar API/Worker anteriores e usar outro nome de projeto Compose
descartável em **todos** os comandos (`-p <nome>`).

Antes de executar o roteiro, definir o viewport Playwright em 1440×1000 para
desktop; repetir em 390×844 para a jornada mobile. O script escolhe personas
sintéticas distintas (`member`/`mobile`), cada uma inicialmente sem grant.

Na raiz, com o mesmo projeto isolado:

```powershell
docker compose -f modules/backend/tests/homologation/compose.yaml run --rm seed python -m tests.homologation.server erase-rq
docker compose -f modules/backend/tests/homologation/compose.yaml restart api worker
docker compose -f modules/backend/tests/homologation/compose.yaml run --rm seed python -m tests.homologation.server verify
docker compose -f modules/backend/tests/homologation/compose.yaml run --rm seed python -m tests.homologation.server presentation
```

Executar depois `modules/frontendv2/homologation/presentation.playwright.js` pelo
mesmo MCP. A preparação de apresentação é idempotente e produz somente dados
sintéticos da conta de teste. Não executar a suíte pytest no banco que deseja
preservar para o walkthrough: iniciar **outro projeto descartável**, aplicar
Alembic e executar o service `tests` (profile `test`).

Drill Redis reproduzível no mesmo runtime isolado, após a jornada desktop:

1. `docker compose -f modules/backend/tests/homologation/compose.yaml stop redis`
2. Executar via Playwright MCP o filename
   `modules/frontendv2/homologation/redis-outage.playwright.js`.
3. Restaurar Redis mesmo se a verificação falhar:
   `docker compose -f modules/backend/tests/homologation/compose.yaml start redis`.

Resultado observado: GET persistido **200**, nova submissão **503**, contagem
inalterada de transcrições. Não desabilitamos rate limit: sua falha segura é
uma das barreiras que impedem a criação do job nessa indisponibilidade.

Drill de crash e demais jornadas HTTP, em **outro projeto/banco descartável**:

```powershell
docker compose -p usagi-beta-e2e-tests -f modules/backend/tests/homologation/compose.yaml run --rm migrate
docker compose -p usagi-beta-e2e-tests -f modules/backend/tests/homologation/compose.yaml --profile test run --rm tests python -m pytest -q tests/integration/test_beta_journey_runtime.py
```

Não executar `seed` nesse projeto de pytest. O teste de crash exige Linux/fork;
no Windows nativo é explicitamente ignorado. A execução Docker Linux passou.

Os scripts Playwright registram somente paths/status/métricas qualitativas;
não registram headers ou payloads de autenticação. Tokens/secret do harness são
fixtures explícitas, não credenciais válidas fora desse runtime. A configuração
Vite de produção não importa os doubles; o bundle foi pesquisado e não contém
os marcadores de homologação.

## Testes e validações

- Backend: **644 passaram**, incluindo PostgreSQL/Redis/RQ, formatos FFmpeg,
  ownership, segurança, quotas, falhas, recovery e novos testes verticais.
- Frontend: **327 passaram**, lint/build passaram.
- Alembic upgrade/check, compilação Python, pip check, Compose oficial + overlay
  Firebase (validação silenciosa) e Compose de teste passaram.
- Nenhuma migration nova; preservadas as existentes, incluindo downgrade seguro
  exercitado pela suíte de integração.
- Playwright principal e apresentação: execução real contra HTTP/PG/RQ locais.
  No fluxo principal, zero erros JS e zero respostas HTTP de erro. Os negativos
  adicionais produzem 401/503 esperados, não erros inesperados da aplicação.
- CI, revisões independentes, Security Gate e Gitleaks: resultados finais no PR
  e Trello, não presumidos pela execução local.

As duas revisões independentes iniciais não encontraram P0/P1: Standards não
apontou violação; Spec identificou lacunas de cobertura mobile e reprodução de
falhas, fechadas pelos drills acima. O verificador funcional independente
confirmou apresentação/retorno, 200 segmentos, ownership A/B/admin, sidebar e
idempotência sobre resultado persistido, mas não repetiu cadastro, grant,
upload ou crash. A cobertura restante provém da execução do responsável e dos
testes, não é atribuída indevidamente ao verificador.

## Próxima ação

Após aprovação humana e integração deste PR, pode-se **planejar o deploy de
homologação e um smoke AssemblyAI curto**, mas não executá-los sem autorização
específica. Antes de convidados reais: revisar capacidades de resumos,
credenciais/serviços reais, saldo/exclusividade/tarifa/teto, domínio/auth,
backup/restore e operação no destino. Não basta esta simulação para abrir Beta.
