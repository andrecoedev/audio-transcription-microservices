# Privacidade no beta

Este documento descreve o comportamento atual do serviço e recomendações
operacionais para o beta. A configuração local não representa, por si só, uma
política de produção homologada nem uma garantia de conformidade legal.

## Dados tratados

O PostgreSQL guarda a conta e seus dados de produto: identidade, preferências,
referências de credenciais próprias protegidas, transcrições, segmentos,
reuniões, falantes, tarefas e revisões de inteligência. O acesso ao conteúdo é
vinculado ao dono da conta. O papel de administrador e o plano são controles
separados: administrar contas ou permissões não concede acesso global ao
conteúdo de outras pessoas.

O áudio original fica em armazenamento privado enquanto o job está em execução.
Após o job chegar a um estado terminal, o sistema agenda a remoção do original.
Falhas de storage deixam uma intenção de limpeza durável para novas tentativas.
Arquivos de conversão são temporários do Worker. Uploads sem referência ativa
podem ser encontrados pela reconciliação de órfãos após 24 horas, valor padrão
configurável (`AUDIO_ORPHAN_RETENTION_HOURS`).

Transcrições concluídas e falhas permanecem disponíveis até que o dono as
exclua, salvo se o operador configurar retenção automática. No default atual,
`TRANSCRIPTION_RETENTION_DAYS=0` significa sem expiração automática. Jobs ativos
são protegidos contra retenção e exclusão normal. Sessões Guest expiradas usam
limpeza separada, com `GUEST_RETENTION_HOURS=24` por padrão; a rotina de
manutenção preserva jobs ativos e só remove a sessão quando pode remover seus
dados associados.

## Providers externos

O processamento local de áudio não envia o áudio ao provider de transcrição em
nuvem. O Worker pode consultar o Hugging Face para baixar os modelos
configurados. A seleção explícita de AssemblyAI envia o áudio ao serviço
AssemblyAI, tanto com credencial da plataforma autorizada quanto com BYOK. A
seleção de Gemini envia transcrição e contexto da reunião ao Gemini; Groq recebe
o contexto da reunião quando escolhido e autorizado. Groq não processa áudio.
BYOK muda a origem da credencial e a conta externa usada, não o fato de que os
dados selecionados são enviados ao provider.

Não há fallback silencioso entre execução local e cloud ou entre providers.
Políticas de retenção, uso para treinamento, processamento posterior e exclusão
remota dependem dos termos, configurações e contrato aplicáveis à conta do
provider. O serviço não configura nem verifica essas políticas e não garante
que dados externos não sejam retidos ou usados para treinamento. A exclusão no
USAGI não apaga automaticamente cópias mantidas pelo provider. Antes de usar
conteúdo sensível com um provider externo, confirme suas condições diretamente
com esse provider.

## Exclusão e exportação

`GET /account/data` exporta somente a conta autenticada: perfil, plano,
transcrições, reuniões, falantes, tarefas e revisões, preferências e medidas
técnicas de consumo próprias. Não aceita seletor de usuário. O JSON não contém
hash de senha, tokens, BYOK/ciphertext, diagnóstico livre, caminhos, storage keys
ou custos internos. A resposta não pode ser armazenada em cache; o download é
criado no navegador, sem arquivo de export permanente no servidor. O limite de
exportação é configurável (`PRIVACY_EXPORT_RATE_LIMIT_PER_USER`, padrão 5/hora).

`DELETE /account` exige confirmação literal `EXCLUIR`. Para login local exige
novamente a senha; para Firebase exige ID Token verificado com autenticação nos
últimos cinco minutos. A interface reautentica com o SDK oficial e confirma o
mesmo UID antes de enviar a solicitação. Não aceita ID de outra conta, mesmo
para administradores. A guarda do usuário serializa admissão e exclusão; conta
em uso retorna 409. Redis indisponível bloqueia a verificação de operações
legadas, não autoriza exclusão por aproximação. O rate limit usa contador
próprio e falha segura com 503.

