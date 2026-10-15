# Whisper small / pipeline completo — evidência local e gates de VPS

Data: 2026-10-14. Base `origin/dev 79b99ea` após fetch; PR #25 e PR #18 integrados.
Task existente: <https://trello.com/c/iDDtYreC>.

**Decisão: NÃO APROVADO PARA BETA nesta homologação.** Usuário confirmou que não
há VPS. Preparação remota e ensaios locais foram realizados, não homologação de
VPS ou produção. Nenhum provider padrão, permissão real, plano, franquia ou
configuração de desenvolvimento foi promovido. Pyannote 4 não foi utilizado.

## Ambiente realmente medido

| Item | Observado |
|---|---|
| Host | Windows, Ryzen 5 7600X, 6 cores / 12 threads |
| RAM física | 16.229.769.216 bytes (~15,12 GiB) |
| Runtime | Docker Desktop Linux/WSL2, kernel 6.18.54.1-microsoft-standard-WSL2 |
| RAM visível Linux | 7.858.864.128 bytes (~7,32 GiB), compartilhada com outros serviços locais |
| GPU host | RTX 3060 12.288 MiB, driver 616.64; **não exposta nem usada** pelos ensaios CPU |
| Worker | Imagem estável reutilizada, base CUDA histórica; execução real CPU |
| Faster-Whisper / CTranslate2 | 1.2.1 / 4.8.2 |
| Torch / Pyannote.audio / RQ / psutil | 2.2.2 / 3.3.2 / 1.16.2 / 7.2.2 |
| Compute | Configurado `int8`; inspeção do Native CT2 confirmou `cpu` / `int8_float32` |
| ASR | small multilíngue, pt forçado, beam 1, 2 threads, VAD off, contexto anterior off, janelas 300s |
| Diarização | speaker-diarization-3.1, CPU, auto-count, filtros existentes 0s/-100dBFS, cache autorizado offline |

Imagem Worker utilizada:
`sha256:8f4131827fc760f54b0e00f2e308f4e64aeed3bcdbd394800f128c487e4a5c78`.
Imagem API:
`sha256:d209b63558d5cce0ad5af4a5a760fc530b026d3149df14c00370275b97d54352`.
Código montado readonly da branch da Task; imagens não foram reconstruídas ou
promovidas. API segue separada dos modelos. A imagem Worker CPU ainda carrega
dependências CUDA no disco; isso não significa inferência GPU.

Pesos small: revisão `536b0662742c02347bc0e980a01041f333bce120`, model.bin
483.546.902 bytes, SHA-256
`3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671`.
Hash conferido igual à proveniência do PR #18; não houve novo download.
Model load inclui imports/runtime; download inicial ficou fora e não foi medido.

## Dataset e qualidade

Áudios públicos: FLEURS pt_br CC-BY-4.0, revisão e preparação em
[fixtures](../../modules/backend/benchmarks/fixtures/README.md). Referências
human-supervised separadas, não saídas do modelo. WER/CER seguem o mesmo
`metrics.py` do PR #18: NFC/minúsculas, pontuação removida, hífens preservados,
CER sem espaços. Pontuação não é avaliada por esses escores.

| Cenário | Duração | WER | CER | Limite / revisão crítica |
|---|---:|---:|---:|---|
| FLEURS quality, pipeline sem falantes, n=3 | 77,68s | 4,41% | 0,69% | Fala lida, não valida reunião/identidade de um único speaker |
| FLEURS 6m, beam1, coortes 1/2/3 Workers, n=3 cada | 368,89s | 13,59% | 8,16% | Diferença relevante versus engine isolado; revisão de nomes/números/negações pendente |
| FLEURS 6m, comparação explícita beam5, n=3 | 368,89s | 13,29% | 9,35% | Beam isoladamente não recupera qualidade; não promover |
| FLEURS alternado com Pyannote, n=3 | 62,54s | 0,00% | 0,00% | Duas vozes controladas, 84 palavras; não é reunião natural ou prova de qualidade geral |
| Trecho autorizado de vídeo, n=3 | 900s | **desconhecido** | **desconhecido** | Sem referência/idioma revisados; apenas performance, áudio/texto/métricas brutas privados e ignorados |

