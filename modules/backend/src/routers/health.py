import logging

import psutil
import torch
from fastapi import APIRouter

from .. import engine_registry
from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/")
async def root():
    """Endpoint raiz."""
    return {
        "message": "Transcription API",
        "version": "1.0.0",
        "docs": "/docs",
    }


@router.get("/health")
async def health_check():
    """Verifica a saúde da API e o estado de todos os engines carregados."""
    return {
        "status": "ok",
        "models": {
            "diarization": {
                "loaded": engine_registry.diarization_engine is not None,
                "device": (
                    engine_registry.diarization_engine.get_device()
                    if engine_registry.diarization_engine
                    else "not loaded"
                ),
            },
            "whisper": {
                "loaded": engine_registry.whisper_engine is not None,
                "device": (
                    engine_registry.whisper_engine.get_device()
                    if engine_registry.whisper_engine
                    else "not loaded"
                ),
            },
            "assemblyai": {
                "loaded": engine_registry.assemblyai_engine is not None,
                "device": (
                    engine_registry.assemblyai_engine.get_device()
                    if engine_registry.assemblyai_engine
                    else "not loaded"
                ),
            },
            "gemini": {
                "loaded": engine_registry.meeting_minutes_generator is not None,
                "device": (
                    "cloud"
                    if engine_registry.meeting_minutes_generator
                    else "not loaded"
                ),
            },
        },
        "database": "connected",
    }


@router.get("/system/gpu")
async def gpu_diagnostics():
    """
    Diagnóstico completo de GPU, VRAM e RAM do sistema.

    Retorna:
    - Disponibilidade de CUDA
    - Informações da GPU (nome, VRAM total/livre)
    - Uso de RAM do sistema
    - Device atual de cada engine carregado
    - Motivo pelo qual a GPU pode não estar sendo usada
    - Recomendações de configuração
    """
    # ── RAM do sistema ──────────────────────────────────────────────────────
    vm = psutil.virtual_memory()
    ram_info = {
        "total_gb": round(vm.total / 1024**3, 2),
        "used_gb": round(vm.used / 1024**3, 2),
        "available_gb": round(vm.available / 1024**3, 2),
        "percent": vm.percent,
        "status": (
            "critical" if vm.percent >= 90
            else "warning" if vm.percent >= 75
            else "ok"
        ),
    }

    # ── GPU / CUDA ──────────────────────────────────────────────────────────
    cuda_available = torch.cuda.is_available()
    force_cpu = settings.FORCE_CPU

    gpu_info = {
        "cuda_available": cuda_available,
        "force_cpu_setting": force_cpu,
        "pytorch_version": torch.__version__,
        "cuda_version": torch.version.cuda if cuda_available else None,
        "cudnn_version": str(torch.backends.cudnn.version()) if cuda_available else None,
        "device_count": torch.cuda.device_count() if cuda_available else 0,
        "devices": [],
        "vram_usage": None,
    }

    if cuda_available:
        for i in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(i)
            allocated = torch.cuda.memory_allocated(i)
            reserved = torch.cuda.memory_reserved(i)
            total = props.total_memory
            gpu_info["devices"].append({
                "id": i,
                "name": props.name,
                "total_vram_gb": round(total / 1024**3, 2),
                "allocated_vram_gb": round(allocated / 1024**3, 2),
                "reserved_vram_gb": round(reserved / 1024**3, 2),
                "free_vram_gb": round((total - reserved) / 1024**3, 2),
                "compute_capability": f"{props.major}.{props.minor}",
                "multiprocessor_count": props.multi_processor_count,
            })

        if torch.cuda.device_count() > 0:
            props = torch.cuda.get_device_properties(0)
            allocated = torch.cuda.memory_allocated(0)
            reserved = torch.cuda.memory_reserved(0)
            gpu_info["vram_usage"] = {
                "allocated_gb": round(allocated / 1024**3, 2),
                "reserved_gb": round(reserved / 1024**3, 2),
                "free_gb": round((props.total_memory - reserved) / 1024**3, 2),
                "total_gb": round(props.total_memory / 1024**3, 2),
            }

    # ── Engines carregados e seus devices ───────────────────────────────────
    def engine_device(engine) -> str:
        if engine is None:
            return "not loaded"
        try:
            return engine.get_device()
        except Exception:
            return "unknown"

    engines = {
        "diarization": engine_device(engine_registry.diarization_engine),
        "whisper": engine_device(engine_registry.whisper_engine),
        "assemblyai": engine_device(engine_registry.assemblyai_engine),
        "gemini": engine_device(engine_registry.meeting_minutes_generator),
    }

    # Checar se algum engine local está em CPU quando GPU está disponível
    local_engines_on_cpu = [
        name for name, dev in engines.items()
        if dev not in ("not loaded", "cloud", "unknown")
        and "cuda" not in dev.lower()
        and name not in ("assemblyai", "gemini")
    ]

    # ── Diagnóstico e recomendações ─────────────────────────────────────────
    issues: list[str] = []
    recommendations: list[str] = []

    if not cuda_available:
        issues.append("CUDA não disponível: torch.cuda.is_available() retornou False.")
        recommendations.append(
            "Verifique se o PyTorch foi instalado com suporte a CUDA. "
            "Reinstale com: pip install torch==2.2.2+cu121 --index-url https://download.pytorch.org/whl/cu121"
        )
        recommendations.append(
            "Verifique se os drivers NVIDIA estão instalados: execute 'nvidia-smi' no terminal."
        )
    elif force_cpu:
        issues.append("FORCE_CPU=True está ativado no .env — GPU ignorada intencionalmente.")
        recommendations.append("Remova ou defina FORCE_CPU=False no arquivo modules/backend/.env para usar a GPU.")
    elif local_engines_on_cpu:
        issues.append(
            f"GPU detectada mas engines estão em CPU: {', '.join(local_engines_on_cpu)}. "
            "Isso causa alto consumo de RAM."
        )
        recommendations.append(
            "Reinicie o servidor com as API Keys configuradas — os engines serão carregados na GPU automaticamente."
        )
        recommendations.append(
            "Se estiver usando Docker, adicione suporte a GPU no docker-compose.yml "
            "(seção deploy.resources.reservations.devices)."
        )

    if ram_info["percent"] >= 75:
        if local_engines_on_cpu:
            issues.append(
                f"RAM crítica ({ram_info['percent']}%): modelos ML em CPU consomem ~10GB de RAM. "
                "Mova os engines para GPU para liberar RAM."
            )
        else:
            issues.append(f"Uso de RAM elevado: {ram_info['percent']}% utilizado.")
        recommendations.append(
            "Whisper large-v3 em CPU usa ~6GB de RAM. Em GPU (float16) usa apenas ~3GB de VRAM."
        )

    gpu_being_used = (
        cuda_available
        and not force_cpu
        and len(local_engines_on_cpu) == 0
        and any(
            "cuda" in dev.lower()
            for dev in engines.values()
            if dev not in ("not loaded", "cloud", "unknown")
        )
    )

    return {
        "gpu_being_used": gpu_being_used,
        "gpu": gpu_info,
        "ram": ram_info,
        "engines": engines,
        "issues": issues,
        "recommendations": recommendations,
    }
