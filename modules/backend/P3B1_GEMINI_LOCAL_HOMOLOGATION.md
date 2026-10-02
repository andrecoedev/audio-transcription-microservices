# P3-B.1 — Homologação funcional local Gemini

Histórico preservado. A correção e homologação local limitada dos critérios
de grounding/abstinência estão no [relatório P3-B.2](P3B2_GROUNDING_ABSTENTION.md).
O resultado negativo abaixo corresponde ao prompt anterior, não ao estado final.

Data: 2026-10-02 (America/Bahia). **NÃO HOMOLOGADO LOCALMENTE** por erro factual
crítico de prazo em B. Integração técnica real funciona; não há homologação
de produção. Não foi iniciada P3-C, migrado SDK ou alterado Pyannote.

## Configuração e execução

Chave disponível no Worker, verificada somente como boolean. API recebeu apenas
o indicador de disponibilidade (override de ambiente Compose desta sessão,
sem escrever chave nem modificar `.env`). Provider efetivamente usado: Gemini,
modelo configurado e retornado na metadata persistida: `gemini-2.5-flash`.
Não se afirma um snapshot interno do modelo: o SDK não o registrou.
Schema version `1`, JSON mode, temperatura 0.1, budget de saída 16384 tokens,
limite de entrada 200000 caracteres, timeout de chamada 300s e job RQ 600s.
Retries de transporte desabilitados (`retry=None`), sem reparos ou replay de
inferência. Quatro chamadas concluídas: A, B, regeneração B, C.

Ambiente: desenvolvimento identificado `usagidev`, PostgreSQL `transcription_db`
no volume `usagidev_postgres_data`, Redis/RQ existente, matriz ML estável CUDA.
Cada fixture passou por upload HTTP → Whisper → Pyannote → Meeting → Gemini
real → polling → resultado PostgreSQL/API. Schemas e grounding literal válidos.
Somente o job RQ exato de cada análise foi apagado depois de finished;
resultado continuou idêntico via API. Todos os dados criados pelo drill foram
excluídos via endpoint ao terminar; backups e dados anteriores não foram tocados.

## Fixtures e evidências reproduzíveis

Roteiros imutáveis em `benchmarks/p3b1_fixtures.json`, geração local por
`benchmarks/generate_p3b1_audio.ps1`, vozes Microsoft Zira Desktop e Microsoft
Maria Desktop alternadas. Personagens Alice/Bruno são fictícios, sem pessoas,
clientes, organizações ou informações pessoais reais. Áudios e roteiros são
sintéticos; não se afirma que foram gravados por falantes humanos.
Áudios em `benchmarks/fixtures/p3b1/{A,B,C}.wav` (ignorados pelo Git).
Artefatos completos com segmentos realmente persistidos, conteúdo e revisões:
`benchmarks/results/p3b1/{A,B,C}.json`. Referências usam índice zero-based.
Não contêm chaves, senhas ou tokens de autenticação.

| Fixture | Intenção original | Duração | Speakers / segmentos | Caracteres |
|---|---|---:|---:|---:|
| A | Descrever sala de leitura; sem tarefas/decisões | 53.861s | 2 / 15 | 566 |
| B | Template azul aprovado; slides com Bruno até Friday; projetor sem owner/deadline | 74.815s | 2 / 25 | 804 |
| C | Sugestões sobre workshop/comparação, sem decisão ou compromisso | 78.768s | 2 / 21 | 838 |

Limitação importante do ensaio: roteiros em inglês sintetizados com uma voz
inglesa e outra portuguesa; Whisper está configurado em `pt`, não `auto`.
A transcrição apresentou traduções/mistura de idiomas e erros. Não se alterou
idioma, modelo, parâmetros ou áudio para favorecer o resultado. Ground truth
do roteiro e source realmente consumido pelo Gemini foram avaliados separadamente.

## Revisão factual manual item a item

Revisão humana realizada pela leitura dos segmentos persistidos e de todos os
itens, não por aceite automático de citação literal. Não houve walkthrough
visual de frontend nem escuta humana externa independente.

### A — discussão simples

- Summary: **suportado pelo transcript** (2–4, 10–11), mas **parcialmente
  suportado pelo roteiro**: “livro” veio da transcrição de “reading room”.
