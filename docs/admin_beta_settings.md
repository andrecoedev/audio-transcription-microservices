# Configurações administrativas da beta fechada

## Estado e escopo

Esta documentação descreve a implementação administrativa desta branch. A
interface e a API permitem preparar e revisar uma política persistida, mas isso
não significa que a integração foi homologada para produção, que uma chave está
configurada ou que o provider está online. A validação humana e a ativação real
da rodada são etapas separadas. Não faça chamadas pagas nem conceda acesso real
durante a validação técnica desta entrega.

A página é privada e exige administrador autenticado. Ela oferece quatro
seções: **Visão geral** (inclui Sistema), **Beta**, **AssemblyAI** e **Limites**.
O painel mostra status operacional, configurações, participantes convidados,
busca limitada de contas e histórico de alterações. Não permite ler áudios,
transcrições ou outro conteúdo pessoal.

As rotas de leitura são `GET /admin/settings`, `/overview`, `/participants`,
`/accounts?q=...` e `/history`. A busca exige pelo menos dois caracteres e
retorna até dez contas ativas correspondentes a nome ou e-mail. A alteração de
configuração usa `POST /admin/settings/initialize` para preparação inicial e
`PATCH /admin/settings/beta`, `/assemblyai` e `/limits` depois disso. Concessões
e revogações continuam nos endpoints administrativos de conta, descritos
adiante.

## O que mudou

| Configuração | Antes | Depois | Motivo |
|---|---|---|---|
| Política operacional | Variáveis de ambiente e uma política compartilhada entre API e Worker | Campos tipados em JSON na linha `PlatformProviderBudget` de AssemblyAI | Edição administrativa auditável sem criar um editor genérico de ambiente ou uma segunda fonte de orçamento |
| Inicialização | Valores de bootstrap podiam parecer configuração ativa | `POST /admin/settings/initialize` exige `confirmed=true`, versão esperada e cria política com beta e plataforma desativadas | Separar preparação de ativação; versão inicial é zero |
| Concorrência de edição | Sem versão explícita para detectar abas desatualizadas | Comparação de versão e bloqueio da linha no banco; toda gravação avança a versão e gera evento de auditoria | Evitar sobrescrita silenciosa e preservar autoria/histórico |
| Aplicação em execução | Mudança de ambiente dependia de recriação de processos | API e Worker leem o estado persistido no banco durante a admissão/chamada | Alterações dinâmicas, sem cache de processo que deixe os serviços divergentes |
| Teto e reservas | Ajustar limite podia conflitar com uso histórico | A mesma linha financeira conserva teto, alerta, reservado, baseline e histórico; redução só limita autorizações futuras | Não apagar compromissos financeiros já feitos |
| Chave do provider | Configuração da política podia ser confundida com credencial | Segredo permanece na infraestrutura do Worker; tela mostra apenas status configurado | Manter segredo fora do navegador, API administrativa e banco de políticas |
| Modelo e preço | Opções de modelo/preço podiam parecer editáveis junto com a política | Modelo `universal-3-5-pro` e detecção de falantes ficam fixos; preço exige catálogo revisado e versão registrada | Evitar reprecificação implícita de chamadas ou reservas |

## Armazenamento e aplicação

A política usa o registro existente de `PlatformProviderBudget` do provider
AssemblyAI. O JSON é validado contra campos declarados, a versão é comparada
antes da gravação e cada alteração gera auditoria com estado anterior e novo.
Não há chave-valor arbitrário para configurar variáveis de ambiente, novo
registro de orçamento ou cache permissivo quando o banco falha.

API e Worker consultam o banco antes da admissão e da chamada, sob os locks
transacionais aplicáveis. A edição não requer reiniciar processos. Um erro de
banco ou política inválida deve bloquear a operação, não reutilizar uma cópia
local possivelmente desatualizada. A chave AssemblyAI continua como segredo de
infraestrutura disponível somente ao Worker; a interface mostra no máximo se
uma credencial está configurada. Status “registrada” ou “configurada” não prova
que a chave foi validada pelo provider nem que o serviço está online.

`POST /admin/settings/initialize` só prepara uma política ausente. Ele exige
`confirmed: true`, aceita a versão atual (na primeira preparação, versão `0`)
e registra a alteração administrativa. Os valores de ambiente servem apenas
como bootstrap dos limites técnicos e da rodada quando ainda não há um
`round_id`; flags de habilitação e teto financeiro do ambiente não são
importados como permissões. A política criada mantém beta e plataforma
desativadas e teto financeiro zero. A inicialização não ativa tráfego.
Especificamente, `AAI_PLATFORM_BUDGET_CENTS` e
`AAI_PLATFORM_ENABLED` não são copiados para a nova política. Teto, reservado,
alerta e histórico que já existiam na linha financeira são preservados; o
bootstrap não importa habilitação antiga nem cria um teto novo a partir do
ambiente.

