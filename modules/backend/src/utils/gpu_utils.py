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


def check_memory_requirements(model_name: str = "whisper-large") -> Dict[str, Any]:
    """
    Verifica se há memória suficiente para carregar modelo.
    
    Args:
        model_name: Nome do modelo a verificar
        
    Returns:
        Dict com informações de memória
    """
    requirements = {
        "whisper-large": 6.0,  # GB VRAM
        "whisper-medium": 3.0,
        "whisper-small": 1.5,
        "pyannote": 4.0
    }
    
    required_gb = requirements.get(model_name, 2.0)
    
    result = {
        "model": model_name,
        "required_gb": required_gb,
        "sufficient_memory": False,
        "available_gb": 0.0,
        "recommendation": ""
    }
    
    if torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        total_gb = props.total_memory / 1024**3
        allocated_gb = torch.cuda.memory_allocated(0) / 1024**3
        available_gb = total_gb - allocated_gb
        
        result["available_gb"] = available_gb
        result["sufficient_memory"] = available_gb >= required_gb
        
        if not result["sufficient_memory"]:
            result["recommendation"] = f"Precisa de {required_gb:.1f}GB VRAM, tem {available_gb:.1f}GB. Use CPU ou modelo menor."
        else:
            result["recommendation"] = f"✅ Memória suficiente ({available_gb:.1f}GB disponível)"
    else:
        result["recommendation"] = "GPU não disponível - usando CPU"
    
    return result


def clear_gpu_memory():
    """Limpa cache de memória GPU."""
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        logger.info("🧹 Cache de GPU limpo")


def set_memory_fraction(fraction: float = 0.8):
    """
    Define fração de memória GPU a usar.
    
    Args:
        fraction: Fração da memória (0.1 a 1.0)
    """
    if torch.cuda.is_available():
        torch.cuda.set_per_process_memory_fraction(fraction, 0)
        logger.info(f"📊 Fração de memória GPU definida: {fraction * 100:.0f}%")