A transação remove perfil/hash, ownership resolvido, conteúdo, reuniões,
tarefas/revisões, preferências e credenciais. O mesmo commit grava cleanup de
arquivos e um recibo em `account_deletions`. A remoção da identidade Firebase
usa apenas o projeto configurado e ADC **da API**, nunca do Worker; não remove
a conta Google global. Falha externa mantém UID/projeto só no recibo pendente
e bloqueia login/reprovisionamento e vinculação desse UID a outra conta. O retry
é idempotente; ao concluir elimina UID/projeto do recibo. Não há credenciais
administrativas novas nem alterações de IAM nesta entrega.

A resposta diferencia `account_deleted`, `cleanup_pending` e
`identity_cleanup_pending`; exclusão lógica não promete exclusão física imediata.
O administrador de bootstrap excluído não é recriado automaticamente pelo `.env`:
o recibo bloqueia bootstrap posterior, exigindo recuperação operacional revisada.
Ownership legado sem correspondência inequívoca continua preservado, sem atribuir
ou excluir conteúdo de terceiros.

A exclusão de transcrição/reunião protege transcrição ativa e apaga o agregado
local. Uma geração de resumo já iniciada pode terminar externamente, mas seu
resultado não recria o registro excluído. Isso não cancela nem apaga cópias no
serviço externo. Jobs legados ativos no RQ também bloqueiam exclusão. Conteúdo
efêmero de atas legadas pode permanecer no Redis até seu TTL de resultado,
`MEETING_MINUTES_TIMEOUT_SECONDS`; os resumos atuais retornam só metadata no RQ.

Eventos de auditoria e métricas de uso não guardam o áudio ou o texto da
transcrição, mas podem manter timestamps, IDs técnicos de recurso/operação,
provider, modelo e medições. Na exclusão da conta, referências diretas ao
usuário são removidas ou anuladas conforme a relação de cada ledger. IDs
técnicos que permanecem podem permitir correlação com registros externos; trate
esses registros como dados operacionais pseudonimizados, não como anonimização
irreversível. Não há expiração automática configurada para audit ou usage no
default atual. A retenção de auditoria pode ser configurada pelo operador;
`AUDIT_RETENTION_DAYS=0` significa sem expiração automática. Não há TTL de usage
implementado nesta etapa.

## Backups e restauração

O repositório documenta procedimentos para backup e restauração do PostgreSQL,
mas ainda não tem uma política de backup de produção configurada ou validada.
Como recomendação operacional para o beta, mantenha backup diário e uma janela
de retenção de sete dias, com controle de acesso e proteção adequados. Isso é
uma recomendação; não instala scheduler, política de lifecycle nem backup
automático.

Backups podem conter dados que foram excluídos depois de sua criação. Portanto,
restaure primeiro em ambiente isolado, identifique e reaplique as exclusões
solicitadas após a data do backup e só então disponibilize a stack restaurada.
Não abra o serviço aos usuários antes dessa reconciliação. A chave de
criptografia de credenciais BYOK precisa estar disponível e protegida
separadamente do banco; sem ela, as credenciais cifradas não podem ser
decriptadas. Nenhum backup real ou procedimento de restore de produção foi
homologado nesta etapa.

Para reconciliar uma restauração antiga, preserve os recibos mais recentes em
backup privado separado do snapshot escolhido. Compare `deleted_user_id` dos
recibos com usuários restaurados, com API e Workers ainda parados; reaplique as
exclusões identificadas antes de abrir o serviço. Registros antigos marcados
ativos exigem revisão offline, não reenvio automático a providers. A tabela de
recibos e as filas de limpeza não podem ser descartadas por downgrade:
`20261013_0015` recusa downgrade quando existem recibos. Sem recibos atuais ou
sem resolver essas diferenças, **não promover o restore**. A reconciliação
histórica não é automatizada por esta Task.

## Política aprovada e responsabilidades

