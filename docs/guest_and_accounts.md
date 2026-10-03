# Contas públicas, visitantes e origem de credenciais

## Experiência e identidade

`/` e `/new-transcription` usam o Layout, navegação e upload do aplicativo,
inclusive sem conta; `/guest` é somente um redirect compatível para `/`.
Recursos privados mostram um convite para entrar/criar conta, sem montar telas
que disparem requests privados. `/signup` cria usuário persistente não administrador;
login mantém o JWT no navegador como antes e logout remove a sessão local.
JWT já emitido permanece válido até expirar: logout não é revogação global.
Email não é verificado nem usado para atribuir ownership nesta etapa.
Login/signup entram imediatamente na área autenticada, inclusive com
`saveGuest=1`. A prova temporária continua na aba, com ação explícita para salvar
o resultado anterior na conta; autenticação não reclama ownership automaticamente.

Uma sessão Guest tem UUID aleatório, expiração no PostgreSQL e JWT assinado
com `purpose=guest`. Não é um usuário fictício. JWT de conta não serve como
prova Guest, e JWT Guest não autentica nas rotas privadas. A prova temporária
fica em `sessionStorage` da aba; fechar a aba pode perder a possibilidade de
recuperar dados, não torna o resultado público. Tokens nunca vão em URLs.
Os resultados continuam no PostgreSQL, não no estado efêmero RQ.

## Operações e limites

Guest usa exclusivamente AssemblyAI com detecção de falantes nativa, sem
Whisper/Pyannote/CUDA nem fallback. Uma submissão por arquivo, com timestamps
normalizados em segundos e falhas propagadas, não texto falso de sucesso.
Fica desligado por padrão: exige política explícita, chave no Worker, indicação
segura na API e orçamento PostgreSQL. A política publica `can_create_job` conforme
essa admissão; configuração ausente retorna 503, quota/orçamento esgotado 429.
Jobs legados sem reserva ou Guest Whisper são rejeitados antes de engines.
Sessão, leitura de resultados, claim e exclusão continuam protegidos.

O ledger financeiro persiste origem platform/contexto original mesmo após claim,
reserva custo conservador antes do enqueue e marca tentativa antes de upload.
Não há reembolso/reset em exclusão nem segunda submissão automática em recovery.
BYOK por conta está separado deste orçamento, sem fallback de execução para a chave da plataforma. Consulte
[configuração, recuperação e limites AssemblyAI](assemblyai.md), inclusive a
retenção externa, que não é coberta pela exclusão local.
Contas públicas podem salvar e revisar reuniões, editar ações e usar os recursos
P3 locais; não herdam credenciais externas da plataforma. A diarização local
permanece permitida para contas autenticadas, conforme configuração existente.

Defaults operacionais configuráveis, não planos comerciais:

| Configuração | Default | Aplicação |
|---|---:|---|
| `SIGNUP_RATE_LIMIT_PER_IP` | 5/h | Cadastro |
| `GUEST_SESSION_RATE_LIMIT_PER_IP` | 5/h | Criação de sessão |
| `GUEST_JOBS_PER_SESSION` | 1 | Reserva atômica persistente |
| `GUEST_RETENTION_HOURS` | 24 | Desde criação da sessão |
| `PUBLIC_MAX_UPLOAD_MB` | 100 MiB | Guest e conta pública |
| `PUBLIC_MAX_AUDIO_SECONDS` | 600s | Snapshot no job |
| `PUBLIC_JOB_TIMEOUT_SECONDS` | 300s | Snapshot no job/RQ/recovery |
| `PUBLIC_JOB_RATE_LIMIT_PER_IP` | 3/h | Guest e conta pública |
| `PUBLIC_JOB_RATE_LIMIT_GLOBAL` | 10/h | Quota de jobs públicos, não orçamento pago |

Redis indisponível fecha criação de sessão, signup e upload/job com 503.
Login, signup e claim limitam o corpo JSON real a 16 KiB antes de parsing.
Limite retorna 429/Retry-After; consultas a resultados persistidos não dependem
de Redis. Janela fixa pode permitir dois orçamentos próximos à virada de hora;
não é contabilização financeira. Cadastro de múltiplas contas não reinicia o
orçamento global público. Falhas/tentativas podem consumir o orçamento horário;
excluir um resultado não reinicia a cota persistente de Guest.

