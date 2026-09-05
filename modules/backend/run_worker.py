#!/usr/bin/env python
"""
Script para iniciar o worker de transcrição com RQ.

Uso:
    python run_worker.py

Este worker processa jobs da fila Redis de forma contínua.
Execute em um terminal separado do servidor FastAPI.
"""

import logging
import sys
from pathlib import Path

# Adiciona o diretório do backend ao path para importações
backend_src = Path(__file__).parent / "src"
if backend_src.exists():
    sys.path.insert(0, str(backend_src.parent))

from rq import Worker

from src.workers.config import (
    get_redis_connection,
    get_transcription_queue,
    is_redis_available,
)
from src.workers.transcription_worker import initialize_worker_engines, recover_pending_jobs

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    """Inicia o worker RQ."""
    
    # Verifica Redis
    redis_conn = get_redis_connection()
    if not is_redis_available(redis_conn):
        logger.error("❌ Redis não está disponível!")
        logger.error("Instale Redis: https://redis.io/download")
        logger.error("Ou use Docker: docker run -d -p 6379:6379 redis:latest")
        sys.exit(1)
    
    logger.info("✅ Redis disponível")
    
    logger.info("Worker connected to Redis")
    queue = get_transcription_queue(redis_conn)

    try:
        initialize_worker_engines()
        recover_pending_jobs(queue)
    except Exception:
        logger.exception("Worker initialization failed")
        sys.exit(1)

    logger.info("👂 Aguardando jobs na fila 'transcriptions'...")

    worker = Worker(
        [queue],
        connection=redis_conn,
        name="transcription-worker-1",
        job_monitoring_interval=5,
    )
    
    try:
        worker.work(with_scheduler=False, logging_level="INFO")
    except KeyboardInterrupt:
        logger.info("⏹️  Worker interrompido pelo usuário")
        sys.exit(0)


if __name__ == "__main__":
    main()
