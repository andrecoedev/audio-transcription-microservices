"""
Engine de diarização usando Pyannote - carregado uma vez e reutilizado.
"""

import logging
from importlib.metadata import version
import numpy as np
import librosa
from huggingface_hub import hf_hub_download
import torch

# Desabilita TF32 antes de importar pyannote para evitar o ReproducibilityWarning
torch.backends.cuda.matmul.allow_tf32 = False
torch.backends.cudnn.allow_tf32 = False

from pyannote.audio import Pipeline
from pyannote.audio.pipelines.utils.hook import ProgressHook
from huggingface_hub.utils import GatedRepoError, HfHubHTTPError
from ..config import settings
from .diarization_compat import pipeline_config, speaker_turns

logger = logging.getLogger(__name__)


class DiarizationEngine:
    """Motor de diarização usando Pyannote."""
    
    def __init__(self, hf_token: str):
        self.hf_token = hf_token
        self.pipeline = None
        self._load_pipeline()
    
    def _load_pipeline(self):
        """Carrega o pipeline de diarização com configuração otimizada de GPU."""
        try:
            logger.info("Carregando pipeline de diarização Pyannote...")
            pyannote_version = version("pyannote.audio")
            model_repo, auth_kwargs = pipeline_config(pyannote_version, self.hf_token)
            
            # Verificar disponibilidade de CUDA e configuração
            cuda_available = torch.cuda.is_available() and not settings.FORCE_CPU
            if cuda_available:
                gpu_count = torch.cuda.device_count()
                gpu_name = torch.cuda.get_device_name(0)
                logger.info(f"🎮 GPU detectada: {gpu_name} ({gpu_count} device(s))")
            else:
                if settings.FORCE_CPU:
                    logger.info("⚙️  Modo CPU forçado via configuração")
                else:
                    logger.warning("⚠️  GPU não disponível - usando CPU (será mais lento)")
            
            try:
                # Validar acesso aos repositórios gated necessários antes de carregar o pipeline.
                hf_hub_download(repo_id=model_repo, filename="config.yaml", token=self.hf_token)
                if int(pyannote_version.split(".", 1)[0]) < 4:
                    hf_hub_download(
                        repo_id="pyannote/segmentation-3.0",
                        filename="config.yaml",
                        token=self.hf_token,
                    )
                self.pipeline = Pipeline.from_pretrained(model_repo, **auth_kwargs)
            except GatedRepoError as e:
                raise ValueError(
                    f"Acesso negado ao pipeline Pyannote '{model_repo}' ou dependência gated. "
                    "Verifique os termos aceitos pela conta do HF_TOKEN."
                ) from e
            except HfHubHTTPError as e:
                raise ValueError(
                    "Falha HTTP ao baixar pipeline Pyannote no Hugging Face. "
                    "Verifique HF_TOKEN e conectividade de rede."
                ) from e
            except AttributeError as e:
                if "NoneType" in str(e) and "eval" in str(e):
                    raise ValueError(
                        "Falha ao inicializar Pyannote por falta de acesso a modelos dependentes. "
                        f"Confirme acesso a https://huggingface.co/{model_repo}"
                    ) from e
                raise

            if self.pipeline is None:
                try:
                    hf_hub_download(repo_id=model_repo, filename="config.yaml", token=self.hf_token)
                except GatedRepoError as e:
                    raise ValueError(
                        f"Acesso negado ao modelo gated '{model_repo}'. "
                        f"Acesse https://huggingface.co/{model_repo}, "
                        "clique em Request access/Accept terms e aguarde aprovação."
                    ) from e
                except HfHubHTTPError as e:
                    raise ValueError(
                        "Falha HTTP ao validar acesso ao Pyannote no Hugging Face. "
                        "Verifique conectividade e permissões do HF_TOKEN."
                    ) from e

                raise ValueError(
                    "Falha ao carregar pipeline de diarização. "
                    f"Confirme HF_TOKEN e termos em https://huggingface.co/{model_repo}"
                )
            
            # Configurar device otimizado
            if cuda_available:
                device = torch.device("cuda:0")
                logger.info("🚀 Configurando Pyannote para GPU (CUDA)...")
                
                # Configurações otimizadas para GPU
                torch.backends.cudnn.benchmark = True
                torch.backends.cudnn.deterministic = False
                
                # Limpar cache se necessário
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    
            else:
                device = torch.device("cpu")
                logger.info("⚙️  Configurando Pyannote para CPU...")
                
                # Configurações otimizadas para CPU
                torch.set_num_threads(torch.get_num_threads())
            
            self.pipeline.to(device)
            self.device = device
            
            # Log detalhado
            memory_info = ""
            if cuda_available:
                memory_allocated = torch.cuda.memory_allocated(0) / 1024**3
                memory_reserved = torch.cuda.memory_reserved(0) / 1024**3
                memory_info = f" | VRAM: {memory_allocated:.1f}GB alocada, {memory_reserved:.1f}GB reservada"
            
            logger.info(f"✅ Pipeline de diarização carregado no device: {device}{memory_info}")
            
        except Exception as e:
            logger.error(f"Erro ao carregar pipeline de diarização: {e}")
            raise
    
    def is_valid_segment(
        self,
        audio_path: str,
        start: float,
        end: float,
        min_duration: float,
        silence_threshold: float,
    ) -> bool:
        """Verifica se segmento é válido (não muito curto ou silencioso)."""
        try:
            duration = end - start
            if duration < min_duration:
                logger.warning(
                    f"Segmento muito curto: {start:.2f}s-{end:.2f}s, "
                    f"duração={duration:.2f}s"
                )
                return False
            
            audio, sr = librosa.load(audio_path, sr=None, offset=start, duration=duration)
            rms = np.sqrt(np.mean(audio**2))
            db = 20 * np.log10(rms) if rms > 0 else -np.inf
            
            if db < silence_threshold:
                logger.warning(
                    f"Segmento silencioso: {start:.2f}s-{end:.2f}s, dBFS={db:.2f}"
                )
                return False
            
            return True
        except Exception as e:
            logger.error(f"Erro ao verificar segmento {start:.2f}s-{end:.2f}s: {e}")
            return False
    
    def diarize(
        self,
        audio_path: str,
        min_duration: float | None = None,
        silence_threshold: float | None = None,
    ) -> dict:
        """
        Realiza diarização do arquivo de áudio.
        
        Returns:
            Dict com 'segments' (lista) e 'num_speakers' (int)
        """
        if self.pipeline is None:
            raise RuntimeError("Pipeline de diarização não carregado")

        min_duration = (
            settings.MIN_SEGMENT_DURATION if min_duration is None else min_duration
        )
        silence_threshold = (
            settings.SILENCE_THRESHOLD
            if silence_threshold is None
            else silence_threshold
        )
        post_filter_enabled = min_duration > 0.0 or silence_threshold > -100.0
        
        try:
            logger.info("Starting local diarization")
            with ProgressHook() as hook:
                output = self.pipeline(audio_path, hook=hook)
            
            segments = []
            speakers = set()
            
            for turn, speaker in speaker_turns(output):
                if not post_filter_enabled or self.is_valid_segment(
                    audio_path, turn.start, turn.end, min_duration, silence_threshold
                ):
                    duration = turn.end - turn.start
                    segments.append({
                        "start": turn.start,
                        "end": turn.end,
                        "duration": duration,
                        "speaker": speaker
                    })
                    speakers.add(speaker)
                else:
                    logger.info(
                        f"Segmento ignorado: {speaker} ({turn.start:.2f}s-{turn.end:.2f}s)"
                    )
            
            if not segments:
                logger.warning("Nenhum segmento válido encontrado")
                return {"segments": [], "num_speakers": 0}
            
            logger.info(f"Diarização concluída: {len(segments)} segmentos, {len(speakers)} falantes")
            return {"segments": segments, "num_speakers": len(speakers)}
        
        except Exception as e:
            logger.error(f"Erro durante diarização: {e}")
            raise
    
    def get_device(self) -> str:
        """Retorna o device usado pelo pipeline."""
        if hasattr(self, 'device') and self.device:
            return str(self.device)
        elif self.pipeline:
            return str(self.pipeline.device)
        return "not loaded"
