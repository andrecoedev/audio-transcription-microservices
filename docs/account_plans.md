# Planos, permissões e reservas de transcrição

## Estado implementado

Guest permanece demonstração sintética. Todas as contas novas e existentes,
inclusive administradores e contas locais, começam em Free. Não há promoção
automática para Starter, checkout, cobrança nem preços comerciais nesta entrega.
Starter/Business permitem credenciais próprias de AssemblyAI e Gemini, não
credenciais pagas da plataforma. Business é apenas um identificador extensível,
sem recursos comerciais adicionais. O papel de administrador gerencia acesso,
mas nunca ignora limites de processamento, rate limits ou orçamento AssemblyAI.

Histórico, ownership, reuniões, tarefas, preferências e ciphertexts existentes
não são removidos ou reatribuídos. Uma conta que perde acesso continua podendo
ler seus resultados e remover suas credenciais. Novas inferências e gravações
de credenciais exigem permissão atual. Worker revalida antes de executar.

## Configuração explícita e segura

API e Worker recebem a mesma `PLAN_POLICIES_JSON` pelo Compose. Default `{}`
desabilita admissão de novas transcrições; não é uma franquia comercial fictícia.
O objeto aceita somente `free`, `starter`, `business`, `beta`. Cada política:

| Campo | Unidade / regra |
|---|---|
| `monthly_usagi_seconds` | Segundos de áudio fornecido pela USAGI, mês-calendário UTC |
| `max_audio_seconds` | Máximo verificado por arquivo, inclusive BYOK |
| `max_stored_bytes` | Bytes de uploads mantidos, inclusive BYOK |
| `max_queued_jobs` | Trabalhos aguardando execução por conta |
| `max_processing_jobs` | Trabalhos simultâneos por conta |

Valores são inteiros não negativos, ausentes valem zero; limites operacionais
zero bloqueiam admissão. BYOK pode operar com franquia USAGI zero, mas exige
limites operacionais positivos. Os valores devem ser definidos pelo operador,
não por defaults comerciais no código. Políticas inválidas falham com 503.
Recriar API e Worker após mudar configurações; não imprimir Compose expandido.

Free não executa Whisper por default. Somente habilitar quando **ambas**
`LOCAL_TRANSCRIPTION_ENABLED` e `LOCAL_TRANSCRIPTION_HOMOLOGATED` forem verdadeiras,
após homologação explícita do ambiente. Beta não contorna esses controles.
Não há fallback para AssemblyAI. Infraestrutura, secrets/config flags, rate limits,
limites públicos/AssemblyAI e orçamento global existentes continuam necessários;
vale o menor limite aplicável. Não adicionar secrets ao frontend.

## Concessão administrativa

Rotas exigem usuário interno ativo com `is_superuser` verificado no banco:

- `PATCH /admin/accounts/{user_id}/plan`: plano explícito e motivo categórico.
- `POST /admin/accounts/{user_id}/beta`: lista de capabilities e prazo UTC futuro.
- `DELETE /admin/accounts/{user_id}/beta/{grant_id}`: revogação idempotente.

Capabilities: `transcription.byok`, `transcription.local`, `transcription.platform`,
`intelligence.byok`, `intelligence.platform`. Uma concessão ativa por conta;
revogar antes de substituir. Enquanto ativa, usa limites configurados em `beta`.
Expiração/revogação bloqueia novas chamadas, inclusive trabalho já enfileirado
mas ainda sem inferência. Não cancela uma chamada já autorizada/em andamento.
Concessões e alterações de plano geram audit events sem secrets ou conteúdo.

## Reserva transacional, separada do ledger

A linha `users` serializa admissões, slots e alterações administrativas no
PostgreSQL; nenhum lock permanece durante inferência. Unique `operation_key`
e recurso impedem duas reservas para o mesmo trabalho. Antes de enfileirar,
reserva-se o máximo permitido por arquivo ou o saldo mensal restante. A duração
confiável só é conhecida após FFmpeg no Worker: esse máximo conservador permite
autorizar upload sem processamento pesado na API. Saldo reservado não é consumo.

Depois da conversão, **antes de qualquer inferência**, Worker verifica duração,
permissão, reserva e persistência do marcador de tentativa. Libera a diferença
entre máximo e duração real, arredondada para cima ao milissegundo. Nunca usa
duração informada pelo cliente ou observador best-effort para autorizar.

`queued → processing → started → consumed` no sucesso. Falha seguramente anterior
à inferência libera a reserva. Falha/interrupção depois de `started` vira `unknown`,
mantendo o saldo indisponível: nenhum retry automático de inferência ambígua.
Recovery pré-inferência reutiliza ID, período original e reserva, mesmo na virada
do mês. Recovery respeita estados vivos do RQ. Limite simultâneo atingido impede
inferência; o trabalho falha de forma segura, sem scheduler adicional nesta Task.

O mês UTC não acumula saldo. BYOK mantém reserva/limites/medição separados e não
desconta franquia USAGI nem orçamento AssemblyAI da plataforma. Local usa franquia
USAGI, mas ledger registra `credential_source=local`, sem afirmar custo infra zero.
Exclusão de transcrição não restitui consumo: FK SET NULL mantém o registro.
Bytes só são liberados após exclusão física pelo outbox existente. Uploads legados
sem reserva usam `file_size_mb` conservadoramente na admissão de armazenamento;
não são apresentados como medição exata nem importados para consumo mensal.

Ledger P5-05 continua best-effort com journal durável e proveniência original.
Falha de métricas não bloqueia resultado. **Falha da autorização transacional**
bloqueia inferência: autorização financeira/operacional não pode ser best-effort.
Sucesso externo seguido de falha de persistência permanece ambíguo, sem desconto
duplo ou liberação automática. Reprocessamento concluído exige novo recurso,
não reset manual do job/reserva terminal.

## Reconciliação e implantação

`POST /admin/transcription-reservations/{id}/reconcile` permite decisão explícita
`consumed`/`released` para `unknown`, com motivo correspondente
`processing_verified`/`no_processing_verified`. O operador deve verificar execução
no provider/logs seguros antes de decidir. Redis indisponível ou RQ/DB ativo
bloqueia a ação. Consumo exige duração verificada. A ação é auditada e não reescreve
ledger técnico nem devolve orçamento AssemblyAI. Não há reconciliação automática
de chamadas externas sem evidência.

Alembic `20261008_0013` é aditiva: preserva dados e atribui Free a todas as contas.
Downgrade recusa remover reservas, concessões ou planos não-Free. Antes de rollout:
backup/restore, conferir destino e drenar jobs antigos; jobs pendentes sem reserva
não recebem autorização retroativa. Aplicar Alembic, configurar limites e recriar
API/Worker conjuntamente. Não executar migrations em volumes desconhecidos.

`GET /account/plan` é privado, derivado do usuário autenticado, sem seletor de
outra conta. Retorna plano, beta, período/renovação, franquia, consumo confirmado,
reservado/saldo e BYOK separado. Settings mantém métricas técnicas P5-05 à parte;
nenhum saldo inventado, preços comerciais ou custos internos são exibidos.

Validação local/isolada não homologa produção ou infraestrutura local de ML.
