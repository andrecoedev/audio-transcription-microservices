# Groq em Resumos inteligentes

## Estado e contrato

Groq é uma opção **explícita somente para resumos**. O primeiro candidato é
`openai/gpt-oss-20b`; 120b não foi implementado nem comparado sem justificativa.
Não há Groq para áudio, mudança de SDK Gemini, franquia mensal de resumos,
cobrança ou promoção automática de contas. `automatic` continua resolvendo
Gemini, sem fallback. Credenciais próprias de Gemini/AssemblyAI continuam com
criptografia, ownership e permissões da Task 2. Groq BYOK não faz parte desta entrega.

O adapter usa o HTTPX existente e o endpoint fixo de Chat Completions, sem tools,
streaming de geração, redirects, retries ou seleção de modelo pelo cliente.
O corpo HTTP é lido com teto de 1 MB. Timeout, recusa, truncamento, JSON inválido
ou erro do serviço falham explicitamente; não tentam Gemini.
Preserva o prompt P3-B.2, schema_version 1, campos null, grounding e revisões.
Tokens são observados antes da validação: uma resposta consumida e rejeitada
continua contabilizada. Schema/literal grounding não comprovam verdade factual.

**Não homologado com Groq real ou em produção.** Testes usam reuniões sintéticas,
respostas mockadas e PostgreSQL/Redis/RQ descartáveis. Nenhuma chamada paga foi
autorizada ou executada. Qualidade factual PT-BR, latência/tokens reais e acesso
ao modelo na conta devem ser homologados separadamente, com orçamento aprovado.

## Habilitação deliberada

Todos estes controles são necessários:

1. Migration `20261009_0014` no PostgreSQL identificado, com backup e janela
   de implantação API/Worker conjunta. Não testar migrations em bancos reais.
2. `GROQ_API_KEY` somente no Worker; API recebe apenas `GROQ_API_KEY_CONFIGURED`.
   Compose injeta a variável no ambiente do Worker, não na API ou frontend.
   Adicionar a chave ao `.env` não valida acesso/cota/modelo no serviço externo.
3. `GROQ_PLATFORM_ENABLED=true`, teto cumulativo positivo em
   `GROQ_PLATFORM_BUDGET_CENTS` (centavos **USD**, não créditos de usuário),
   `GROQ_MAX_ACTIVE_PER_USER` e `GROQ_MAX_PROCESSING_PER_USER` positivos.
4. `GROQ_INPUT_USD_PER_MILLION` e `GROQ_OUTPUT_USD_PER_MILLION` positivos,
   revisados pelo operador como **tetos conservadores** dos preços aplicáveis
   à conta/modelo. Não são preços comerciais nem tarifas automaticamente atualizadas.
5. Concessão administrativa auditada, revogável e com prazo contendo
   **`intelligence.groq.platform`**. A capability Gemini `intelligence.platform`,
   Starter, administrador e conta local não liberam Groq implicitamente.

Defaults: habilitação false; orçamento, taxas e limites por conta zero. Uma
capability não ignora infraestrutura, rate limit Redis nem orçamento. Worker
revalida autorização/validade/configuração antes de chamada. Uma operação já
autorizada pode terminar após revogação, como nas integrações existentes.
`available` na API significa implementação suportada, não conectividade externa.
`allowed/configured/platform_access` são estados seguros de elegibilidade.

Recriar API/Worker após mudar política. Nunca publicar `docker compose config`
expandido, secrets em comandos, URLs, logs ou respostas. Para conferir ambiente,
usar um processo sem modelos que imprime somente booleanos de presença.

## Limites e reserva de orçamento

`GROQ_MAX_INPUT_CHARACTERS` limita o transcript. O pedido completo inclui também
título, falantes, prompt e schema. Seu tamanho UTF-8 mais margem de envelope é
um **limite conservador de tokens**, não medição faturável. É verificado contra
`GROQ_MAX_INPUT_TOKENS` e janela de contexto de 131.072 tokens, junto com
`GROQ_MAX_OUTPUT_TOKENS` (inclui reasoning). Todos são configuráveis.

