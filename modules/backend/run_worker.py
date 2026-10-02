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
import uuid
from pathlib import Path

# Adiciona o diretório do backend ao path para importações
backend_src = Path(__file__).parent / "src"
if backend_src.exists():
    sys.path.insert(0, str(backend_src.parent))

from rq import Worker

from src.config import settings
from src.database import engine
from src.logging_config import configure_logging
from src.workers.config import (
    get_redis_connection,
    get_transcription_queue,
    is_redis_available,
)
from src.workers.transcription_worker import recover_pending_jobs

configure_logging()
logger = logging.getLogger(__name__)


class RecoveringWorker(Worker):
    """Reconcile durable jobs during RQ's existing maintenance cycle."""

    def main_work_horse(self, job, queue):
        # Recovery uses the parent's DB pool. A forked child must create its own
        # connections without closing sockets still owned by the supervisor.
        engine.dispose(close=False)
        return super().main_work_horse(job, queue)

    def run_maintenance_tasks(self):
        super().run_maintenance_tasks()
        for queue in self.queues:
            recover_pending_jobs(queue)


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
        errors = settings.validate_startup(require_api_security=False)
        if errors:
            raise RuntimeError("Invalid worker configuration: " + "; ".join(errors))
        recover_pending_jobs(queue)
    except Exception:
        logger.exception("Worker initialization failed")
        sys.exit(1)

    logger.info("👂 Aguardando jobs na fila 'transcriptions'...")

    # The parent must never initialize CUDA. Each forked work horse loads its
    # engines after fork; RQ's parent can then supervise heartbeats and timeouts.
    worker = RecoveringWorker(
        [queue],
        connection=redis_conn,
        name="transcription-worker-" + uuid.uuid4().hex[:8],
        default_worker_ttl=75,
        maintenance_interval=60,
        job_monitoring_interval=5,
    )
    
    try:
        worker.work(with_scheduler=False, logging_level="INFO")
    except KeyboardInterrupt:
        logger.info("⏹️  Worker interrompido pelo usuário")
        sys.exit(0)


if __name__ == "__main__":
    main()
