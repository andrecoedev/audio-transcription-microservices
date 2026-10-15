# Operação da beta fechada de AssemblyAI

## Escopo e estado

Esta rodada concede acesso a no máximo cinco contas convidadas, por concessão
explícita do administrador. Cada concessão usa `transcription.platform` e o
`round_id` configurado; a duração é cumulativa por usuário e por rodada:
36.000 segundos (600 minutos) por usuário. Não há renovação mensal, reset de
saldo nem renovação automática. A concessão também tem validade administrativa
(`expires_at`) e pode ser revogada.

A plataforma fixa `Universal-3.5 Pro` (`universal-3-5-pro`) com diarização de
falantes habilitada. A chave é exclusiva para a USAGI, configurada apenas no
Worker. Não há fallback automático para Whisper ou outra credencial se a chamada
falhar. BYOK não usa essa franquia nem o orçamento global da plataforma. O
default global `DEFAULT_TRANSCRIPTION_MODEL=whisper` permanece inalterado.

O código e este runbook não representam homologação de produção nem autorização
para uso pago do provider. A entrega ainda está em validação. Não use conta,
áudio ou credenciais de terceiros para validar este fluxo.

## Configuração

API e Worker precisam receber a mesma política pelo anchor
`x-assemblyai-policy` em `modules/backend/docker-compose.yml`. A chave real
`AAI_API_KEY` permanece somente no Worker; a API recebe apenas o indicador
`AAI_API_KEY_CONFIGURED`. Nunca publique ou registre o valor da chave. Os campos
`AAI_PLATFORM_KEY_REFERENCE` e `AAI_PLATFORM_PROJECT_REFERENCE` são rótulos
operacionais não secretos, não são chaves, IDs pessoais nem valores copiados do
segredo. `AAI_PLATFORM_PRICE_VERSION` também é um identificador revisado, por
exemplo uma versão de catálogo neutra.

Os campos da política são:

| Variável | Default seguro | Função |
|---|---:|---|
| `AAI_PLATFORM_ENABLED` | `false` | Permite admissões com a chave da plataforma |
| `AAI_PLATFORM_BUDGET_CENTS` | `0` | Teto cumulativo configurado em centavos de USD |
| `AAI_PLATFORM_ALERT_CENTS` | `1200` | Limiar cumulativo de revisão/alerta |
| `AAI_PLATFORM_MODEL` | `universal-3-5-pro` | Modelo preso para chamadas da plataforma |
| `AAI_PLATFORM_HOURLY_USD` | `0` | Tarifa operacional por hora, revisada pelo operador |
| `AAI_PLATFORM_PRICE_VERSION` | vazio | Versão imutável da tarifa registrada |
| `AAI_PLATFORM_KEY_REFERENCE` | vazio | Rótulo não secreto da chave dedicada |
| `AAI_PLATFORM_PROJECT_REFERENCE` | vazio | Rótulo não secreto do projeto dedicado |
| `AAI_BALANCE_REVIEW_HOURS` | `24` | Validade máxima da última conferência do saldo |
| `AAI_BETA_ROUND_ID` | vazio | Identificador da rodada exigido na concessão |
| `AAI_BETA_ROUND_SECONDS` | `36000` | Franquia total em segundos por conta na rodada |
| `AAI_BETA_MAX_USERS` | `5` | Máximo de contas distintas convidadas na rodada (até cinco) |
| `AAI_PLATFORM_MAX_PROCESSING` | `1` | Chamadas simultâneas autorizadas globalmente |
| `AAI_PLATFORM_MAX_QUEUED` | `10` | Reservas aguardando execução globalmente |
| `AAI_MAX_AUDIO_SECONDS` | `600` | Limite por arquivo, inclusive para BYOK |

Timeouts `AAI_TIMEOUT_SECONDS`, `AAI_HTTP_TIMEOUT_SECONDS` e
`AAI_POLL_INTERVAL_SECONDS` também devem permanecer iguais entre API e Worker.
Os defaults de segurança (`enabled=false`, teto e tarifa zero, rodada e
referências vazias) não habilitam uso. Não coloque a chave real no `.env` de
exemplo, no Compose da API, no frontend, em logs ou na resposta de endpoints.

