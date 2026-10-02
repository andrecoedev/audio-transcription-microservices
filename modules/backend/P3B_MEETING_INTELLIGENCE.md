# P3-B — Meeting Intelligence

## Auditoria anterior à implementação

`services/meeting_minutes.py` configura o SDK `google.generativeai`, modelo
`gemini-2.5-flash`, e extrai seções de Markdown por heurísticas. O prompt pede
português fixo e não contém referências de segmentos. O Worker retorna o
conteúdo apenas ao RQ; `/meeting-minutes/generate` mantém HTTP aberto até o
resultado. Além disso, o job antigo depende do registry do processo pai,
incompatível com inicialização lazy em filhos RQ. A API já não importa o SDK.
Compose entrega a chave apenas ao Worker e um indicador de configuração à API.

Decisão: reutilizar o cliente existente com uma operação JSON dedicada,
validada por Pydantic e referências literais. Manter o contrato legado separado
por compatibilidade. Uma tabela de revisões pertence à Meeting; cada retry
após falha/regeneração cria uma nova revisão, mantendo anteriores. Uma revisão
ativa por Meeting é protegida por lock da Meeting e índice único parcial.
RQ continua na fila existente; somente IDs são enfileirados/retornados.
Não há retry automático de chamadas cobradas: recovery republica pending
órfão, mas execução interrompida torna-se failed e permite retry explícito.

O input registra hash e metadados/speakers do momento da solicitação, sem
duplicar transcript. Segmentos permanecem na Transcription. Datas de tarefas
são expressões explícitas do transcript (por exemplo, "sexta-feira"), sem
inferir uma data de calendário. Provenance v1 usa `segment_order` e `quote`,
com timestamps resolvidos no servidor. Validação de referências não é uma
prova semântica; resultados continuam sujeitos à revisão humana.

## Contrato v1 e endpoints

`MeetingIntelligence` tem FK CASCADE para Meeting, revisão monotônica,
`schema_version`, provider/model, status, JSONB `result`, metadados do source,
fingerprint SHA-256 e datas de criação/início/conclusão. Os campos de conteúdo
são `summary`, `topics`, `decisions`, `action_items`, `open_questions`.
Cada item inclui descrição e `evidence` com índice zero-based `segment_order`
e `quote` literal. Tasks incluem `assignee` e `due_date`, ambos nullable.
Uma constraint impede completed com result NULL; validação Pydantic impede
tipos inválidos, campos extras e conteúdo parcial, e grounding impede índices,
quotes e deadlines inventados. Os nomes/IDs de assignee devem estar no trecho
ou corresponder a um speaker citado. Isso não prova atribuição semântica:
o prompt e a revisão humana continuam essenciais.

| Endpoint | Comportamento |
|---|---|
| POST `/meetings/{id}/intelligence` | 202 para pending/processing; 200 se já completed; failed permite nova revisão. |
| POST `/meetings/{id}/intelligence/regenerate` | Nova revisão depois de uma tentativa terminal; se há revisão ativa, reutiliza-a. |
| GET `/meetings/{id}/intelligence/status` | Última geração, revisão completed disponível, histórico de metadados e indicador de configuração. |
| GET `/meetings/{id}/intelligence/result?revision=N` | Só conteúdo completed; sem N, última revisão completed, mesmo durante falha/regeneração. |

Todas as rotas validam ownership; writes exigem scope existente
`meeting_minutes`, reads `read_transcriptions`. Rate limiting reaproveita o
budget Redis `job-user`, sem cobrar novamente requests idempotentes.
Redis indisponível antes do commit retorna 503 sem nova revisão. Se o enqueue
falhar após commit, a revisão permanece pending porque Redis pode ter aceito
o job; recovery inspeciona o ID determinístico antes de republicar.
Worker claim/finalização são transações curtas; o request ao provider ocorre
sem transação aberta. Falha sanitizada torna a revisão failed e levanta erro
sanitizado para RQ. Timeout/abandono é reconciliado no maintenance existente,
até 60 segundos após RQ reconhecer a execução terminal. Não há retry automático
de inferência: usuário solicita nova revisão, que preserva a anterior.
Exclusão de Meeting remove todas as revisões; conclusão tardia não as recria.
Exportação de dados inclui também todas as revisões de intelligence.

