# Transcrição local CPU × GPU — experimento USAGI

Data: 2026-10-08. Ambiente de desenvolvimento, não homologação de produção.
Nenhum áudio foi enviado a AssemblyAI, Gemini, Groq ou outra API de inferência.
Nenhum provider, regra Guest ou configuração de processamento do produto mudou.

## Ambiente e proveniência

| Item | Detectado |
| --- | --- |
| CPU | AMD Ryzen 5 7600X, 6 núcleos / 12 threads |
| RAM física | 16 GiB DDR5, 4.800 MT/s; Windows utilizável: 15,12 GiB |
| Ambiente ML | Docker Desktop/WSL, memória visível: 7,32 GiB; limite não alterado |
| Sistema | Windows 11 Pro, build 26200 |
| GPU | NVIDIA RTX 3060, 12.288 MiB, WDDM |
| Driver | 616.64; `nvidia-smi` anuncia compatibilidade CUDA 13.4, não um toolkit instalado |
| Faster-Whisper | 1.2.1, CTranslate2 4.8.2, Python 3.10 no container |
| Whisper.cpp | release b5454, revisão d1be6fde11ac6e0407606b4e42fe72d34add8037, Windows nativo, DLLs CUDA 12.4 |
| Pyannote | `speaker-diarization-3.1`, pyannote.audio 3.3.2, Torch 2.2.2+cu121 |
| cuDNN | Torch informa 8.9.2; runtime CTranslate2 usa bibliotecas cuDNN 9 da imagem |
| Instrumentação | Python 3.14 nativo, psutil 7.2.2; 6 threads de inferência |

Imagem reutilizada somente em containers descartáveis:
`sha256:17cfc35863f97c82aeb72c416c551494975d9912af612484b140c83617ad5717`.
A imagem estável do aplicativo e a candidata Pyannote 4 não foram alteradas.
O ZIP oficial do whisper.cpp teve SHA-256 conferido contra o digest do asset:
`afef0b881c500958921c3f5523b50e59ee2ec9b6f5cbd25b324c51ed308a957a`.

Modelos públicos foram baixados antes dos testes; modelos Pyannote já aceitos
foram obtidos após autorização expressa, sem aceitar novos termos. O downloader
usou exclusivamente HF_TOKEN, sem salvar ou imprimir a credencial. Inferências
Docker usam `--network none`; o servidor C++ escuta somente em loopback.
Scripts finais montam apenas experimento, fixtures, modelos e diretório de saída.

## Método e limites de interpretação

Três processos/sessões novos por combinação. Cada sessão mede uma inferência
**cold** e outra **warm**, com modelo residente. Cold não significa boot frio:
cache do sistema/disco não foi limpo. Nenhum segundo benchmark de inferência foi
executado simultaneamente; aplicativos de desktop e serviços ociosos continuaram
em execução. Não se trata de uma GPU sem desktop ou de servidor dedicado.

Faster-Whisper: CPU INT8 / CUDA FP16. Whisper.cpp: pesos GGML F16, runtime de
precisão mista, CPU `--no-gpu` / backend CUDA e alocações explicitamente verificados.
Beam/best-of 5, temperatura zero, VAD desligado e idioma automático. Os engines
têm kernels, flash attention e defaults de decoding diferentes; Windows nativo
versus Docker também é variável. A comparação é entre configurações de implantação,
não uma prova de equivalência numérica ou superioridade intrínseca de biblioteca.

- RTF = tempo efetivo de inferência / duração. Velocidade = 1/RTF.
- Load/startup inclui inicialização de runtime, imports, CUDA ou readiness C++;
  não isola leitura dos pesos. CSV distingue esse escopo.
- Total = conversão + inferência + startup no cold; no warm reutiliza o custo
  de conversão medido, sem refazer o WAV. Upload, fila, download e API não entram.
- RSS/CPU por árvore de processos e VRAM total por `nvidia-smi` foram amostrados;
  incluem carregamento e as duas inferências da sessão, podendo perder transientes.
  C++ mede o processo servidor, não o wrapper. CPU somada pode exceder 100%.
- VRAM total inclui desktop; delta é aproximação, não VRAM privada. Variação
  de VRAM em testes CPU não comprova inferência GPU. Pyannote também mede Torch.
