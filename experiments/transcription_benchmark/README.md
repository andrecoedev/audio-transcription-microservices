# Benchmark experimental de transcrição local

Esta pasta não é um provider do produto. Nenhum módulo é importado pela API ou
pelo Worker. Não muda Guest Mode, AssemblyAI, preferências ou a matriz ML estável.
Todas as inferências são locais; não usa Groq, Gemini ou AssemblyAI.

## Medição e limites

- Modelos multilíngues tiny/base/small/medium; large-v3 quando houver headroom.
- Faster-Whisper: CPU INT8 / CUDA FP16, sem VAD/batching; 6 threads, beam 5,
  temperatura 0, detecção automática de idioma. Consome o generator dentro do timer.
- whisper.cpp: pesos GGML F16 (confirmados por `ftype=1`), runtime misto;
  CPU `--no-gpu` / CUDA confirmado por alocação/backend nos logs. Servidor
  exclusivamente em 127.0.0.1, beam 5, VAD desligado; kernels/decoding dos dois
  projetos não são idênticos. Os resultados com quantizações diferentes comparam
  configurações de implantação, não provam superioridade intrínseca de um engine.
- Cada sessão cria outro processo/modelo. Primeira inferência = cold; a segunda,
  com modelo residente = warm. Três sessões geram três observações de cada fase.
  Não limpa cache do OS/disco nem simula boot frio da máquina.
- Carregamento é inicialização observada do engine/runtime (inclui imports/DLLs,
  contexto CUDA e, no C++, readiness do servidor quando não há timer interno).
  Não é uma medida isolada de leitura de pesos. `startup_seconds` deixa isso explícito.
- RTF = inferência / duração; velocidade = 1/RTF. `total_seconds` é soma dos
  estágios medidos: conversão + inferência + inicialização no cold. No warm,
  reutiliza o custo de conversão medido na sessão; o WAV não é novamente convertido.
  Não inclui transferência de upload, espera RQ, boot/download ou API do produto.
- RSS/CPU da árvore de processos e GPU total são amostrados aproximadamente a
  cada 250 ms (consultas podem atrasar). Recursos pertencem à sessão inteira,
  incluindo carregamento e ambas as inferências, não a cada fase separadamente.
  CPU é percentual somado por núcleo (pode exceder 100%). No C++, RSS exclui o
  wrapper Python. Picos amostrados podem perder transientes.
- VRAM inclui desktop/outros processos. Delta é uma aproximação, não VRAM privada
  nem garantia de capacidade. Pyannote também registra o pico alocado por Torch.
- WER/CER seguem a convenção existente do projeto: NFC, minúsculas, pontuação
  removida, hífens preservados; CER sem espaços. Pontuação/capitalização devem
  ser revisadas separadamente. Referência ausente = métrica desconhecida, nunca zero.
- Verbose JSON do whisper.cpp pode inserir quebras de apresentação dentro de
  palavras. O runner concatena os textos dos segmentos nativos sem separadores
  artificiais. `rescore_cpp.py` corrige escores de respostas antigas preservadas
  sem repetir inferência, mudar tempos ou inventar texto. Isso protege contra
  uma regressão do adaptador de benchmark, não altera o modelo nem o produto.

## Windows: preparar e executar

Pré-requisitos locais: FFmpeg/ffprobe, Python, Docker Desktop com GPU e uma imagem
Worker já existente. Não instala drivers ou altera WSL/configuração global.
O venv de instrumentação instala somente psutil; ML usa container descartável
da imagem informada, sem `.env`, volumes de dados, rede ou acesso à fila.
Os scripts montam apenas código do experimento, fixtures e modelos; nunca a
raiz do repositório ou a configuração do produto.