## Provider, limites e operação

`MeetingIntelligenceProvider.generate(context)` é a interface simples; Gemini
reutiliza `MeetingMinutesGenerator` e o SDK existente apenas no Worker.
`GEMINI_MODEL` padrão é `gemini-2.5-flash`. O provider pede JSON MIME, temperatura
0.1, limita output a 16384 tokens e desabilita retries de transporte. O schema
vai no prompt e é validado depois: JSON mode não garante correção factual.
Não há loops de reparo. Modelo da revisão e configuração Worker precisam
coincidir. `MEETING_MINUTES_TIMEOUT_SECONDS` (600 padrão) limita o job; chamada
Gemini tem timeout máximo 300s. `INTELLIGENCE_MAX_INPUT_CHARACTERS` (200000
padrão) limita texto; reuniões maiores são rejeitadas explicitamente.
Não há chunking nesta fase. O SDK `google.generativeai` é legado: migrar
coordenadamente para `google-genai` é dívida, sem presumir compatibilidade
por falta de smoke real. Referências oficiais:
[JSON e structured output](https://ai.google.dev/gemini-api/docs/structured-output)
e [Gemini 2.5 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash).

O endpoint legado `/meeting-minutes/generate` conserva seu contrato anterior,
inclusive espera HTTP e resultado RQ; não é o fluxo da P3-B. Foi corrigida sua
inicialização lazy do cliente no filho RQ. Sua migração/desativação precisa de
decisão de compatibilidade futura.

Para smoke com credencial local configurada, usar apenas fixture pública e
executar `scripts/smoke_http_dev.py --meeting --diarization --intelligence
--require-segments --drop-rq-job --audio-file /tmp/public-fixture.wav` no Worker.
`USAGI_SMOKE_PASSWORD` é entregue apenas por ambiente de processo. Opcional
`--review-output /tmp/public-review.json` cria arquivo exclusivo de review da
fixture pública, sem imprimir transcript ou output em logs. Revisar manualmente
summary/decisions/tasks e attribution/deadlines contra a fala/transcript.
Sem credencial, a suíte fake não substitui a avaliação do Gemini real.

## Validação local — 2026-10-01

Implementação validada localmente; produção NÃO homologada. A matriz ML
estável foi preservada. Nenhuma promoção Pyannote 4 ou mudança em P2-C.

| Verificação | Resultado e escopo |
|---|---|
| Backend completo | 139 passed, 11 warnings; imagem Worker estável, com PostgreSQL/Redis isolados `p3btest`. |
| Integração intelligence | PostgreSQL/Redis/RQ reais; provider determinístico fake, concorrência de requests, persistência sem resultado RQ e FK/cascade. |
| Alembic isolado | upgrade → downgrade → upgrade → check; sem drift. |
| Frontend | 14 testes; lint com zero warnings e build aprovados. Não houve walkthrough visual. |
| Docker | API, Worker e migrate construídos; Compose base/GPU validado com `config --quiet`. |
| API isolation | Import/startup sem Torch, Transformers, Pyannote, Faster-Whisper, CTranslate2 ou `google.generativeai`; teste bloqueia import da stack. |
| Python / diff | compileall e git diff --check aprovados; Git avisa normalização CRLF/LF em arquivos já existentes. |
| Configuração Gemini | MIME JSON, timeout, budget e retry=None verificados com cliente stub, sem chamada de rede. |
| Smoke desenvolvimento | Login/sessão 200, upload 202, queued → processing → completed; fixture pública FLEURS PT-BR, diarização estável CUDA, 12 segmentos/2 speakers. Meeting consultável após excluir job RQ, speaker renomeado e exclusão 200/consulta posterior 404. |
| Provider ausente | Status sem configuração; POST intelligence 503 esperado no smoke HTTP, sem criar revisão. |
| Gemini real | NÃO executado: chave ausente no Worker. Não houve avaliação manual de resumo, decisões, tarefas ou attribution produzidos pelo provider real. |

Os testes adicionais cobrem JSON/schema inválido, referência/quote/prazo/assignee
inexistente, falha do provider sanitizada, nulls preservados, retry bem-sucedido,
speaker renomeado, rollback de persistência, exclusão durante geração, idempotência
e regenerações com versão anterior preservada. Recovery cobre pending sem RQ,
queued/started e processamento interrompido; falha incerta de enqueue preserva
o intent pending. Testes frontend cobrem solicitação falha, retry e conteúdo
anterior durante regeneração com provenance e campos não identificados.

### Backup, restore e implantação de desenvolvimento

Antes da migration, confirmado volume `usagidev_postgres_data`, database
`transcription_db`, versão `20260930_0003`, 1 user, 0 transcriptions, 0 Meetings,
0 jobs ativos e 27 audit events. Não foram consultados bancos de terceiros.

Backup custom `database/backups/usagidev-pre-p3b-20261001.dump` preservado localmente
(diretório ignorado pelo Git; backup contém dados privados e requer proteção).
SHA-256: `CE02E536FBBDE83FC8A34D12B3963450AF5D71606E74AED72F2A5EEB412C57AE`.
Restore com `pg_restore --no-owner --exit-on-error` executado exclusivamente em
PostgreSQL novo, volume `p3brestore_postgres_data`, schema vazio confirmado.
Versão, todas as contagens acima e 6 FKs coincidiram com a origem. Não foi
sobrescrito banco nem volume existente; SQLite legado permanece intocado.

Após restore aprovado, API/Worker foram parados com zero jobs ativos, aplicada
migration `20261001_0004`, e reiniciados com overlay GPU estável. Alembic check
sem drift e API/PostgreSQL/Redis/Worker saudáveis. Smoke criou e excluiu somente
seus próprios dados. Bancos isolados contêm testes sintéticos, não uma cópia
homologada de produção. Serviços auxiliares de teste foram parados; volumes
preservados para inspeção. Desenvolvimento `usagidev` permanece ativo.

## Limitações e próxima etapa recomendada

Estado mais recente: [P3-B.2](P3B2_GROUNDING_ABSTENTION.md) corrigiu a abstinência
e validou localmente os critérios factuais sobre sources congelados, com uma
repetição B e regressão A/C. Produção não homologada; integração Git/PR pendente
por mudanças acumuladas da base. Os ensaios negativos anteriores seguem abaixo
como histórico, sem apagar evidências.

Atualização 2026-10-02: a execução real foi realizada na P3-B.1; integração
técnica aprovada, homologação factual local reprovada por prazo incorreto.
Os resultados abaixo de 2026-10-01 permanecem como histórico. Ver
[relatório P3-B.1](P3B1_GEMINI_LOCAL_HOMOLOGATION.md) para os quatro requests
reais, revisão semântica, métricas e correção do pool herdado após fork.

- Credencial e avaliação Gemini real pendentes: configurar somente no ambiente
  Worker, indicar disponibilidade na API e executar smoke público + revisão
  humana antes de confiar no conteúdo para uso operacional.
- Provenance literal valida referências, não garante entendimento semântico ou
  ausência de hallucination no resumo/atribuição de tarefas.
- Reuniões acima do limite são rejeitadas; sem chunking ou reparo automático.
- SDK Google legado emite warning de fim de suporte; Python 3.10 do Worker
  também emite aviso de término de suporte no google.api_core em 2026-10-04.
  Migrar SDK/runtime coordenadamente, conforme
  [guia oficial](https://ai.google.dev/gemini-api/docs/migrate), com smoke real;
  não declarar compatibilidade a partir do stub.
- Os 11 warnings da suíte incluem deprecações Starlette/httpx/AnyIO/RQ e
  Matplotlib/Pyannote. Não foram escondidos nem corrigidos por upgrades amplos.
- Endpoint legado de atas ainda usa seu contrato antigo; sua migração exige
  decisão de compatibilidade, não foi reescrito nesta fase.

P3-C recomendada: homologação factual do provider com fixtures e revisão humana,
migração coordenada do SDK legado/runtime, e estabilização do uso da análise
persistente antes de adicionar chat, RAG ou integrações. Não implementada aqui.
