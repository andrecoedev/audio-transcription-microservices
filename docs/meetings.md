# Reuniões e Meeting Intelligence

## Reunião persistente

Meeting compartilha PK com Transcription. Título/idioma/data e speakers editáveis
são próprios da reunião; owner, métricas e transcript JSONB permanecem na
Transcription. Não há segunda cópia do transcript nem dependência do resultado RQ.
Segments recebem ordem determinística por start/end/posição original.
Conclusão do Worker cria Meeting/speakers e completed na mesma transação.

| Endpoint | Contrato |
|---|---|
| GET /meetings | Lista metadados acessíveis ao owner/admin |
| GET /meetings/{id} | Metadados, speakers e métricas |
| GET /meetings/{id}/transcript | Segmentos persistidos com order |
| PATCH /meetings/{id} | Edita título |
| PATCH /meetings/{id}/speakers/{speaker_id} | Edita display name |
| DELETE /meetings/{id} | Remove reunião/transcrição; 409 se job ativo |

A migration de Meeting faz backfill de resultados completed já existentes.
Exclusão de transcrição remove Meeting, speakers e intelligence por cascade.

## Ações administradas pelo usuário

MeetingActionItem pertence à Meeting e armazena descrição, responsável opcional,
data operacional de prazo opcional (YYYY-MM-DD), status e timestamps. Tarefas
manuais não exigem Intelligence. Sugestões aceitas preservam a revisão, índice,
evidence e os campos originais; editar a tarefa nunca altera o resultado da IA.
O `due_date` da IA é uma expressão literal do transcript e fica em
`original_due_date`; só um prazo ISO explicitamente informado pelo usuário vira
`due_date` operacional. A tabela de review mantém a decisão por sugestão mesmo
depois de dismiss ou remoção explícita da ação, tornando retries idempotentes.

| Endpoint | Contrato |
|---|---|
| GET /meetings/{id}/actions | Lista tarefas, inclusive descartadas |
| POST /meetings/{id}/actions | Cria tarefa manual, inicialmente open |
| POST /meetings/{id}/actions/suggestions/{revision}/{source_index} | Aceita sugestão concluída; corpo opcional edita description/assignee/due_date |
| POST /meetings/{id}/actions/suggestions/{revision}/{source_index}/dismiss | Descarta sugestão sem criar tarefa operacional |
| PATCH /meetings/{id}/actions/{action_id} | Edita campos fornecidos; null limpa responsável/prazo |
| DELETE /meetings/{id}/actions/{action_id} | Remove explicitamente a tarefa, retorna 204 |

GET actions também retorna `suggestion_reviews` (accepted/dismissed/deleted),
para a interface suprimir sugestões já revisadas mesmo após reload. Aceite
repetido retorna a tarefa existente; sugestões já descartadas ou removidas
retornam 409 se aceitas novamente. Exclusão operacional é física; o ledger de
review permanece até a exclusão da reunião. Identificadores de revisão/índice
são resolvidos no servidor e somente revisões completed podem originar ações.

Status: open, done, dismissed. Concluir/reabrir/descartar usam PATCH. Dismissed
preserva o registro e pode ser reaberto; delete remove o registro operacional.
Descrição não pode ser vazia; status/descrição não aceitam null. IDs de tarefas
devem pertencer à Meeting da URL. Reads usam read_transcriptions, criação/edição
transcribe e exclusão delete_transcriptions; ownership segue o padrão existente
(404 para outro owner, acesso administrativo preservado). Exclusão da reunião ou
transcrição remove as tarefas por cascade. Audit events não guardam seu conteúdo.

## Ata revisada e exportação

| Endpoint | Contrato |
|---|---|
| GET /meetings/{id}/minutes | Projeção determinística: título/contexto, summary/topics/decisions/open_questions da revisão completed mais recente e tarefas operacionais abertas/concluídas |
| GET /meetings/{id}/minutes.md | Download Markdown da mesma projeção |