- Mediana, mínimo, máximo e MAD (mediana dos desvios absolutos) estão no resumo.
  Três observações não sustentam intervalo estatístico robusto ou SLA.

## Fixtures e qualidade

FLEURS `pt_br`, revisão `70bb2e84b976b7e960aa89f1c648e09c59f894dd`, CC-BY-4.0:
77,68 s de qualidade; 368,89 s representativos; 62,54 s de vozes alternadas.
São leituras públicas, com referências humanas, não reuniões espontâneas.
A fixture de duas vozes é montagem controlada, sem overlap. A origem e
reprodução estão no [README das fixtures](../../modules/backend/benchmarks/fixtures/README.md).

WER/CER usam a normalização já adotada pelo projeto: NFC/minúsculas, pontuação
removida, hífens preservados; CER sem espaços. Não se inventou referência para
o vídeo privado. Idioma e segmentação vêm de cada engine, sem edição para
favorecer resultados. Qualidade de detecção de falantes é DER separado.

Durante a preparação, o verbose JSON C++ revelou quebras de apresentação dentro
de palavras. Isso inflava WER no adaptador. A correção concatena os textos dos
segmentos nativos, sem inserir separadores. Rescore preservou saídas originais,
tempos e configurações; não corrigiu a transcrição com base na referência.
Testes permanentes protegem essa distinção e a recusa de fallback CPU em CUDA.

### Comparação real: PT-BR 77,68 segundos

Medianas de três sessões. FW = Faster-Whisper; C++ = whisper.cpp.
WER/CER em %. Inferência warm entre parênteses é MAD, em segundos.
Load é a inicialização observada, não apenas disco. Total cold inclui conversão.

| Engine | Modelo | Execução | Load s | Inferência cold s | Warm s (MAD) | Total cold s | WER | CER |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| FW | tiny | CPU INT8 | 0,68 | 2,18 | 1,75 (0,00) | 3,10 | 17,65 | 5,42 |
| FW | tiny | CUDA FP16 | 0,92 | 1,68 | 1,32 (0,03) | 2,68 | 16,18 | 5,00 |
| FW | base | CPU INT8 | 1,09 | 4,08 | 4,17 (0,03) | 5,24 | 13,24 | 3,19 |
| FW | base | CUDA FP16 | 1,13 | 1,96 | 1,53 (0,02) | 3,20 | 11,03 | 2,08 |
| FW | small | CPU INT8 | 5,81 | 11,64 | 12,76 (1,80) | 18,84 | 3,68 | 0,69 |
| FW | small | CUDA FP16 | 2,80 | 2,92 | 2,49 (0,06) | 5,80 | 5,88 | 1,25 |
| FW | medium | CPU INT8 | 17,08 | 37,23 | 34,68 (4,96) | 56,27 | 4,41 | 0,83 |
| FW | medium | CUDA FP16 | 18,82 | 4,63 | 4,43 (0,18) | 23,67 | 5,15 | 1,25 |
| C++ | tiny | CPU F16 | 0,55 | 3,88 | 3,75 (0,12) | 5,37 | 19,12 | 5,97 |
| C++ | tiny | CUDA F16 | 1,24 | 2,46 | 2,09 (0,04) | 5,10 | 16,18 | 5,42 |
| C++ | base | CPU F16 | 7,82 | 7,75 | 7,63 (0,61) | 17,39 | 12,50 | 2,22 |
| C++ | base | CUDA F16 | 1,24 | 2,25 | 1,99 (0,00) | 5,03 | 11,03 | 2,64 |
| C++ | small | CPU F16 | 2,96 | 20,24 | 20,44 (0,83) | 24,16 | 6,62 | 1,25 |
| C++ | small | CUDA F16 | 1,25 | 2,53 | 2,44 (0,04) | 4,54 | 6,62 | 1,25 |
| C++ | medium | CPU F16 | 7,80 | 57,58 | 67,93 (3,68) | 65,78 | 5,15 | 0,42 |
| C++ | medium | CUDA F16 | 8,63 | 5,56 | 5,89 (0,31) | 16,69 | 5,15 | 0,42 |
| FW | large-v3 | CUDA FP16 | 32,08 | 6,34 | 5,78 (0,08) | 38,46 | 5,88 | 1,39 |