O conjunto mínimo pedido **não está completo**: faltam reunião natural PT-BR,
ruído, sotaques anotados, vocabulário profissional/entidades e overlap natural
com transcrição humana validada. AMI é inglês; FLEURS é fala lida. Não se declarou
ausência de erros críticos sem revisão humana. Não foram enviados áudios a APIs.

### Explicação da diferença com PR #18

O PR #18 mediu engine isolado, beam5, idioma automático, contexto anterior ligado
e áudio inteiro. Produto usa contexto desligado/janelas300/pt/beam1. Não eram
configurações equivalentes. Um diagnóstico pareado com os mesmos PCM/pesos:

| Política (uma inferência por caso, NÃO benchmark estatístico) | WER | CER |
|---|---:|---:|
| Política atual, janela300, pt, beam1, contexto off | 13,59% | 8,16% |
| Só retirar corte300, demais iguais | 10,93% | 6,25% |
| Áudio inteiro + contexto anterior on, pt/beam1 | 5,76% | 1,62% |
| Política histórica inteira/auto/beam5/contexto on | 6,35% | 2,58% |

A última reproduz o resultado histórico exato. Há evidência de diferença de
política de decoding/chunking, não de mudança de pesos ou erro de scoring.
Não prova que contexto on seja seguro/melhor em reuniões/ruído: pode propagar
texto incorreto. Nenhum parâmetro do produto foi alterado para favorecer fixtures.
O diagnóstico fica reproduzível em `compare_decode_policy.py`; hipóteses não
são publicadas. Aprovação de qualidade permanece pendente.

## Performance da jornada

Medição real: login HTTP, upload/objeto/reserva/banco, Redis/RQ, work horse,
conversão, ASR/Pyannote, segmentos+Meeting persistidos e consulta HTTP. Não houve
walkthrough visual novo: disponibilidade de resultado foi verificada pela API.
Medição de UI/servidor real continua no gate de homologação.

Medianas de 3 jobs; RSS é por work horse, não RAM total da máquina. Todos carregam
modelos em **novo processo**, com cache existente. Não há warm residente no Worker.

| Cenário | Init engines | ASR | Falantes | Worker total | HTTP total | RTF Worker | RSS pico máximo |
|---|---:|---:|---:|---:|---:|---:|---:|
| FLEURS77s, 1 Worker/1 submissão | 3,27s | 8,30s | off | 12,06s | 12,37s | 0,155 | 1.015 MiB |
| FLEURS369s, 1 Worker/2 submissões | 5,08s | 39,29s | off | 44,55s | 86,44s | 0,121 | 1.010 MiB |
| FLEURS369s, 2 Workers/2 submissões | 6,30s | 58,35s | off | 65,00s | 65,27s | 0,176 | 1.010 MiB |
| FLEURS369s, 3 Workers/3 submissões | 7,12s | 77,57s | off | 85,06s | 85,79s | 0,231 | 1.010 MiB |
| FLEURS369s, beam5, 1 Worker | 6,27s | 45,99s | off | 52,58s | 53,28s | 0,143 | 1.066 MiB |
| FLEURS63s com Pyannote, 1 Worker | 8,34s | 25,95s | 80,15s | 114,78s | 115,14s | 1,835 | 2.861 MiB |
| Trecho autorizado900s, 1 Worker | incluído | 74,31s | off | 79,12s | 79,97s | 0,088 | 1.154 MiB |

Valores completos de conversão/persistência/upload/fila/CPU/temporários e
dispersão por observação: [CSV público](evidence/pipeline-local-results.csv).
Em 77s, init variou 3,04–8,74s e Worker11,57–17,34s; não se limpou cache do OS.
O WAV de900s ocupa28,8MB; campo temporary_bytes não é pico de disco total/spool.
`upload_seconds` é roundtrip de admission, não transferência isolada.

