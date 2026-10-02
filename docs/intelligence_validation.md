# Avaliação factual local do Gemini

## Escopo

Gemini real gemini-2.5-flash, SDK legado, schema_version 1.
Homologação **local e limitada** sobre três reuniões sintéticas sem dados pessoais
reais. A simples: duas vozes/assuntos, sem tasks necessárias. B: decisão, duas
tarefas, responsável/prazo explícitos versus ausentes. C: sugestões/ambiguidade.

Ensaios originais passaram por upload → Whisper/diarização estáveis → Meeting →
Gemini → polling → PostgreSQL. Depois da remoção do job RQ, resultado persistiu.
Regeneração criou nova revisão e preservou anterior durante execução.
Vozes TTS em inglês com Whisper configurado para pt geraram transcript ruidoso;
não houve alteração de áudio/idioma/modelo para favorecer os resultados.

## Falha factual e correção

Revisão literal aceitou domingo no fragmento corrompido do segmento 14 de B.
A tarefa de slides tinha fevereiro em 13 e Friday em 17; o fragmento de 14
não prova prazo da tarefa. B original e sua regeneração inventaram esse prazo.
Logo transporte/schema/provenance válidos não significaram homologação factual.

A original elevou trecho ilegível a um conceito; C tinha evidência contextual
fraca para uma pendência. Esses resultados negativos foram preservados.
Prompt/schema reforçados pedem contexto global, abstinência em conflito/ruído,
vínculo explícito tarefa-owner-prazo e resumo sem reintroduzir fato descartado.
Sem regra especial para domingo/fixture, sem correção automática do transcript.

Reavaliação usou sources congelados e inalterados, não novo upload/ASR.
B v1 ainda colocou prazo incorreto no resumo; B v2 usou prompt anterior em cache
do processo. Ambas foram contabilizadas como chamadas reais, não aprovação.
B v3/v4 usaram prompt final idêntico; A/C tiveram uma execução final cada.

## Revisão semântica final

| Campo/fixture | Resultado | Evidência/limite |
|---|---|---|
| B decisão | Modelo azul | Segmentos 8–9 sustentam decisão final |
| B tarefa slides | Presente | 13/17 sustentam compromisso |
| B responsável slides | Bruno | 13/17, independente do trecho ruidoso 14 |
| B prazo slides | null | Abstinência correta diante de conflito/ruído |
| B tarefa projetor | Presente | 18–19 sustentam tarefa |
| B responsável/prazo projetor | null/null | Ausência explícita em 19 |
| B resumo | Não reintroduz domingo/Friday como prazo escolhido | v3/v4 coerentes nos campos críticos |
| B tópicos | Formato/modelo | 2–3, ruído residual de source reconhecido |
| B open questions | [] | Sem invenção; não prova completude |
| A | Sem decisões/tasks/open questions inventadas | Tópicos têm apoio contextual; resumo herda livro do ASR |
| C | Sem decisões/tasks inventadas | Suggestions permanecem discussion; duas pendências com contexto |

Evidence em B inclui redundância/ruído auxiliar (10/14/22), não prova perfeita
de cada quote isolada. Responsabilidade/prazo/decisão se sustentam no conjunto
dos segmentos claros. Em A, conduzida por Alice e Bruno é mais forte que
participação; ressalva não crítica. Resumo não certifica fidelidade ao áudio.
Não considerar referências literais como prova automática de interpretação.

Requests duplicados reutilizaram geração ativa. Revisões anteriores continuaram
idênticas e disponíveis; nova revisão persistiu. Resultado continuou idêntico
após excluir cada job RQ específico.

## Métricas históricas (não nova execução)

Primeiro ensaio: 4 requests reais, incluindo regeneração B; sua falha factual
não foi escondida. Reavaliação: 6 calls, duas intermediárias + quatro finais.
Retries automáticos = 0.

| Reavaliação | SDK latência | Input/output tokens | Total SDK |
|---|---:|---:|---:|
| B v1, reprovada | 64.149s | 3362 / 837 | 6306 |
| B v2, prompt anterior | 12.827s | 3362 / 907 | 6013 |
| B v3, final | 12.673s | 3504 / 731 | 6261 |
| B v4, repetição | 13.191s | 3504 / 750 | 6379 |
| A final | 8.481s | 2822 / 401 | 4498 |
| C final | 21.809s | 3244 / 947 | 8095 |

Total reavaliação: input 19798, output candidates 4573, SDK 37552. Não presumir
que total é input+output, pois outras categorias não foram instrumentadas.
Não calcular custo sem base confiável configurada. Nenhuma nova chamada paga
na limpeza; testes de falha usam mocks/credencial ausente.

## Decisão e reprodução

**P3-B/P3-B.2 homologadas localmente dentro desses critérios**, não ausência
universal de hallucination. Amostra pequena/provider não determinístico, ASR
ruidoso, evidências redundantes e sem ensaio adversarial amplo exigem revisão
humana e nova avaliação após mudança de prompt/modelo/SDK.
P3-A validada localmente; produção não homologada; Pyannote 4 não promovido.

Artefatos completos positivos/negativos, scripts one-off e roteiros foram
arquivados em .local-artifacts/archive/modules/backend; podem também ser
consultados nos commits 9c4ab15 (Gemini) e 012df9d (implementação final).
Fixtures inline/parametrizadas permanentes nos testes continuam protegendo
schema/grounding/nulls/erros e fronteiras, mas mocks não demonstram raciocínio
semântico do LLM. Smoke genérico scripts/smoke_http_dev.py permanece suportado.