| Dado | Onde fica | Retenção | Exclusão | Observação |
|---|---|---|---|---|
| Perfil, vínculo e BYOK | PostgreSQL | Até excluir conta | Cascades na transação | Cifra BYOK não entra no export |
| Transcrição, reunião, tarefas, revisões | PostgreSQL | Até dono excluir; sem TTL automático | Agregado local | Admin não lê conteúdo alheio |
| Original/materialização | Volume privado do processamento | Até terminal; temporários por execução | Worker + outbox/retry | Falhas podem deixar cleanup pendente |
| Arquivo órfão | Volume privado | 24h padrão | Reconciliação com preview | Não apaga input ativo |
| Guest legado | PostgreSQL/volume | 24h padrão | Manutenção própria | Guest atual é demonstrativo |
| Usage/audit e reservas de segurança | PostgreSQL/spool privado | Sem expiração automática por enquanto | FKs pessoais anuladas; metadata livre de audit limpa | IDs técnicos permanecem; não declarar anonimização irreversível |
| Recibo de exclusão | PostgreSQL | Sem expiração automática | UID removido ao completar Firebase | Preserva retry e histórico para restore |
| Estado/resultados efêmeros | Redis/RQ | TTL e regras existentes por job | Expiração/recovery | Não é fonte de verdade dos resultados atuais |
| Export | Memória da API/navegador | Duração da requisição/download | Blob revogado no navegador | Cópia baixada passa ao controle do usuário |
| Backups | Destino privado definido pelo operador | Diário, janela proposta 7 dias | Rotação operacional | Agendamento e homologação de implantação pendentes |

## Rotina operacional atual

`scripts.apply_retention` oferece preview por padrão. A execução com `--apply`
aplica retenção configurada de transcrições e auditoria e limpeza de sessões
Guest. A reconciliação de uploads órfãos e o retry de exclusões de storage ficam
em `scripts.reconcile_audio_files`, também preview por padrão e executável com
`--apply`. Nenhum dos comandos é agendado automaticamente; o operador precisa
executá-los periodicamente e acompanhar falhas. Não configure dias de retenção
de resultados sem definir também a comunicação ao usuário e conferir os
candidatos antes da primeira aplicação.

Para identidade pendente, executar **dentro da API com o overlay Firebase/ADC
correto**, não no container maintenance ou Worker:

```sh
python -m scripts.reconcile_account_deletions
python -m scripts.reconcile_account_deletions --apply --limit 100
```

O primeiro comando é preview; a saída contém apenas contagens. O operador deve
monitorar pendências e repetir falhas, sem ampliar IAM automaticamente. Não foi
instalado scheduler. A interface informa Beta e envio externo antes de upload e
resumo; relatos de falha devem ser encaminhados pelo contato que concedeu o
acesso ao Beta, sem tokens, chaves ou conteúdo privado em prints públicos.

## Evidência local e limites

No cluster descartável `usagi-beta-privacy-test-20261014`, a migration 0015 e
`alembic check` passaram. O drill PostgreSQL custom-format `pg_dump`/`pg_restore`
validou 24 tabelas, head, contagens, ownership, JSONB e FKs com conteúdo sintético.
Isso não homologa produção, backup automatizado, restore de volume real nem
reaplicação histórica de todas as exclusões. A remoção Firebase foi testada com
mocks, sem excluir contas reais; permissão real `firebaseauth.users.delete` e
um teste autorizado de conta descartável são requisitos de implantação.

Antes de convidar usuários externos: instalar/acompanhar rotinas de manutenção
e backup aprovadas, testar restore coordenado de banco/volume/chave BYOK,
verificar permissão de remoção Firebase e estabelecer canal de feedback e
revisão jurídica/comercial. Não afirmar LGPD ou políticas de treinamento do
provider com base nos testes técnicos.

Referências oficiais consultadas para esta integração:
[Admin SDK delete_user](https://firebase.google.com/docs/reference/admin/python/firebase_admin.auth#delete_user),
[reautenticação no SDK Web](https://firebase.google.com/docs/reference/js/auth#reauthenticatewithpopup) e
[permissão de exclusão](https://firebase.google.com/docs/projects/iam/permissions).

Referências: [segurança](security.md), [operações e backup/restore](operations.md),
[ciclo de dados](cloud_data_architecture.md), [providers por conta](provider_preferences.md),
[AssemblyAI](assemblyai.md), [Groq](groq_intelligence.md) e
[retenção de sessões Guest](guest_and_accounts.md).