### Concorrência e capacidade

| Workers / submissões | RAM limite por Worker | CPU quota total | Coorte total | Throughput observado |
|---|---:|---:|---:|---:|
| 1 / 2 | 6.400 MiB | 2 CPUs | 135,76s | 489,10 minutos de áudio/h |
| 2 / 2 | 2.800 MiB | 4 CPUs | 116,42s | 570,35 minutos de áudio/h |
| 3 / 3 | 1.800 MiB | 6 CPUs | 90,27s | 735,57 minutos de áudio/h |

Mesmo **usuário sintético**, permissões beta/concorrência explícitas; isolamento
entre contas foi testado na suíte, não nesta campanha multiusuário real.
1 Worker teve esperas RQ0,009s/44,59s/40,47s; 2/3 Workers iniciaram sem fila
significativa. Cada resultado tinha uma tentativa no ledger, reserva consumed,
PostgreSQL completed e RQ finished. Não se observou OOM nesses jobs ASR.

Não interpretar throughput como capacidade sustentada ou extrapolar para VPS.
CPU total cresce entre cenários; não é comparação com vCPUs fixas. Máquina teve
outros serviços/testes/builds; coortes 2 Workers/beam5/Pyannote/diagnóstico têm
carga compartilhada. Diarização concorrente não foi testada. Não multiplicar
throughput de ASR por mês para definir franquias.

`monitor_stack.py` gerou CSVs locais de CPU/memória container. Capturou ~200% CPU
por Worker sob quota2; amostragem de 2/3 Workers terminou incompleta quando
containers/driver foram recriados/removidos. Esses CSVs não provam pico agregado
completo, ausência universal de OOM ou estabilidade de servidor. Refazer sem
recriação/carga paralela na VPS. RSS e Docker memory não são valores equivalentes.

## Diarização

Três execuções combinadas CPU:2 speakers/12 segmentos/84 palavras, sem marcador
de erro de segmento. Tempo adicional63,62–83,39s; RSS2.746–2.860MiB. A primeira
configuração de cache incompleta gerou falhas, não resultados válidos: faltava
`PYANNOTE_CACHE` no harness. Correção reutiliza o cache autorizado offline; sem
download, token real, troca de modelo ou ajuste de clustering.

**DER não calculado nesta campanha:** não há RTTM humano correspondente às
fixtures PT-BR. Contagem2 não é DER/cobertura/overlap/speaker confusion validado.
DER AMI histórico e protocolo collar0,25s/overlap incluído permanecem em
[validação ML](../../docs/ml_validation.md) e relatório PR #18, sem nova medição
disfarçada de resultado desta Task. Diarização CPU é executável localmente, mas
sua latência/custo em VPS e qualidade de reunião brasileira não estão aprovados.

## Falhas e integridade

| Caso real isolado | Observado |
|---|---|
| Assinatura inválida | Admission rejeitada, sem inferência |
| RIFF truncado | PostgreSQL failed / RQ failed / reserva released / uma tentativa |
| Silêncio digital20s, antes | 223 palavras inventadas, completed; defeito confirmado |
| Mesmo silêncio, depois | 0 palavras, completed/finished; nenhuma inferência sobre PCM zero |
| Timeout RQ3s por job sintético | PostgreSQL failed / RQ failed / reserva unknown; recovery0; tentativa permanece1 |
| Input ausente antes do Worker | PostgreSQL failed / RQ failed / reserva released; recovery0; tentativa1 |
| Redis parado na stack de falhas | POST503 antes do parsing; total de jobs inalterado; Redis/Worker restaurados |
| Limites campanha | HTTP429 real; nenhum contador apagado ou segurança desabilitada |