A migration `20261015_0018_admin_beta_settings` adiciona os campos de política,
versão, versão de preço e autoria/horário de atualização ao registro existente.
Ela não habilita a beta. O downgrade recusa prosseguir quando houver política,
versão alterada ou reservas comprometidas acima do teto, pois remover esses
dados perderia configuração ou histórico.

## Campos da interface

“Dinâmica” indica que o valor salvo é lido do banco em execução sem reinício.
“Fonte” explica a origem efetiva; limites técnicos do ambiente podem reduzir o
valor persistido. Valores padrão abaixo são defaults da política tipada antes
de bootstrap; valores de bootstrap podem vir da configuração de limites
existente. Nenhum desses defaults constitui aprovação comercial.

| Setting | Dinâmica | Fonte | Default | Requer restart | Sensível |
|---|---|---|---:|---|---|
| `beta.enabled` | Sim | Política no banco; exige confirmação explícita | `false` | Não | Não |
| `beta.round_name` | Sim | Política no banco | `Beta fechado` | Não | Não |
| `beta.round_id` | Sim; torna-se imutável após convite ou uso | Coluna de rodada no registro financeiro; bootstrap pode preencher se vazia | vazio | Não | Não |
| `beta.max_participants` | Sim | Política no banco, máximo permitido 5 | `5` | Não | Não |
| `beta.quota_minutes_per_participant` | Sim; redução só vale para novas autorizações | Política no banco; bootstrap usa segundos de rodada convertidos em minutos inteiros | `600` | Não | Não |
| `assemblyai.platform_enabled` | Sim | Política no banco; exige confirmação explícita | `false` | Não | Não |
| `assemblyai.hard_stop_usd` | Sim; redução abaixo do comprometido é aceita e bloqueia apenas autorizações futuras | Coluna financeira de teto em centavos; exige confirmação explícita | `0` | Não | Não |
| `assemblyai.alert_usd` | Sim | Coluna financeira do alerta; precisa ficar abaixo do teto | `0` | Não | Não |
| `assemblyai.model` | Não editável | Constante da implementação | `universal-3-5-pro` | Não | Não |
| `assemblyai.speaker_detection` | Não editável | Constante da implementação | `true` | Não | Não |
| `assemblyai.price_version` | Não editável pela tela | Versão do catálogo revisado associada ao registro financeiro | sem versão | Não | Não |
| `limits.max_audio_seconds` | Sim, limitado também pela capacidade técnica | Política no banco e `AAI_MAX_AUDIO_SECONDS` | `600` s | Não | Não |
| `limits.max_upload_mb` | Sim, limitado também pelo máximo global de upload | Política no banco e `MAX_UPLOAD_SIZE_MB` | `100` MB | Não | Não |
| `limits.max_stored_bytes` | Sim | Política no banco; bootstrap vem de `PLAN_POLICIES_JSON.beta` | `0` bytes | Não | Não |
| `limits.max_queued_per_account` | Sim | Política no banco; bootstrap vem dos limites beta ou fallback `2` | `2` | Não | Não |
| `limits.max_processing_per_account` | Sim | Política no banco; bootstrap vem dos limites beta ou fallback `1` | `1` | Não | Não |
| `limits.max_platform_queued` | Sim | Política no banco; bootstrap usa `AAI_PLATFORM_MAX_QUEUED` | `10` | Não | Não |
| `limits.max_platform_processing` | Sim | Política no banco; bootstrap usa `AAI_PLATFORM_MAX_PROCESSING` | `1` | Não | Não |

Outros limites do provider também restringem a operação: upload no beta é no
máximo 100 MB, duração por áudio no máximo 600 segundos, quota por conta entre
0 e 600 minutos, até cinco contas distintas, até 100 chamadas de plataforma na
fila (default 10) e até dez em processamento (default global uma em
processamento).
As filas e concorrências por conta também têm teto de validação de 100 e 10,
respectivamente. O limite efetivo é sempre o menor entre política beta e
capacidade técnica. Exceções preexistentes `LARGE_UPLOAD_USER_IDS` e acesso
local de desenvolvimento continuam aplicáveis conforme sua finalidade; não
são concedidas pela tela beta.

## Regras de mudança e compromissos

Alterações de habilitação beta, quota, rodada e teto financeiro requerem
confirmação explícita. A rodada não pode ser trocada depois de convites, uso,
reservas ou chamadas históricas. O máximo de participantes não pode ficar abaixo
das vagas já usadas. Aumentar teto ou habilitar uma das flags depende de
conferência financeira válida e de tarifa revisada no catálogo.

Reduzir quota abaixo do total consumido ou reservado é aceito como limite para
futuras autorizações. O sistema não altera retroativamente o uso, não cancela
jobs já enviados e não cria crédito/reembolso. Se o total comprometido superar
o novo limite, a disponibilidade de novos minutos fica em zero e novas
admissões são bloqueadas; a interface sinaliza o compromisso acima do limite.
Chamadas já submetidas continuam seu fluxo normal. Não há renovação automática
nem reposição mensal da franquia.