- Topic 0: **parcialmente suportado** (2, 6, 10). A frase ilegível “The Quiet
  Table Usarius Fall for Reading” foi elevada a um “conceito”; não é tópico
  inteligível no áudio planejado. Problema de source, com elaboração do modelo.
- Topic 1: **suportado** (3, 7, 13); áreas de leitura/conversa.
- Decisions/action_items/open_questions vazios: **suportados** por 4 e 11;
  não foram inventadas tarefas. Segmento 14 perdeu a negação original (“no
  action items” virou “Existem itens de ação”), mas Gemini não criou tarefas.
- Evidências literais corretas; referência 6 é tecnicamente válida, porém
  semanticamente fraca. Resultado não certifica qualidade da transcrição.

### B — tarefas e decisão, revisão 1

- Summary: **parcialmente suportado**; formato/decisão/tarefas têm suporte,
  mas “duas tarefas foram atribuídas” é impreciso para projetor sem owner.
- Topic 0: **suportado**, segmento 2.
- Decision 0: **suportado**, segmentos 8–9 declaram decisão final e template
  azul. Referência 10 está deformada e não acrescenta prova clara de aprovação.
- Action 0 descrição (slides): **suportada**, segmento 13.
- Action 0 responsável Bruno: **suportado**, 13–14, também 17.
- Action 0 prazo `domingo`: **NÃO SUPORTADO semanticamente**. Quote 14 diz
  “A pessoa responsável é Bruno e a hora de morte é domingo.” Isso não é
  declaração inequívoca de prazo dos slides. Segmento 13 diz “em fevereiro”,
  e 17 diz “will prepare the demonstration slides by Friday”. O modelo usou
  um fragmento de tempo fora de contexto e ignorou evidência conflitante.
  Grounding literal passou porque `domingo` ocorre em 14; é a falha crítica.
- Action 1 descrição (projetor): **suportada**, 18–19.
- Action 1 responsável `null`: **suportado**, ausência explícita em 19.
- Action 1 prazo `null`: **suportado**, ausência explícita em 19.
- Open questions vazias: não há afirmações a validar; possível omissão de
  pendência sobre atribuir o projetor, não invenção de conteúdo.

### B — regeneração, revisão 2

- Summary: **parcialmente suportado**, com subafirmação “para domingo”
  **não suportada** pelo compromisso dos slides.
- Topic 0 e Decision 0: **suportados**, mesmas ressalvas de evidência acima.
- Action 0: descrição/responsável **suportados**; prazo `domingo`
  **NÃO SUPORTADO**, repetição do erro da revisão 1.
- Action 1: descrição/responsável null/prazo null **suportados**. Quote 22
  é transcrição ruidosa; 18–19 são a base semântica suficiente.
- Open questions vazias: mesma observação da revisão 1.

Regeneração técnica aprovada: nova revisão 2, revisão 1 mantida e idêntica,
consulta da versão anterior durante pending/processing, uma única geração
ativa, request duplicado retornando o mesmo ID, versão 2 persistida,
ambas consultáveis depois da exclusão dos jobs RQ. Não significa melhoria
factual: o erro crítico permaneceu.

### C — ambiguidade

- Summary: **suportado**, 2–4, 8, 10–11, 14, 18, 20. Sugestões não viraram
  decisões ou tarefas.
- Topic 0: **suportado**, 2–3.
- Topic 1: **suportado**, 10.
- Decisions/action_items vazios: **suportados**, 4, 8, 14, 18, 20.
- Open question 0 (formato workshop): **suportado** pelo conjunto 2–4, 15.
- Open question 1 (necessidade de comparação): **parcialmente suportado**;
  source 15 está muito corrompido. O roteiro confirma a intenção, mas a quote
  isolada não demonstra inequivocamente a pendência. Evidência literal válida,
  semântica fraca. Melhor citar também contexto claro, quando disponível.

## Métricas observadas

Contagens extraídas de `response.usage_metadata`, latência da chamada via
`time.monotonic`. Polling inclui fila/SDK e intervalo de consulta, não somente
tempo do provider. Sem custo monetário estimado: projeto não registra base
de preço confiável para esse ensaio. Não se inventou preço de tabela.