O WER melhor do small CPU não demonstra que INT8 melhora modelos em geral;
é resultado deste áudio e configuração. Large-v3 completou três sessões sem
falha, mas não melhorou esta referência curta. Large-v3 CPU e C++ large-v3
**não executados**: fora da matriz prioritária e sem prolongar a ampliação sob
16 GiB/WSL 7,32 GiB. Não foram declarados incompatíveis nem se inventou OOM.

### Comparação real: PT-BR 368,89 segundos

| Engine/modelo | Execução | Warm s (MAD) | RTF | Velocidade | WER % | CER % |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| FW small | CPU INT8 | 67,04 (2,25) | 0,1817 | 5,50× | 6,35 | 2,58 |
| FW small | CUDA FP16 | 11,55 (0,04) | 0,0313 | 31,95× | 7,09 | 2,78 |
| FW medium | CUDA FP16 | 21,44 (0,47) | 0,0581 | 17,20× | 8,57 | 4,75 |
| C++ small | CUDA F16 | 9,50 (0,10) | 0,0258 | 38,81× | 6,79 | 2,69 |
| C++ medium | CUDA F16 | 16,93 (0,23) | 0,0459 | 21,78× | 8,57 | 4,60 |

Small FW CPU → GPU: **5,81×** menos tempo nessa fixture. Na curta, ganho FW
tiny/base/small/medium: aproximadamente 1,33× / 2,73× / 5,13× / 7,83×;
C++: 1,80× / 3,83× / 8,38× / 11,53×. Não usar esses fatores para estimar VPS.
Na leitura alternada de duas vozes, FW small obteve WER/CER 0% em ambos os
devices; warm CPU 6,91 s versus CUDA 1,60 s. Não prova qualidade em reuniões.

Uma revisão dos segmentos públicos encontrou termos próprios/técnicos ainda
errados: small CUDA FW reconheceu `Dunlap` como `Unlep`, C++ como `don't let`;
`Riga` apareceu como `Higa`. Hífen versus palavra separada também influencia
WER. Capitalização e pontuação variam e não são avaliadas pelos escores usados.
Logo, small é o melhor equilíbrio desta amostra, não qualidade perfeita.

### Memória observada (não requisitos mínimos)

Mediana do pico amostrado por sessão na fixture curta. GiB arredondados.
VRAM é delta total aproximado; CPU não precisa dessas alocações CUDA.

| Engine/modelo | RSS CPU GiB | RSS CUDA GiB | Delta VRAM CUDA GiB |
| --- | ---: | ---: | ---: |
| FW tiny | 0,32 | 0,63 | 0,27 |
| FW base | 0,38 | 0,69 | 0,41 |
| FW small | 0,78 | 0,67 | 0,84 |
| FW medium | 1,66 | 1,58 | 2,20 |
| C++ tiny | 0,48 | 0,58 | 0,40 |
| C++ base | 0,58 | 0,59 | 0,48 |
| C++ small | 1,03 | 0,58 | 0,92 |
| C++ medium | 2,32 | 0,59 | 2,25 |
| FW large-v3 | Não medido | 3,03 | 4,20 |

No áudio de 6min09s, RSS small FW CPU/GPU foi 1,12/1,24 GiB e medium GPU
2,21 GiB; small/medium C++ CUDA 0,67/0,68 GiB. Não confundir RSS com memória
total da máquina/VM. VRAM adicional small FW/C++ foi cerca de 0,92/0,95 GiB;
medium 2,26/2,31 GiB. A RTX 3060 12 GB comportou esses testes individuais.
Não houve teste de residência simultânea Whisper + Pyannote ou concorrência >1.

### Reuniões de 30 e 60 minutos: projeções, não testes diretos

Extrapolação linear do RTF warm da leitura de 368,89 s, somente transcrição.
Acrescentar startup/conversão para processo frio, fila/upload e diarização se usados.
Conteúdo, pausas, idioma, silêncio, decoding e comprimento podem mudar o RTF.

| Configuração | Áudio 30 min | Áudio 60 min |
| --- | ---: | ---: |
| FW small CPU INT8 | ~5min27s | ~10min54s |
| FW small CUDA FP16 | ~56s | ~1min53s |
| FW medium CUDA FP16 | ~1min45s | ~3min29s |
| C++ small CUDA F16 | ~46s | ~1min33s |
| C++ medium CUDA F16 | ~1min23s | ~2min45s |