Antes de enfileirar, a mesma transação cria revisão e reserva. A linha do usuário
serializa admissões/concorrência; UPDATE condicional no orçamento compartilhado
impede ultrapassagem por contas concorrentes. A reserva em centavos é o custo
do limite de entrada/saída nas taxas configuradas, arredondado para cima, mínimo
um centavo. O teto efetivo é o menor entre banco e ambiente.

O Worker persiste `attempted` **antes** de HTTP. A mesma autorização não pode
produzir uma segunda chamada. Recovery preserva intenção pendente não publicada;
inferência interrompida fica failed/unknown no domínio/ledger, nunca é repetida
automaticamente. Uma nova tentativa deliberada cria nova revisão e nova reserva.
Resultado anterior permanece disponível durante regeneração e após falha.

Não há liberação automática das reservas Groq, inclusive pré-chamada, timeout,
exclusão ou reinício. É conservador: evita conceder orçamento em caso ambíguo,
mas pode bloquear uso antes de atingir a fatura real. O operador deve verificar
reservas/tentativas e fatura antes de alterar o teto; não zerar markers para retry.
Não é uma garantia contra tarifas mal configuradas ou mudanças do provedor:
revisar tetos e usar também o spend limit da própria conta Groq. Não há reset
mensal deste orçamento nem franquia mensal de resumos nesta Task.

## Medição, estimativas e desconhecidos

| Métrica | Fonte | Unidade / disponibilidade |
|---|---|---|
| `input_tokens` | `usage.prompt_tokens` | Tokens reais quando retornados; audit-only |
| `output_tokens` | `usage.completion_tokens` | Tokens reais, inclui reasoning; preço só com catálogo |
| `total_tokens` | `usage.total_tokens` | Agregado audit-only, não soma aos custos |
| `cache_read_tokens` | `usage.prompt_tokens_details.cached_tokens` | Opcional, ausência permanece null |
| `input_uncached_tokens` | Prompt menos cache, ambos consistentes | Derivado; null sem contagens suficientes |
| `reasoning_tokens` | `usage.completion_tokens_details.reasoning_tokens` | Opcional, subconjunto de saída; nunca preço separado |
| `provider_latency_seconds` | Relógio monotônico local | Segundos de chamada, não unidade de cobrança |
| `external_call` | Intenção antes de HTTP | Uma chamada por attempt, não prova faturamento |

Campos adicionais só são registrados se realmente presentes e numéricos; não
inferimos categorias da Responses API para uma resposta de Chat Completions.
Modelo/origem/provider vêm da revisão persistida, não de asserts do cliente.
Ledger/journal P5-05 preservam idempotência e recuperação sem invocar provider.
Falha temporária de métricas não impede entregar resultado.

Catálogo append-only aceita provider `groq` e model IDs com `/`; custos Decimal
são congelados com versão/vigência/fonte/moeda. Tarifas não são importadas por
default. Somente entrada não cacheada, saída e cache podem receber preço; total,
prompt inclusivo e reasoning são audit-only. Ausência de contagens/preço significa
custo desconhecido, não zero. BYOK existente mantém escopo customer, plataforma
usagi, local infraestrutura; não se misturam orçamento e ledger técnico.

## Referências oficiais e limites de homologação

Revisadas em 08/10/2026, sem inferência:

- [Structured Outputs](https://console.groq.com/docs/structured-outputs): 20b/120b suportam strict, todos os campos required e objetos sem propriedades adicionais.
- [Modelos e preços](https://console.groq.com/docs/models): confirmar catálogo/preços da conta antes de habilitar; nada é copiado como default real.
- [API](https://console.groq.com/docs/api-reference): Chat Completions e usage; ausência de detalhes opcionais não deve ser fabricada.
- [Limites](https://console.groq.com/docs/rate-limits): limites da organização não equivalem a franquias da USAGI.

Downgrade recusa perder reservas existentes ou preferências explícitas Groq.
Dados Gemini, ownership, ciphertexts e revisões anteriores permanecem intactos.