| Execução | Latência SDK | Polling total | Input tokens | Output tokens | Total tokens SDK |
|---|---:|---:|---:|---:|---:|
| A | 10.386s | 12.078s | 1933 | 393 | 4162 |
| B v1 | 25.523s | 28.139s | 2615 | 525 | 5491 |
| B v2 | 13.913s | 16.115s | 2615 | 550 | 5760 |
| C | 9.005s | 12.068s | 2355 | 433 | 3930 |

Input total 9518, output candidates 1901, total SDK 19343. Total não é a
soma simples de input/candidates; o SDK pode incluir outras categorias
(por exemplo, reasoning). Categorias adicionais não foram instrumentadas,
portanto não se atribui automaticamente a diferença a uma categoria.
Quatro chamadas reais concluídas, zero retries automáticos, uma regeneração
explícita. Falha inicial da transcrição B não chamou Gemini nem gerou tokens.

## Defeito concreto corrigido e testes de falha

Primeira execução B falhou com ProgrammingError antes de Gemini. PostgreSQL
registrou `prepared statement "_pg3_0" already exists`. Supervisor RQ executa
recovery com SQLAlchemy; filhos herdavam sockets/pool e estado psycopg.
Correção pequena em `RecoveringWorker.main_work_horse`: `engine.dispose(close=False)`
antes de delegar ao RQ, criando conexões próprias sem fechar as do pai.
Não houve troca de Worker, fila ou serviço. B foi repetida com o mesmo áudio,
seguida por regeneração e C, sem novas falhas desse tipo. Registro inicial
preservado em `benchmarks/results/p3b1/B-initial-failure.json`.

Também adicionados logs numéricos de uso/latência, sem conteúdo/credenciais.
Nenhum prompt, contrato ou modelo foi alterado durante a avaliação para
melhorar as fixtures. Scripts são ferramentas explícitas de homologação,
não novos endpoints nem funcionalidades do produto.

- Provider indisponível: mock RuntimeError, failed sem resultado parcial,
  erro sanitizado e retry novo ID.
- Resposta inválida: JSON/schema/quote/ref/deadline/assignee mocks, rejeição.
- Timeout: mock TimeoutError, mesma persistência failed e sanitização.
- Credencial ausente: mock de configuração vazia, API 503 sem criar revisão
  e get_provider rejeita sem rede.
- Regressão do fork: teste verifica descarte `close=False` antes da execução.
- Suite completa: **142 passed, 11 warnings**, incluindo PostgreSQL/Redis/RQ
  isolados com provider fake. Testes específicos: **28 passed, 2 warnings**.
  Testes não geraram chamadas Gemini reais; não se confundem com este drill.

## Decisão e alterações necessárias

Integração de transporte/schema/persistência/revisões **validada localmente**.
Homologação factual **REPROVADA**: prazo incorreto semanticamente aceito em
B v1/v2. Referências literais não são garantia semântica; isso foi comprovado
com dados reais do pipeline, não hipótese.

Separação da causa:

1. **Source/configuração:** idioma `pt` com áudio sintético inglês/acento misto
   gerou erros relevantes e conflito Friday/fevereiro/domingo. Não é falha do
   transporte Gemini, nem se demonstra regressão Pyannote com este ensaio.
2. **Prompt/modelo:** faltou abstinência diante de tempo em outro contexto e
   conflito de prazos. O modelo escolheu domingo sem suporte de compromisso.
3. **Contrato/validação:** aceita prazo como expressão literal; não consegue
   provar relação semântica tarefa↔prazo apenas por substring. Schema permanece
   útil, mas insuficiente para certificar ausência de hallucination.

Menor correção recomendada: instruir explicitamente abstinência (`null`) para
responsável/prazo ambíguo, conflitante ou citado em outro contexto; considerar
todo o transcript para conflitos, sem corrigir por suposição. Cobrir com uma
regressão semântica documentada, sem regras especiais para “domingo” ou esta
fixture. Se aprovada e implementada, reavaliar o MESMO source B congelado e
novamente o fluxo de áudio relevante. Não prometer que mudança de prompt
garante a solução; manter revisão humana.

Não houve chamadas adicionais após o erro nem repetição cobrada até obter
um resultado favorável. Melhorar fonte de áudio/idioma exige ensaio explícito
separado; não substituir estas fixtures e apagar o resultado negativo.
Produção continua NÃO homologada. A decisão de homologação local permanece
negativa até tratamento e nova validação factual do bloqueio.