Nenhuma reunião completa de 30/60 minutos foi cronometrada. A amostra local
autorizada de 600 s levou 33,68 s warm (mediana, faixa 32,68–36,07 s, três sessões)
com FW small CUDA, RTF 0,0561: projeções de ~1min41s / ~3min22s, mais lentas
que FLEURS. Sem referência humana, não recebeu WER/CER. Fonte, conteúdo, saídas
e fingerprint dessa amostra não estão publicados. Isso mostra por que as
projeções não são promessas de latência para qualquer reunião.

## Detecção de falantes: Pyannote 3.1, separado

AMI ES2004a público, RTTM humano correspondente, collar 0,25 s, overlap incluído,
contagem automática, sem filtros/merge ou tuning. Não é áudio PT-BR.
Cada linha abaixo tem três sessões cold/warm, sem Whisper carregado simultaneamente.

| Fixture | Device | Cold s | Warm s (MAD) | RTF warm | DER % | Falantes ref → encontrados | RSS pico GiB |
| --- | --- | ---: | ---: | ---: | ---: | --- | ---: |
| Clean, 60 s | CPU | 39,17 | 39,05 (0,06) | 0,6508 | 22,64 | 2 → 3 | 2,35 |
| Clean, 60 s | CUDA | 2,12 | 1,40 (0,01) | 0,0233 | 22,64 | 2 → 3 | 1,48 |
| Four speakers, 90 s | CPU | 65,85 | 65,02 (0,14) | 0,7225 | 12,08 | 4 → 2 | 2,42 |
| Four speakers, 90 s | CUDA | 2,94 | 2,26 (0,02) | 0,0251 | 12,08 | 4 → 2 | 1,48 |

CPU/GPU repetiram as mesmas métricas e 15/34 segmentos, respectivamente.
São os DER automáticos já registrados na [baseline estável](../../docs/ml_validation.md),
não uma promoção de Pyannote 4. Known-count não foi executado neste benchmark.
O DER agregado relativamente menor no trecho de quatro falantes **não** resolve
a subcontagem; não declarar a diarização perfeita ou homologada para reuniões.

CUDA warm foi ~28× mais rápida nas duas janelas. Delta VRAM mediano da sessão:
2,43/2,44 GiB; pico alocado por Torch: 1,59 GiB em ambas. Diferentes medidas,
não valores intercambiáveis. O modelo rodou de fato em CUDA, não fallback CPU.
Load Pyannote mede construção/transferência do pipeline, **exclui imports Torch**;
não é diretamente comparável ao startup do runner ASR.

Diarização em CPU foi mais rápida que duração do áudio **neste Ryzen com seis
threads**, mas acrescenta muito mais tempo que ASR. Somar RTFs warm de testes
separados dá apenas cenário aritmético: FW small + clean AMI ~0,8325 CPU ou
~0,0546 GPU (30 min ~25min / ~1min38s; 60 min ~50min / ~3min16s).
Não é medição de reunião/pipeline combinado, memória conjunta ou Worker real.
Custos/capacidade não devem usar o RTF de ASR sozinho quando há falantes.

## Custos: fontes e escopo

