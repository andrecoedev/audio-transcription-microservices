# Matriz ML e critérios de validação

## Padrão suportado

| Componente | Matriz estável | Candidata histórica, não promovida |
|---|---|---|
| Torch / Torchaudio | 2.2.2 / 2.2.2 | 2.10.0 / 2.10.0, CUDA 12.8 |
| Torchvision | 0.17.2 | 0.25.0 |
| Pyannote.audio / core | 3.3.2 / 5.0.0 | 4.0.7 / 6.0.1 |
| TorchCodec | Não requerido pelo caminho atual | 0.10.0 |
| Diarização | speaker-diarization-3.1 | speaker-diarization-community-1 |
| Faster-Whisper / CTranslate2 | 1.2.1 / 4.8.2 | Mantidos nos ensaios |
| Base estável Docker | CUDA 12.3.2 / cuDNN 9 | Overlay descartável, não imagem suportada |

Compose nunca seleciona a candidata. Seu Dockerfile/pins e JSONs de ensaio estão
arquivados localmente; originais no commit 84ea885. A pequena fronteira de
compatibilidade no engine permanece por uso atual e testes de preservação de
tracks. Não implica homologação de Pyannote 4.

Torchvision não tem import direto no produto, mas permanece no triplet avaliado:
remover/upgradear um membro isoladamente não é limpeza segura da matriz.
Librosa processa segmentos Pyannote; pydub continua necessário para AssemblyAI.
aiofiles serve uploads. Nenhum desses é dependência morta.
Requisitos Worker também contêm ferramentas de teste; mantidos para suíte completa.
A declaração duplicada de httpx foi preservada nesta limpeza: removê-la invalidava a camada de dependências e resolvia novamente versões transitivas não fixadas. A matriz instalada deve permanecer inalterada; consolidar o manifest exige uma validação própria do lock de dependências.

Um rebuild descartável com o manifest original também resolveu 11 versões
transitivas diferentes da imagem instalada, pois ainda não há lock completo.
Essa imagem não foi promovida. A suíte de limpeza e o smoke de desenvolvimento
utilizaram a matriz instalada: 176 pacotes, sem mudança de versão. Build com
sucesso não significa homologação dessas novas resoluções; reprodutibilidade
das dependências permanece uma dívida operacional separada.

## Reproduzir qualidade sem tuning de fixtures

Ferramentas permanentes em modules/backend/benchmarks:
- benchmark_transcription: pipeline atual, stages/RTF/RAM/VRAM/temp files.
- benchmark_stability: jobs sequenciais e memória.
- evaluate_transcript: WER/CER contra referência humana.
- compare_results: mesma fixture/hash, hardware e configuração.
- prepare_fleurs_fixtures / prepare_ami_diarization_fixtures: datasets públicos.
- generate_synthetic_fixture: apenas smoke técnico de decode, não qualidade.
- benchmark_diarization_robustness / compare_diarization_runs: DER, tracks e scoring.

Áudio/referências/RTTM/manifest gerados ficam ignorados. Ver
[origem/licenças e preparação](../modules/backend/benchmarks/fixtures/README.md).
FLEURS PT-BR usa referência humana, não saída do modelo. AMI ES2004a contém
clean/unequal volume/rapid turns/overlap/far-field/four speakers.
Use mesmo áudio, reference RTTM, duração, collar 0.25s, overlap incluído,
speaker mapping, parâmetros de clustering e pós-processamento. Compare modo
automático e known-count. Não ajustar parâmetros para favorecer uma fixture.
GPU isolada, Workers sequenciais; GPU-total inclui outros processos e não é VRAM
privada. Torch peak allocation fornece outra medida, não valor equivalente.

## Baseline e decisão preservadas

Filtros antigos 0.5s/-40 dBFS descartavam fala curta/distante legítima.
Padrões atuais MIN_SEGMENT_DURATION=0 e SILENCE_THRESHOLD=-100 preservam tracks;
sem merge/batching/mudança de modelo nesta revisão.

Comparação local registrada sob scoring equivalente:

| Fixture AMI | DER automático estável → candidata | DER known-count estável → candidata |
|---|---:|---:|
| Clean 2 speakers | 22.639 → 18.769% | 18.769 → 18.769% |
| Unequal volume | 36.813 → 35.358% | 35.358 → 35.358% |
| Rapid turns | 15.207 → 14.939% | 15.207 → 21.862% |
| Overlap | 18.698 → 13.818% | 13.901 → 13.818% |
| Far-field | 33.718 → 16.905% | 23.705 → 16.905% |
| Four speakers | 12.079 → 12.506% | 10.707 → 24.609% |

Nas 12 inferências candidatas, tracks nativos e adaptação start/end/speaker
coincidiram; filtros/clipping preservaram segmentos. Rescoring no mesmo runtime
reproduziu DER. Não foi demonstrada perda de integração/configuração/eval;
diferença está no output/clustering do modelo, com regressão known-count relevante.

| Automático | RTF estável → candidata | RAM pico MB | Torch peak CUDA MB |
|---|---:|---:|---:|
| Clean, primeiro/cold | 0.131 → 0.263 | 1818 → 2229 | 9321 → 10703 |
| Rapid turns | 0.037 → 0.043 | 1799 → 2209 | 1629 → 1630 |
| Four speakers | 0.055 → 0.088 | 1858 → 2249 | 1629 → 9726 |

Não houve OOM nesse ensaio, mas há gate de headroom/repetibilidade em GPU 12GB.
CPU/INT8 combinado candidato registrado: fixture PT-BR 62.54s, processamento
141.56s, RTF 2.263, RAM 4240MB, 2 speakers/12 segmentos/84 palavras.
Não é endorsement de performance nem foi rerodado nesta limpeza.

**Não promover** até resolver regressões/memória e revalidar stack conjunta,
qualidade PT-BR WER/CER, speakers/timestamps, 3 jobs, CPU/INT8, GPU/FP16 e scanners.
23 advisories Torch e wheels CUDA não escaneados continuam riscos documentados
em [segurança](security.md). Reduzir scanner findings não justifica piorar qualidade.

## Evidência operacional versus produção

Smokes históricos estáveis validaram HTTP com/sem diarização, CUDA e fixture
pública PT-BR: 12 segmentos/2 speakers. Probe longo 45s manteve heartbeat (~1.7s),
timeout 3s marcou PostgreSQL/RQ failed; kill/restart aguardou abandono sem execução
paralela e recuperou 1 job em 2 tentativas. Não prova exatamente-uma-vez universal.

Nesta limpeza, testes usam mocks; nova inferência GPU paga ou promoção não foi
realizada. Baselines históricas não são métricas de uma nova execução.
Produção permanece não homologada.