Para uma futura abertura, a política aprovada é
`AAI_PLATFORM_BUDGET_CENTS=1500`, `AAI_PLATFORM_ALERT_CENTS=1200` e
`AAI_PLATFORM_HOURLY_USD=0.23`, com `AAI_PLATFORM_PRICE_VERSION` preenchida após
revisão da fonte de preço. Essa aprovação não ativa a integração, não autoriza
smokes nem altera os defaults seguros desta branch. O preço público consultado é US$0,21/h
para Universal-3.5 Pro mais US$0,02/h para diarização; 50 horas agregadas dariam
uma estimativa teórica de US$11,50. Essa conta é apenas estimativa, sujeita a
preço/contrato vigente, e não prova gasto real. Confira
[AssemblyAI Pricing](https://www.assemblyai.com/pricing) antes de definir a
tarifa e a versão.

Além destes campos, a admissão exige `PLAN_POLICIES_JSON` explícita e válida
incluindo a política `beta` com limites positivos. A recomendação operacional
da rodada é `max_queued_jobs=2` e `max_processing_jobs=1` por usuário; os limites
globais do provider são os campos acima. Defaults de processo e fila são um
worker e dez chamadas aguardando. O menor limite aplicável prevalece.

Após revisar e alterar configurações, recrie API e Worker juntos. Alterar env
não aumenta o teto já persistido no banco nem zera o gasto/reservas registrados.
As proteções são cumulativas: configuração atual e orçamento armazenado no DB.
Não imprima Compose expandido, pois ele pode incluir credenciais.

## Preparação manual antes de abrir a rodada

1. Confirme que o projeto/chave da conta AssemblyAI é de uso exclusivo da
   USAGI. A exclusividade deve continuar válida durante a rodada. Se for perdida,
   suspenda admissões e retire o acesso até uma nova conferência operacional.
2. Não altere saldo, habilite autopay nem faça qualquer compra nesta etapa.
   Apenas confira no painel o saldo disponível existente. Não existe API
   automática de leitura de saldo nem garantia de cobrança limitada pelo hard stop.
3. Registre a conferência inicial, data/hora e os rótulos não secretos da
   chave/projeto dedicados. Não confunda créditos externos com orçamento a
   consumir; não há dependência de consulta automática ou de hard stop externo.
4. Configure no ambiente a rodada, o modelo, a tarifa/versão e rótulos não
   secretos correspondentes. Mantenha `AAI_PLATFORM_ENABLED=false` e os demais
   defaults seguros; esta etapa não ativa nem autoriza chamadas de smoke.
5. Para registrar a fotografia do saldo, primeiro pause novas admissões e drene
   a fila e os processamentos. Só prossiga sem operações pendentes; a rota também
   rejeita a confirmação exclusiva quando houver chamadas pendentes. Use
   `POST /admin/providers/assemblyai/balance-check` com saldo já existente
   conferido, `checked_at` com timezone, os mesmos rótulos configurados e
   `exclusive: true`. O valor vem do painel e não deve ser inventado ou copiado
   para documentação.
   Em orçamento legado ainda sem rodada, esta confirmação explícita vincula a
   rodada inicial sem apagar autorizações antigas. Resolva antes as pendências
   históricas; preços antigos desconhecidos continuam desconhecidos. Ajuste
   teto e alerta pela rota administrativa, sem reescrever o acumulado.
6. Uma futura ativação requer revisão do hard stop/alerta e saldo conferido,
   configuração, migration e homologação operacional pelo processo de release.
   Este runbook não ativa o serviço nem autoriza tráfego pago.

O registro da conferência é uma fotografia manual. Ela não limita outras
aplicações na conta externa. A validade padrão é 24 horas, configurável por
`AAI_BALANCE_REVIEW_HOURS`; após expirar, a admissão falha fechada até nova
conferência. Se `exclusive` for falso, a rota desmarca a exclusividade e novas
admissões ficam bloqueadas. O saldo externo não é atualizado automaticamente.

## Limites e garantias

O hard stop impede que a USAGI autorize novas chamadas além do menor destes
valores: teto operacional persistido, teto configurado, saldo disponível
manualmente conferido somado ao baseline autorizado. Reservas são cumulativas,
arredondadas para cima e não se renovam por mês. Atingir o alerta exige revisão
humana antes de qualquer aumento. Para o beta, aumentos são decisões manuais e
auditadas, nunca automáticos.

O hard stop é autorização interna, não garantia de saldo externo, limite de
fatura ou proteção contra consumo por outras integrações. Sem exclusividade da
chave/conta e reconciliação periódica com o painel, não se pode afirmar que o
saldo observado cobre as chamadas da USAGI. Em dúvida, desative
`AAI_PLATFORM_ENABLED` e mantenha a rodada suspensa.

Mudanças em modelo ou preço exigem parar a admissão, drenar trabalhos da fila,
confirmar que não há chamadas pendentes antes de capturar qualquer snapshot, e
então configurar uma nova versão de tarifa e executar outra conferência de saldo.
Trabalhos já reservados com
modelo/versão incompatíveis são negados, não reprecificados. O snapshot grava a
tarifa configurada em `UsagePrice` para aquele modelo e versão; qualquer valor
estimado segue sendo estimativa, não fatura.

## Operação administrativa e reconciliação

As rotas ficam sob `/admin/providers/assemblyai` e exigem administrador
autenticado:

| Método e rota | Campos principais | Efeito |
|---|---|---|
| `POST /balance-check` | `available_usd`, `checked_at`, `key_reference`, `project_reference`, `exclusive` | Registra a conferência manual e o baseline; com `exclusive=true`, requer zero chamadas pendentes |
| `PATCH /budget` | `hard_stop_usd`, `alert_usd`, `reason="manual_review"` | Ajusta teto/alerta e audita. Aumento exige saldo válido suficiente e nunca pode ficar abaixo de reservas |
| `GET /operations` | sem corpo | Mostra rodada, teto, reservado, estimativa tentada, alerta, estado da conferência, rótulos e contagens; nunca a chave real |
| `POST /calls/{call_id}/reconcile` | `decision`, `reason="dashboard_verified"`, dados comprovados aplicáveis | Concilia uma tentativa ambígua usando evidência do painel |

Não compartilhe nem arquive resposta de operação que inclua saldo observado
fora do canal operacional autorizado. Campos `key_reference` e
`project_reference` são rótulos sintéticos e não devem conter credenciais,
identificadores pessoais nem a própria chave.

Falhas após uma tentativa externa podem deixar uma chamada `unknown`. Não repita
a submissão nem libere a reserva por suposição. Primeiro confirme estado
terminal no painel do provider e que o job não está ativo no banco ou RQ. A rota
de reconciliação consulta a fila e recusa jobs ativos; indisponibilidade da fila
também bloqueia a ação. Até a conciliação manual com evidência terminal, a reserva
e o slot de processamento continuam ocupados. Depois da evidência:

- `completed`: informe `provider_id` e duração real comprovada; a reserva fica
  consumida e a chamada é marcada como sucesso;
- `error`: informe a referência remota comprovada; a chamada é encerrada como
  erro e a reserva interna correspondente pode ser liberada;
- `not_submitted`: permitido apenas sem ID remoto, com evidência de não envio; a
  reserva é liberada. Também permite encerrar uma reserva pré-tentativa de job
  cancelado ou cuja publicação falhou, após confirmar ausência no banco e RQ.

Todas as decisões exigem `reason="dashboard_verified"` e geram auditoria. Se
os estados do provider ou da fila não puderem ser confirmados, preserve a
reserva e mantenha a admissão suspensa. Para reservas de franquia por conta em
estado `unknown`, use `POST /admin/transcription-reservations/{reservation_id}/reconcile`
somente após o job não estar ativo no banco/RQ e com evidência terminal. A
decisão `consumed` exige duração medida; escolha `released` apenas após
comprovar que não houve processamento. Essa conciliação não altera o ledger
técnico nem devolve orçamento AssemblyAI.

## Concessão de acesso por usuário

O endpoint administrativo `POST /admin/accounts/{user_id}/beta` recebe
`capabilities`, `expires_at` com timezone e `round_id`. Para usar a chave da
plataforma, inclua `transcription.platform` e o `round_id` igual à configuração
ativa. O banco impede ultrapassar o máximo de cinco contas distintas naquela
rodada; revogação, expiração ou exclusão de conta não repõem vagas. Um contador
anônimo mantém esse limite após a exclusão, sem preservar identidade. Existe
uma concessão ativa por usuário; revogue a anterior antes de
substituí-la. Revogar ou expirar bloqueia novas execuções, inclusive jobs ainda
na fila. Concessões e revogações são auditadas.

Migration `20261015_0017` adiciona metadados de rodada e evidência financeira,
preservando os registros anteriores. O downgrade protege esse histórico e
recusa remover evidência da beta.