```powershell
./experiments/transcription_benchmark/prepare.ps1 -WorkerImage usagidev-worker:latest
./experiments/transcription_benchmark/matrix.ps1 -Engine faster-whisper
./experiments/transcription_benchmark/matrix.ps1 -Engine whisper.cpp
python experiments/transcription_benchmark/summarize.py .local-artifacts/cpu-gpu-benchmark/results --csv .local-artifacts/cpu-gpu-benchmark/results/raw.local.csv --summary .local-artifacts/cpu-gpu-benchmark/results/summary.local.json
python -m unittest discover -s experiments/transcription_benchmark -v
```

As fixtures FLEURS existentes ficam em `modules/backend/benchmarks/fixtures/`.
Veja seu README para origem, licença CC-BY-4.0, referência humana e reprodução.
Arquivos ausentes não são sintetizados automaticamente nem substituídos por silêncio.
`matrix.ps1` não reutiliza evidência existente silenciosamente: `-Resume` exige
verificação manual dos mesmos hashes, configurações e versão da imagem/harness.
Para outro experimento, use uma cópia/coorte de resultados separada, sem misturar
revisões. Preserve a evidência anterior antes de limpar resultados locais.

`prepare_private.py` aceita a pasta de vídeos autorizada e extrai no máximo o
limite explícito de duração do maior arquivo decodificável. Nunca imprime seu
nome. Áudio, transcript, logs, paths locais e JSONs detalhados permanecem somente
em `.local-artifacts/` (ignorada). Não publicar hipóteses, mesmo de fixtures públicas.
O CSV/relatório publicado nesta pasta deve conter somente métricas/proveniência
aprovadas; não incluir arquivos privados, dados pessoais ou credenciais.
Use `summarize.py --public-only` para publicar apenas FLEURS/AMI; o exportador
também aceita somente campos de métricas conhecidos, descartando texto, paths,
segredos ou campos de debug adicionados a um JSON local por engano.

## Pyannote (separado)

`diarization.py` usa apenas speaker-diarization-3.1 em cache, offline, sem token
implícito ou fallback CPU. Monte o cache isolado em `/models/pyannote` somente leitura.
Para obter pesos já aceitos, `prepare_diarization.py` exige autorização explícita;
consome apenas HF_TOKEN do arquivo de configuração montado readonly, sem guardar
token. Nunca aceita termos ou habilita outro modelo por conta própria.
Use AMI com RTTM humano correspondente, collar 0,25 s, overlap incluído e opção
automática ou known-count explicitamente registrada. DER não é WER/CER.

## Repetir numa VPS/Linux

1. Registre CPU real/vCPUs/RAM, virtualização e limites cgroup; não transfira RTF do
   Ryzen para vCPU compartilhada. Desative workloads concorrentes apenas com autorização.
2. Use mesmos áudios/referências/hashes e configurações. Baixe somente modelos
   públicos antes de desligar rede; registre revisões e hashes. Registre versões
   Faster-Whisper/CTranslate2/driver/CUDA/cuDNN e identidade imutável da imagem.
3. Instale ferramentas somente em venv/imagem de benchmark. Compile whisper.cpp
   na release/revisão registrada com `GGML_CUDA=ON` para CUDA, arquiteturas adequadas
   à GPU; CPU usa `--no-gpu`. O runner aceita `--cpp-server` de um binário Linux.
4. Execute `run.py` uma vez por sessão (1, 2, 3), com `--model-path`, `--audio`,
   `--reference`, `--device`, `--compute-type`, `--output` e fixture ID anônimo.
   Cada invocação realiza cold + warm. CPU/CUDA devem ser explicitamente confirmados.
5. Verifique três sessões distintas por grupo, erros, idioma e amostras de recursos.
   Repita concorrência real antes de colocar perfil `by_concurrency` no simulador.
6. Execute `cost_model.py prices.example.json --output <arquivo-local>` com preços
   atualizados, perfil RTF medido no servidor, overhead de diarização/startup,
   horas enviadas, calendário, margem, concorrência e chegadas para simular fila.

O simulador é cenário, não ledger P5-05, orçamento real ou planos comerciais.
Capacidade/fila ficam desconhecidas sem medições adequadas; preços sem câmbio
implícito, Decimal, fontes/datas e custos desconhecidos explícitos.