Timeout global3s foi rejeitado corretamente pela configuração (mínimo60s).
O teste válido usa override de um job novo, sem enfraquecer política global.
Os probes rodam em stack/banco/Redis próprios; não tocaram nos dados reais.
Remover o RQ terminal de3 jobs públicos preservou os segmentos/resultados HTTP.
Ledger P5-05 e reservas originais são reutilizados, sem novo ledger ou cobrança.

Correção de produto mínima: janelas PCM **exatamente zero** não chegam ao
Whisper. Não introduz limiar RMS, VAD ou filtro que descarte fala baixa não zero;
três regressões cobrem silêncio, amplitude baixa e fala após janela silenciosa.
Ruído/não fala não zero ainda pode alucinar: não anunciar problema geral resolvido.

Cancelamento operacional, kill abrupto/restart durante inferência, OOM controlado,
starvation prolongada e perda de PostgreSQL não foram novamente medidos com
inferência nesta campanha. Há regressões existentes com mocks/PG/RQ, mas ensaio
no servidor final permanece obrigatório. Não declarar exatamente-uma-vez universal.

## Custos e limites

VPS/storage/backup/egress: **desconhecidos**, servidor não escolhido/provisionado.
AssemblyAI: nenhuma chamada, autorização paga ausente. API local não ter cobrança
por chamada não torna infraestrutura gratuita. Catalog P5-05 permanece vazio
sem preço verificado; eventos locais mantêm origem local e custo desconhecido.

Reutilizar `cost_model.py` e ledger para cenários explícitos, nunca um ledger novo.
Exemplos de demanda para simulação, não comportamento real nem franquias:
leve30min/mês, médio3h/mês, pesado20h/mês. Preencher custos e capacidade **medidos
na VPS**; custo/hora entregue = custo mensal total / horas realmente entregues,
incluindo ociosidade. Baixa/média/alta ocupação não ganham valor monetário antes
do servidor/preço/faturamento conhecidos. Não extrapolar Ryzen para vCPU compartilhada.

Recomendação apenas para próximo ensaio: começar com1 Worker; detecção de falantes
opcional, medir separadamente; 8GB RAM é alvo de teste, não mínimo homologado.
Testar 2 Workers só com orçamento agregado de RAM/CPU e dataset representativo.
Não recomendar duração/tamanho/timeout/franquia comercial definitivos com estes
dados. Não habilitar processamento Free ou fallback AssemblyAI.

## Validação de código

- Backend atual560 passed/2 skips/14 warnings, PostgreSQL/Redis/RQ descartáveis;
  os2 skips FFmpeg passaram separadamente no Worker.
- 34 testes engine/filtros/audio passaram na imagem Worker, incluindo3 novos de
  silêncio. Sem modelos reais nesses testes.
- Frontend298 testes/38 arquivos, lint e build passaram; nenhuma UI alterada.
- 45 testes stdlib do benchmark, compileall, Alembic upgrade/check, Compose quiet
  e diff-check passaram. Avisos de depreciação existentes permanecem.
- Builds ML novos, scanner completo de dependências e inferência GPU não foram
  executados/promovidos. Não resolver stack Torch vulnerável fora deste escopo.
- Security Gate e CI do PR devem ser consultados no PR/Trello; são diferentes
  da homologação de infraestrutura/qualidade.

## Próxima ação / gates pendentes

1. VPS Linux real autorizada; registrar hardware/contrato/limites/preços, sem
   extrapolação. Executar harness com CPU/RAM total fixos e carga isolada.
2. Reuniões PT-BR autorizadas com revisão humana e RTTM quando houver speakers;
   revisar entidades, valores, datas, negações, omissões e alucinações.
3. Definir critérios de qualidade/fila/custo junto ao uso do Beta e testar políticas
   de decoding em vários cenários, sem tuning de uma fixture.
4. Cold/download/cache/load separados,3 repetições, multiusuário, longos, falhas,
   headroom e capacidade sustentável. DER com protocolo documentado.
5. Revisão humana go/no-go antes de habilitar local no ambiente de Beta. Card não
   deve ir para Validação de homologação apenas porque o CI do harness passou.