Sem intelligence concluída, as seções de IA retornam vazias; summary é string
vazia e listas são arrays vazios. Tarefas dismissed nunca entram na ata. Tarefas
AI aceitas usam descrição/responsável/prazo/status operacionais; a projeção
expõe source e identificadores de provenance. Texto dinâmico é escapado como
texto inline do Markdown para não criar links, HTML ou seções injetadas. Os
endpoints exigem read_transcriptions e respeitam ownership.

## Revisões de intelligence

MeetingIntelligence tem FK para Meeting, revisão monotônica, schema_version,
provider/model, status, fingerprint/metadados do source, result JSONB e timestamps.
O transcript não é duplicado. Contexto e speakers são capturados no request.
Lock na Meeting e índice único parcial garantem uma revisão ativa por reunião.

| Endpoint | Contrato |
|---|---|
| POST /meetings/{id}/intelligence | 202 pending/processing; 200 se já completed; failed permite retry |
| POST /meetings/{id}/intelligence/regenerate | Nova revisão terminal; reutiliza geração ativa |
| GET /meetings/{id}/intelligence/status | Estados/revisões duráveis e configuração pública |
| GET /meetings/{id}/intelligence/result?revision=N | Resultado completed; sem N, último completed |

Resultado anterior continua disponível durante geração/falha nova.
RQ recebe apenas ID; excluir seu estado efêmero não remove resultado PostgreSQL.
Ownership é verificado em todas as rotas; writes exigem scope meeting_minutes,
reads read_transcriptions. Erros públicos são sanitizados.
Redis indisponível antes do commit retorna 503 sem revisão. Enqueue incerto após
commit preserva pending; recovery examina job determinístico antes de republicar.
Abandono de inferência vira failed, sem retry automático de chamada cobrada.
Conclusão tardia após exclusão não recria a reunião.

## Contrato e grounding

Schema v1: summary, topics, decisions, action_items, open_questions.
Evidence contém segment_order zero-based e quote literal; timestamps são
resolvidos no servidor. Tasks têm assignee/due_date nullable. Prazo é expressão
explícita do transcript, não data de calendário inferida.

Pydantic rejeita campos extras/tipos/estruturas inválidas; grounding verifica
segmentos/quotes e presença literal de atributos. **Isso não prova interpretação
correta**, relação tarefa-responsável-prazo ou ausência de hallucination.
Prompt trata transcript como dados não confiáveis, pede leitura global,
abstinência em ruído/conflito e impede que o resumo reintroduza fatos descartados.
Responsável/prazo ausentes permanecem null. Sugestões não são decisões finais.
Revisão humana continua necessária; não existe um validador semântico perfeito.

## Provider e limites

Gemini reutiliza o cliente legado MeetingMinutesGenerator no Worker; SDK
google.generativeai, não migrado nesta limpeza. Modelo padrão gemini-2.5-flash,
schema_version 1, temperatura 0.1, JSON MIME, máximo 16384 tokens de saída.
Input limitado a 200000 caracteres por padrão. Job timeout padrão 600s;
chamada SDK no máximo 300s, retries de transporte desabilitados.
Sem chunking, loop de reparo ou troca silenciosa de provider.

GEMINI_API_KEY é Worker-only; API recebe GEMINI_API_KEY_CONFIGURED.
Modelo/runtime devem corresponder à revisão. Alterar versão/prompt exige nova
avaliação, não presumir compatibilidade.

## Compatibilidade e limites

/meeting-minutes segue ativo na navegação e conserva Markdown/espera HTTP/RQ.
Não tem persistência/revisões/provenance de intelligence; removê-lo exigiria
decisão de contrato/UX. O cliente Gemini e generate_minutes continuam necessários.

Ver [avaliação factual local](intelligence_validation.md). P3-A e P3-B/P3-B.2
foram validadas localmente; produção não homologada. Sem P3-C nesta limpeza.
