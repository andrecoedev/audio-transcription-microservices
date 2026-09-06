# RQ (Redis Queue) - Implementação de Fila Assíncrona Local

Este projeto usa **RQ** (Redis Queue) para processar jobs de transcrição de forma assíncrona. A FastAPI não carrega engines de ML: somente `run_worker.py` importa e inicializa Whisper, Pyannote, Torch/CUDA, AssemblyAI, Gemini e o processamento FFmpeg.

## 🚀 Como Funciona

```
1. Upload (síncrono, < 1 seg)
   POST /transcriptions/jobs
   └─> salva arquivo no banco
   └─> cria registro no banco
   └─> enfileira em Redis
   └─> retorna 202 (Accepted) com transcription_id

2. Processamento (assíncrono, minutos)
   Worker RQ lê jobs da fila
   └─> atualiza status para "processing"
   └─> processa (WAV, diarização, transcrição)
   └─> salva resultado no banco
   └─> atualiza status para "completed" ou "failed"

3. Consulta (síncrono)
   GET /transcriptions/{id}
   └─> retorna status + resultado
   └─> frontend faz polling a cada 3s
```

## 📦 Setup Mínimo

### Pré-requisitos

- **Python 3.10+**
- **Redis** (local ou Docker)

### 1. Instalar Redis

#### Option A: Docker (recomendado para Windows)
```bash
docker run -d -p 6379:6379 --name redis redis:latest
```

#### Option B: Windows (instalação local)
```bash
# Com Chocolatey
choco install redis

# Ou download: https://github.com/microsoftarchive/redis/releases
```

#### Option C: Linux/Mac
```bash
brew install redis  # Mac
sudo apt-get install redis-server  # Linux
```

Verificar se Redis está rodando:
```bash
redis-cli ping
# Resposta esperada: PONG
```

### 2. Instalar dependências Python

```bash
cd modules/backend
# Ambiente do worker/desenvolvimento:
pip install -r requirements.txt

# Em um ambiente exclusivo da API:
pip install -r requirements.api.txt
```

### 3. Configurar variável de ambiente (opcional)

Se Redis está em outra máquina, crie `.env`:
```env
REDIS_URL=redis://localhost:6379/0
```

## 🏃 Rodando Tudo

### Terminal 1: Servidor FastAPI

```bash
cd modules/backend
python -m uvicorn src.main:app --reload --port 2020
```

### Terminal 2: Worker RQ

```bash
cd modules/backend
python run_worker.py
```

Esperado:
```
✅ Redis disponível
📦 Worker iniciado (Redis: redis://localhost:6379/0)
👂 Aguardando jobs na fila 'transcriptions'...
```

### Terminal 3: Frontend (opcional)

```bash
cd modules/frontendv2
npm run dev
```

## 🔄 Fluxo de Uso

### 1. Upload de arquivo (POST)
```bash
curl -X POST http://localhost:2020/transcriptions/jobs \
  -F "file=@audio.mp3" \
  -F "use_diarization=true" \
  -F "transcription_model=whisper"

# Resposta (202 Accepted):
{
  "transcription_id": 42,
  "status_url": "/transcriptions/jobs/42/status",
  "result_url": "/transcriptions/42",
  "message": "Job enfileirado com sucesso"
}
```

### 2. Consultar status (GET)
```bash
curl http://localhost:2020/transcriptions/jobs/42/status

# Resposta:
{
  "transcription_id": 42,
  "transcription_status": "processing",
  "job_status": "processing",
  "queue_size": 2,
  "error_message": null
}
```

### 3. Obter resultado quando pronto (GET)
```bash
curl http://localhost:2020/transcriptions/42

# Resposta (quando completed):
{
  "id": 42,
  "filename": "audio_uuid",
  "segments": [...],
  "status": "completed",
  "processing_time_seconds": 45.2,
  "word_count": 1234,
  "num_speakers": 2
}
```

## 📊 Monitorar Fila RQ

### Via CLI
```bash
# Ver jobs na fila
rq info transcriptions

# Ver worker
rq worker transcriptions --monitor

# Ver job específico
rq info --job transcription_42
```

### Via Dashboard Web (opcional)

```bash
pip install rq-dashboard
rq-dashboard
# Acessa em http://localhost:9181
```

## 🛑 Parar Workers

```bash
# Terminal do worker
Ctrl+C

# Ou via Redis CLI
redis-cli
> FLUSHDB  # Limpa fila (cuidado!)
> EXIT
```

## ⚠️ Troubleshooting

### "Redis não disponível"

Verifique se Redis está rodando:
```bash
redis-cli ping
```

Se retornar erro, inicie Redis:
```bash
# Mac
brew services start redis

# Linux
sudo systemctl start redis-server

# Docker
docker start redis
```

### "Worker não está processando jobs"

1. Verifique se está rodando: `ps aux | grep run_worker`
2. Verifique logs no Terminal 2
3. Reinicie: `Ctrl+C` e execute novamente `python run_worker.py`

### "Job ficou em 'processing' pra sempre"

Worker pode ter crashado. Marque job como falho:
```bash
redis-cli
> FLUSHDB  # Limpa tudo (cuidado!)
```

Reinicie servidor e worker.

## 🎯 Próximos Passos (Escalabilidade)

Quando precisar escalar, migre para:

1. **Redis em outra máquina** - apenas mude `REDIS_URL` no `.env`
2. **Múltiplos workers** - rode `python run_worker.py` em várias máquinas
3. **Celery** - para uso em produção com monitoramento avançado

O contrato de API permanece o mesmo! Nenhuma mudança no frontend.

## 📝 Notas

- Jobs que não foram processados são recuperados no startup do worker
- Engines são inicializados uma vez por processo worker e reutilizados
- Alterar chaves pela API exige reiniciar os workers
- Arquivos temporários são limpados após processamento
- Suporta até ~100 jobs/min em um PC (suficiente para uso pessoal)
- Sem banco de dados adicional necessário (SQLite é suficiente)
- Sem configuração complexa (zero lines of config!)

---

**Desenvolvido com ❤️ para processamento assíncrono simples**