Preços públicos consultados em 2026-10-08, USD sem conversão cambial:
[Hetzner — tabela oficial](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/)
e [AssemblyAI — preço oficial](https://www.assemblyai.com/pricing/).
Não são propostas comerciais USAGI, fatura real ou preços garantidos por contrato.

| Cenário | Preço parametrizado | Hardware de destino medido? |
| --- | --- | --- |
| VPS econômica CX23 EU | US$ 6,49/mês; 2 vCPU compartilhadas, 4 GB | Não |
| VPS intermediária CPX32 EU | US$ 41,99/mês; 4 vCPU compartilhadas, 8 GB | Não |
| GPU GEX44 | US$ 272,10/mês + US$ 134 setup; RTX 4000 SFF Ada 20 GB | Não |
| AssemblyAI Universal-2 + falantes | US$ 0,17/h de áudio; US$ 0,002833/min | Sem chamada de inferência |
| AssemblyAI Universal-3.5 Pro + falantes | US$ 0,23/h; US$ 0,003833/min | Sem chamada de inferência |

AssemblyAI soma US$ 0,15/h ou US$ 0,21/h de transcrição e US$ 0,02/h de
detecção de falantes. Faturamento multichannel é por canal; a comparação
financeira acima assume um canal. Opções adicionais, contratos e impostos
podem mudar a conta. Hetzner exclui IVA e, na VPS, IPv4 opcional.

O simulador [cost_model.py](cost_model.py) usa Decimal, moeda explícita, custo
mensal/setup amortizado, horas enviadas, calendário, concorrência exata medida,
startup, diarização e chegadas FIFO. Sem perfil RTF do servidor, capacidade,
fila e ponto de equilíbrio operacional permanecem desconhecidos. Nunca aplica
automaticamente o desempenho do Ryzen a uma VPS barata ou da RTX 3060 a Ada.
Uma taxa por hora de compute sem RTF deixa o custo correspondente desconhecido.
Perfis de concorrência 1 não são multiplicados para inventar concorrência maior.

Somente como piso financeiro, antes de despesas extras e sem comprovar capacidade:

| Custo fixo / tarifa de API | Universal-2 + falantes | Universal-3.5 Pro + falantes |
| --- | ---: | ---: |
| CX23 | 38,18 h de áudio/mês | 28,22 h/mês |
| CPX32 | 247,00 h/mês | 182,57 h/mês |
| GEX44 + setup/12 meses | 1.666,27 h/mês | 1.231,59 h/mês |

Fórmula simplificada: custo fixo / tarifa por hora de áudio. **Não são pontos
de equilíbrio operacional validados**: precisam de capacidade/concorrência/fila
medidas no servidor, qualidade aceitável e custos variáveis. A 100 h/mês,
AssemblyAI nesse escopo seria US$ 17 / US$ 23; não foi uma cobrança realizada.
O custo configurado da GPU seria US$ 283,27/mês com setup amortizado. Num cenário
sem startup/diarização, 720 h/mês e ocupação assumida de 75%, o RTF local small
FW implicaria teto algébrico de 2.971 h/mês CPU ou 17.254 h/mês CUDA. Esses números
**não são capacidade sustentada medida**, disponibilidade da máquina nem perfil
transferível para servidores; não foram colocados como medições nos perfis VPS.

O custo zero de chamada de API local **não** significa infraestrutura grátis:
energia, hardware/depreciação, operação, armazenamento, tráfego, backups,
ociosidade e redundância não foram cotados. Não há medição de qualidade
AssemblyAI nesta execução nem equivalência garantida de features/modelos.

## Recomendação técnica (não planos implementados)

1. **Melhor equilíbrio medido:** small. FW CPU INT8 é claramente mais rápido
   que C++ CPU F16 nesta configuração; em GPU, C++ small foi mais rápido no áudio
   longo, com WER próximo, mas não justifica trocar a biblioteca do produto sem
   medir o pipeline real. Manter Faster-Whisper simplifica continuidade.
2. **Free futuro:** small com execução compartilhada/assíncrona e limites
   explícitos, se a infraestrutura se provar sustentável. Tiny/base podem servir
   a uma prévia experimental, mas WER de 11–19% neste teste não sustenta recomendá-los
   como resultado final padrão de reuniões. Guest atual continua AssemblyAI.
3. **Starter futuro:** small CUDA FP16 é o ponto de partida técnico. Medium/large
   não merecem promessa de qualidade superior nesta amostra; avaliar reuniões
   PT-BR naturais, nomes e termos de domínio antes de diferenciá-los por plano.
4. **Infraestrutura inicial:** preservar AssemblyAI/BYOK quando volume/latência
   exigirem serviço gerenciado; não comprar GPU dedicada apenas por velocidade
   local. Testar VPS intermediária 8 GB para CPU em ambiente isolado antes de
   contratação. VPS 2 vCPU/4 GB pode ser candidata para transcrição limitada,
   mas não há medição que autorize oferecer fila curta ou Whisper+Pyannote nela.
5. **Híbrido futuro:** fila RQ existente com seleção explícita local/AssemblyAI,
   origem BYOK/plataforma e limites já existentes. GPU própria somente após
   provar qualidade, concorrência, memória conjunta, recuperação e custo total;
   AssemblyAI para demanda que a capacidade local não consiga atender, com
   consentimento/política explícita. Nunca fallback externo silencioso ou envio
   de mídia a terceiro sem autorização. Nenhuma dessas mudanças foi implementada.

Antes de decidir investimento, repetir o harness no servidor exato, com pelo
menos três sessões, carga concorrente real e calendário de chegadas. Incluir
diarização e overhead de recarga/supervisão do Worker; este teste de engines
residentes não substitui o benchmark operacional do Worker que recarrega por job.

## Reprodução e publicação

Consulte [README](README.md) para preparação, matriz, diarização offline,
privacidade e repetição em VPS. Áudios, modelos, hipóteses, logs, referências
e resultados privados ficam em `.local-artifacts/`, ignorada pelo Git.
O CSV publicável aceita uma lista fechada de campos e somente IDs FLEURS/AMI.
Não publicar o vídeo autorizado, nomes de arquivos, caminhos ou transcripts.

Evidência desta execução:

- [CSV bruto público](evidence/public-results.csv): 168 observações, 56 grupos
  cold/warm, cada um com três sessões distintas. Mais 6 observações privadas
  completam as 174 inferências executadas, mas ficam somente no CSV local ignorado.
- [Resumo público](evidence/public-summary.json): mediana, mínimo/máximo, MAD,
  RTF, memória, WER/CER/DER e confirmação de repetição suficiente.
- [Identidades dos modelos](evidence/model-provenance.json): hashes SHA-256 de
  pesos/configs/tokenizers, revisões HF quando disponíveis, imagem e asset C++.
  Main GGML foi observado, não pinado no download. Large-v3 foi copiado de
  cache: revisão observada separada de proveniência atestada; hashes definitivos.
  Para repetição exata, obter e conferir esses mesmos artefatos, não confiar em
  resolver `main` novamente. `provenance.py` resolve symlinks do cache no Linux.
- [Simulação de servidores não medidos](evidence/cost-unmeasured-servers.json):
  executada com o catálogo de exemplo; capacidade/fila/equilíbrio operacional
  continuam null em todos os servidores, por ausência de perfis de hardware.

Não houve erro de inferência/OOM observado nas combinações executadas. Isso
não comprova estabilidade por dias, concorrência ou processamento combinado.
Fixture hashes estão no CSV. SHA do harness pode variar com instrumentação/
prova de device/rescore corrigidos durante a preparação; decoding/modelos usados
na comparação não foram afinados com as referências. Hypotheses originais
permanecem locais, e escores C++ foram recalculados sem repetir inferência.

## Validações e limitações operacionais

- 29 testes stdlib do experimento passaram (métricas, privacidade/proveniência,
  dispositivos, generator lazy, custos, concorrência e filas parametrizadas).
- Compilação Python do experimento, parsing dos três scripts PowerShell e
  `git diff --check` passaram. Não há linter Python específico no projeto.
- Backend completo na imagem existente, checkout rastreado isolado sem `.env`,
  rede ou dados: **356 passaram / 37 ignorados** por serviços de integração ausentes.
  Seis warnings preexistentes: Starlette/AnyIO/httpx, Matplotlib/Pyannote, suporte
  Python 3.10 e SDK Gemini legado. Não foram escondidos nem corrigidos fora do escopo.
- Venvs locais consultados não tinham pytest; a execução Docker acima foi usada
  em vez de alterar o ambiente do aplicativo. Pip check do Worker e do venv
  somente-psutil passaram.
- Frontend: lint, **156 testes** e build passaram, sem alterações no frontend.
- API de desenvolvimento respondeu HTTP 200 em `/health`; consulta read-only
  RQ indicou fila vazia e Worker ocioso antes dos benchmarks. Não foram criados
  jobs, usuários, transcrições ou migrations no banco do produto.

CI backend PostgreSQL/Redis/RQ e frontend será registrado no PR sobre o HEAD
final. O experimento adiciona ao CI apenas seus testes stdlib, sem baixar modelos,
pedir GPU, fixtures ou credenciais. Nenhum resultado CI ainda pendente conta
como aprovado.

Os resultados e recomendações deste documento devem ser lidos com esses limites;
nenhum teste local autoriza troca de provider, plano ou promoção de matriz ML.
