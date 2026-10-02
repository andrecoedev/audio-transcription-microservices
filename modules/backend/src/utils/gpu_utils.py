import logging
import torch
from typing import Dict, Any

logger = logging.getLogger(__name__)


def get_device_info() -> Dict[str, Any]:
    """
    Obtém informações detalhadas sobre dispositivos disponíveis.
    
    Returns:
        Dict com informações de GPU/CPU
    """
    info = {
        "cuda_available": torch.cuda.is_available(),
        "device_count": 0,
        "devices": [],
        "current_device": "cpu",
        "memory_info": {}
    }
    
    if torch.cuda.is_available():
        info["device_count"] = torch.cuda.device_count()
        info["cuda_version"] = torch.version.cuda
        info["cudnn_version"] = torch.backends.cudnn.version()
        
        for i in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(i)
            device_info = {
                "id": i,
                "name": props.name,
                "total_memory_gb": props.total_memory / 1024**3,
                "compute_capability": f"{props.major}.{props.minor}",
                "multiprocessor_count": props.multi_processor_count
            }
            info["devices"].append(device_info)
        
        # Memória atual
        if info["device_count"] > 0:
            current_device = torch.cuda.current_device()
            info["current_device"] = f"cuda:{current_device}"
            info["memory_info"] = {
                "allocated_gb": torch.cuda.memory_allocated() / 1024**3,
                "reserved_gb": torch.cuda.memory_reserved() / 1024**3,
                "max_memory_gb": torch.cuda.max_memory_allocated() / 1024**3
            }
    
    return info


def optimize_gpu_settings():
    """Aplica configurações otimizadas para GPU."""
    if torch.cuda.is_available():
        # Otimizações do cuDNN
        torch.backends.cudnn.benchmark = True
        torch.backends.cudnn.deterministic = False
        
        # Limpar cache
        torch.cuda.empty_cache()
        
        logger.info("🚀 Configurações de GPU otimizadas aplicadas")
    else:
        # Otimizações para CPU
        torch.set_num_threads(torch.get_num_threads())
        logger.info("⚙️  Configurações de CPU otimizadas aplicadas")


def log_device_info():
    """Registra informações detalhadas sobre dispositivos no log."""
    info = get_device_info()
    
    logger.info("=" * 50)
    logger.info("INFORMAÇÕES DE DISPOSITIVOS")
    logger.info("=" * 50)
    
    if info["cuda_available"]:
        logger.info(f"✅ CUDA Disponível: {info['cuda_version']}")
        logger.info(f"✅ cuDNN Versão: {info['cudnn_version']}")
        logger.info(f"✅ Dispositivos GPU: {info['device_count']}")
        
        for device in info["devices"]:
            logger.info(f"   GPU {device['id']}: {device['name']}")
            logger.info(f"      VRAM: {device['total_memory_gb']:.1f} GB")
            logger.info(f"      Compute: {device['compute_capability']}")
            logger.info(f"      SMs: {device['multiprocessor_count']}")
        
        memory = info["memory_info"]
        logger.info(f"💾 Memória Atual:")
        logger.info(f"   Alocada: {memory['allocated_gb']:.2f} GB")
        logger.info(f"   Reservada: {memory['reserved_gb']:.2f} GB")
        
    else:
        logger.info("❌ CUDA não disponível - usando CPU")
        logger.info("💡 Para usar GPU:")
        logger.info("   1. Instale drivers NVIDIA")
        logger.info("   2. Instale CUDA Toolkit")
        logger.info("   3. Reinstale PyTorch com CUDA")
    
    logger.info("=" * 50)