Teto financeiro, reservado, saldo baseline e consumo histórico continuam no
mesmo registro. Reduzir teto abaixo de montantes comprometidos não apaga
reservas nem reescreve chamadas antigas. O hard stop controla novas
autorizações internas; não é saldo externo nem limite garantido de fatura.
Modelo e detecção de falantes permanecem fixos e somente leitura. A revisão de
preço deve apontar para uma entrada imutável do catálogo de `UsagePrice` para
`universal-3-5-pro+speakers`, quantidade de 3600 segundos por unidade e moeda
USD. Não altere tarifa durante chamadas ou reservas pendentes.

## Acesso, participantes e endpoints existentes

A busca administrativa é somente de contas ativas por nome/e-mail, com dois ou
mais caracteres. A página não oferece busca de conteúdo do usuário. A visão de
participantes lista contas convidadas, capacidades, expiração/revogação e
segundos consumidos, reservados e disponíveis. Exclusão/anonimização não repõe
vaga: o contador anônimo preserva o máximo de cinco participantes distintos.

Conceder acesso permanece uma ação explícita pelo endpoint
`POST /admin/accounts/{user_id}/beta`, com capacidades, `expires_at` com fuso
horário e `round_id` da rodada. O uso da chave USAGI requer
`transcription.platform`; a concessão precisa corresponder à rodada e só vale
com beta e plataforma habilitadas. Defina uma expiração futura deliberada.
Revogação usa `DELETE /admin/accounts/{user_id}/beta/{grant_id}`. Concessões e
revogações são auditadas. Uma concessão ativa por usuário deve ser revogada
antes de substituí-la.

## Runbook futuro — manual, sem execução nesta validação

As etapas seguintes são um roteiro para operação futura após homologação e
autorização humana específica. **Este documento não executa nem autoriza saldo,
ativação, concessões reais ou chamadas pagas.** Todos os valores comerciais e
evidências precisam vir da operação real; não invente tarifa, saldo ou
referências.

1. Confirme manualmente que conta/projeto/chave AssemblyAI são exclusivos da
   USAGI e que não há autopay. Não compre créditos nem altere saldo.
2. Inicialize no banco a política explicitamente desativada, confirmando
   `beta.enabled=false` e `assemblyai.platform_enabled=false`. Não copie flags
   de habilitação ou teto de ambiente para a política.
3. Se `round_id` estiver vazio, escolha e registre o identificador da rodada
   antes de qualquer convite ou histórico; depois disso a troca é bloqueada.
4. Confira o saldo existente no painel do provider e registre evidência pela
   CLI/API administrativa já existente, com JWT de administrador obtido por
   canal local seguro. Nunca cole token ou saldo observado em documentação,
   chat, issue ou log. Use rótulos não secretos para chave/projeto. Confirme
   exclusividade e que não há chamadas pendentes antes do snapshot. A fotografia
   é manual, expira segundo a configuração operacional e não acompanha saldo
   externo automaticamente.
5. Com chamadas e reservas drenadas, revise a tarifa do modelo fixo na fonte
   atual e grave uma versão imutável no catálogo; não escolha tarifa comercial
   por suposição. Revise teto interno e alerta, mantendo a relação aprovada de
   15 USD de teto e 12 USD de alerta somente se essa autorização comercial
   continuar válida. Verifique também os limites externos observados: snapshots
   não são hard stop do provider.
6. Revise quota de até 600 minutos por conta, máximo de cinco participantes,
   concorrência e fila globais/por conta, limite de duração e armazenamento.
   Configure limite de armazenamento explicitamente acima de zero somente se
   houver capacidade definida; seu default zero bloqueia armazenamento beta.
7. Só conceda contas por decisão explícita do administrador, com expiração
   futura e capacidades mínimas necessárias. Registre a concessão no sistema,
   sem compartilhar evidências financeiras na interface do convidado.
8. Ative a plataforma e a beta somente após autorização humana para a rodada,
   conferência financeira válida, tarifa revisada e revisão de limites. A
   ativação exige confirmação explícita; este passo
   não substitui o processo de release nem validação humana da entrega.

## Interpretação dos indicadores

“Credencial configurada” é apenas indicação de configuração disponível ao
Worker, não comprova que a chave funciona ou que o provider está online.
“Worker registrado” indica presença/registro operacional, não prontidão para
produção, disponibilidade do provider ou uma chamada bem-sucedida. A visão geral
não expõe saldo ou crédito do provider, valor de chave nem rótulo de projeto ao
navegador. A checagem de saldo disponível permanece operação de CLI/painel
restrita ao operador; a página não executa chamadas pagas.

Estado desta entrega: documentação dos contratos implementados. Ativação real
do Beta permanece pendente de autorização e operação manual; não interprete
esta página como aprovação para ativar a integração.
