FROM python:3.11-slim

# Definir diretório de trabalho
WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    bash \
    && rm -rf /var/lib/apt/lists/*

# Copiar os requirements (arquivo fica em modules/backend/requirements.txt no contexto de build ajustado)
COPY modules/backend/requirements.txt /app/requirements.txt

# Instalar dependências Python
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copiar todo o repositório para dentro do container (build context deve ser a raiz do repo)
COPY . /app

# Permissões e diretórios
RUN mkdir -p /app/database /app/temp /app/logs

# Expor a porta da API; o worker RQ não publica porta HTTP.
EXPOSE 2020

# Comando padrão para iniciar a API
CMD ["bash", "-c", "cd /app/modules/backend && python -m uvicorn src.main:app --host 0.0.0.0 --port 2020"]
