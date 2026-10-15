FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY modules/backend/requirements.api.txt modules/backend/requirements.test.txt ./
RUN pip install --no-cache-dir -r requirements.test.txt
COPY modules/backend/src ./src
COPY modules/backend/tests ./tests
COPY modules/backend/alembic ./alembic
COPY modules/backend/alembic.ini ./alembic.ini
COPY modules/backend/pytest.ini ./pytest.ini
COPY modules/backend/scripts ./scripts
COPY modules/backend/run_worker.py ./run_worker.py