O upload Guest e o JWT emitido para conta pública limitam também os bytes reais da requisição antes do spool
multipart, com margem de 64 KiB para envelope. O Worker converte somente até
limite de duração + 1s e rejeita excedentes antes da inferência. Não confia na
duração declarada pelo cliente. Timeout inclui carregamento de modelos; máquina
lenta pode precisar ajuste operacional. Conversão para conta não remove o limite
gravado no job pendente. API continua sem ML/FFmpeg/CUDA.

O claim assinado de procedência serve somente para restringir antecipadamente o
transporte. Autorização e acesso a providers continuam consultando a identidade
atual no banco; claims e estado do navegador não concedem permissões.

Proxy/perímetro deve limitar corpo, tempo, conexões e buffering antes da API.
Nginx do desenvolvimento não é um perímetro público homologado: IPs de clientes
podem compartilhar o bucket do proxy, pois cabeçalhos forwarded não são confiança
automática. Configure confiança explícita/perímetro antes de implantação pública.

## Conversão e retenção

`POST /guest/claim` exige JWT de conta ativa e prova Guest no corpo. O servidor
bloqueia a sessão no banco, transfere seus ownerships e revoga acesso Guest.
Não aceita ID do cliente como autorização. Repetir na mesma conta é idempotente;
outra conta não pode reclamar a mesma sessão. Jobs ativos podem ser salvos na
conta, mas não excluídos. Cadastro não pode reservar admin nem assumir usernames
de ownership legado; contas públicas não usam a ponte `owner_sub` para acesso.
Migrations antigas e ownerships históricos não resolvidos são preservados.

Expiração bloqueia acesso/claim imediatamente. A eliminação física ocorre pela
rotina existente de manutenção; não há novo serviço/agendador. Execute regularmente
em banco/volume identificado (recomendação: de hora em hora):

```powershell
docker compose -p usagidev --env-file modules/backend/.env --profile maintenance run --rm maintenance python -m scripts.apply_retention
docker compose -p usagidev --env-file modules/backend/.env --profile maintenance run --rm maintenance python -m scripts.apply_retention --apply
```

Preview é default. Cleanup serializa com claim/upload, preserva jobs ativos,
não apaga resultados transferidos e é idempotente. Falhas de arquivos são
reportadas; arquivos órfãos restantes são tratados pela reconciliação existente.
Se a rotina não for agendada, os dados ficam inacessíveis após expirar, mas
permanecem fisicamente no armazenamento: responsabilidade operacional explícita.

Migration `20261002_0007`: origem de cadastro, sessões/ownership Guest e limites
do job. Downgrade bloqueia quando existem contas públicas ou ownerships Guest:
exige plano explícito de preservação/transferência, não transforma silenciosamente
conta pública em identidade local privilegiada nem descarta dados temporários.

## BYOK e providers

BYOK é o padrão para contas públicas e está disponível em Settings, com proteção
de armazenamento e respostas somente de metadados; ver [providers](provider_preferences.md).
Não há secrets em JWT/schema Guest. Não usar uma flag
`cloud_enabled`: disponibilidade do provider, permissão por contexto, preferência,
origem da credencial e orçamento são conceitos separados.

`registration_source=public` é procedência da identidade validada no banco,
não um plano/provedor. Identidades locais provisionadas pelo operador, incluindo
admin e contas pré-existentes, preservam contratos privados. A política central
nega `credential_source=platform` para identidade pública, independentemente de
flags `*_CONFIGURED` ou claims enviados pelo cliente. Credencial `user` consome a
cota do usuário, sem orçamento platform nem fallback durante execução.

P4-03: Settings → Providers → credencial própria protegida → preferência.
Intelligence inicialmente Gemini, extensível a providers efetivamente suportados,
sem OpenAI/Anthropic nesta entrega. Nunca retornar chaves salvas, logar, incluir
em erros/JWT/URL nem persistir em plaintext. Somente estado `configured` e
metadados seguros, remoção/substituição explícitas e estratégia de proteção.

P4-04: AssemblyAI híbrido. Credencial `user` usa cota do usuário; eventual franquia
`platform` exige habilitação e orçamento próprios, separados de BYOK. A recuperação
do adapter foi validada localmente. Não habilitar consumo público de chaves do operador
por apenas criar conta. Produção segue não homologada; Pyannote 4 não promovido.
