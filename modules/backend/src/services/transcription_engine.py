"""
Engines de transcrição (Whisper e AssemblyAI) carregados uma vez e reutilizados.
"""

import logging
import os
import time
import torch
import librosa
from pydub import AudioSegment
from transformers import WhisperForConditionalGeneration, WhisperProcessor
import assemblyai as aai
from ..config import settings

logger = logging.getLogger(__name__)


class WhisperEngine:
    """Motor de transcrição usando Whisper (local)."""

    engine_name = "huggingface-whisper"
    
    def __init__(
        self,
        hf_token: str,
        model_name: str = "openai/whisper-large-v3",
        language: str | None = None,
    ):
        self.hf_token = hf_token
        self.model_name = model_name
        self.language = language or settings.WHISPER_LANGUAGE
        self.model = None
        self.processor = None
        self._load_model()
    
    def _load_model(self):
        """Carrega o modelo Whisper com configuração otimizada de GPU."""
        try:
            logger.info(f"Carregando modelo Whisper: {self.model_name}...")
            
            # Verificar disponibilidade de CUDA e configuração
            cuda_available = torch.cuda.is_available() and not settings.FORCE_CPU
            if cuda_available:
                gpu_count = torch.cuda.device_count()
                gpu_name = torch.cuda.get_device_name(0)
                memory_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
                logger.info(f"🎮 GPU detectada: {gpu_name} ({memory_gb:.1f}GB VRAM)")
            else:
                if settings.FORCE_CPU:
                    logger.info("⚙️  Modo CPU forçado via configuração")
                else:
                    logger.warning("⚠️  GPU não disponível - usando CPU (será muito mais lento)")
            
            # Carregar modelo com configurações otimizadas
            model_kwargs = {
                "token": self.hf_token
            }
            
            if cuda_available:
                # Determinar dtype baseado na configuração
                if settings.WHISPER_DTYPE == "auto":
                    # Auto: float16 para GPU com >6GB, senão float32
                    memory_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
                    dtype = torch.float16 if memory_gb >= 6 else torch.float32
                elif settings.WHISPER_DTYPE == "float16":
                    dtype = torch.float16
                else:
                    dtype = torch.float32
                
                # Configurações para GPU
                model_kwargs.update({
                    "torch_dtype": dtype,
                    "device_map": "auto",          # Mapeamento automático de GPU
                })
                logger.info(f"🚀 Configurando Whisper para GPU ({dtype}, fração VRAM: {settings.GPU_MEMORY_FRACTION})...")
            else:
                # Configurações para CPU
                model_kwargs.update({
                    "torch_dtype": torch.float32,  # Full precision para CPU
                })
                logger.info("⚙️  Configurando Whisper para CPU (full precision)...")
            
            self.model = WhisperForConditionalGeneration.from_pretrained(
                self.model_name, 
                **model_kwargs
            )
            self.processor = WhisperProcessor.from_pretrained(
                self.model_name, 
                token=self.hf_token
            )
            
            # Configurar device
            if cuda_available:
                device = torch.device("cuda:0")
                
                # Configurar fração de memória GPU
                if hasattr(torch.cuda, 'set_per_process_memory_fraction'):
                    torch.cuda.set_per_process_memory_fraction(settings.GPU_MEMORY_FRACTION, 0)
                
                # Configurações otimizadas para GPU
                torch.backends.cudnn.benchmark = True
                torch.backends.cudnn.deterministic = False
                
                # Limpar cache se necessário
                torch.cuda.empty_cache()
                
                # Mover modelo para GPU se não foi mapeado automaticamente
                if not hasattr(self.model, 'device_map'):
                    self.model.to(device)
                    
            else:
                device = torch.device("cpu")
                
                # Configurações otimizadas para CPU
                torch.set_num_threads(torch.get_num_threads())
                self.model.to(device)
            
            self.device = device
            
            # Log detalhado
            memory_info = ""
            if cuda_available:
                memory_allocated = torch.cuda.memory_allocated(0) / 1024**3
                memory_reserved = torch.cuda.memory_reserved(0) / 1024**3
                memory_info = f" | VRAM: {memory_allocated:.1f}GB alocada, {memory_reserved:.1f}GB reservada"
            
            dtype_info = f" | Dtype: {str(self.model.dtype)}"
            logger.info(f"✅ Modelo Whisper carregado no device: {device}{dtype_info}{memory_info}")
            
        except Exception as e:
            logger.error(f"Erro ao carregar modelo Whisper: {e}")
            raise
    
    def transcribe_segment(
        self,
        audio_path: str,
        start: float = 0.0,
        end: float = None
    ) -> str:
        """
        Transcreve um segmento de áudio.
        Para áudios longos (>30s), divide em chunks de 30s e processa separadamente.
        
        Args:
            audio_path: Caminho do arquivo de áudio
            start: Tempo de início (segundos)
            end: Tempo de fim (segundos, None = até o final)
            
        Returns:
            Texto transcrito
        """
        if self.model is None or self.processor is None:
            raise RuntimeError("Modelo Whisper não carregado")
        
        start_time = time.time()
        logger.info(f"Transcrevendo segmento {start}s-{end}s com Whisper")
        
        try:
            # Carregar áudio
            audio = AudioSegment.from_file(audio_path)
            total_duration = len(audio) / 1000.0
            
            if end is None or end > total_duration:
                end = total_duration
            
            if start >= end:
                raise ValueError("Tempo de início deve ser menor que tempo de fim")
            
            segment_duration = end - start
            
            # Whisper funciona melhor com chunks de 30 segundos
            CHUNK_SIZE = 30.0  # segundos
            
            if segment_duration <= CHUNK_SIZE:
                # Processar tudo de uma vez
                return self._transcribe_chunk(audio, start, end, segment_duration)
            else:
                # Dividir em chunks e processar
                logger.info(f"Áudio longo ({segment_duration:.1f}s) - processando em chunks de {CHUNK_SIZE}s")
                transcriptions = []
                current_start = start
                
                while current_start < end:
                    current_end = min(current_start + CHUNK_SIZE, end)
                    chunk_text = self._transcribe_chunk(audio, current_start, current_end, segment_duration)
                    
                    if chunk_text.strip():
                        transcriptions.append(chunk_text.strip())
                    
                    current_start = current_end
                
                final_transcription = " ".join(transcriptions)
                elapsed = time.time() - start_time
                logger.info(
                    "Transcrição Whisper legada concluída em %.2fs (%s chunks)",
                    elapsed,
                    len(transcriptions),
                )
                
                return final_transcription
        
        except Exception as e:
            logger.error(f"Erro na transcrição Whisper: {e}")
            raise
    
    def _transcribe_chunk(
        self,
        audio: AudioSegment,
        start: float,
        end: float,
        total_duration: float
    ) -> str:
        """
        Transcreve um chunk individual de áudio.
        
        Args:
            audio: Objeto AudioSegment completo
            start: Tempo de início do chunk (segundos)
            end: Tempo de fim do chunk (segundos)
            total_duration: Duração total do áudio original (para logging)
            
        Returns:
            Texto transcrito do chunk
        """
        # Extrair segmento
        start_ms = int(start * 1000)
        end_ms = int(end * 1000)
        segment_audio = audio[start_ms:end_ms]
        
        # Salvar temporariamente
        segment_path = f"temp/whisper_chunk_{start}_{end}.wav"
        segment_audio.export(segment_path, format="wav")
        
        try:
            # Carregar e processar
            audio_data, sample_rate = librosa.load(segment_path, sr=16000)
            input_features = self.processor(
                audio_data,
                sampling_rate=sample_rate,
                return_tensors="pt",
                return_attention_mask=True
            )
            
            # Garantir consistência de dtype e device
            input_features = input_features.to(self.model.device)
            if hasattr(self.model, 'dtype') and self.model.dtype == torch.float16:
                input_features["input_features"] = input_features["input_features"].to(torch.float16)
            
            # Gerar transcrição com configurações otimizadas
            with torch.no_grad():
                # Configurar o idioma quando ele foi selecionado explicitamente.
                generation_kwargs = {}
                if self.language != "auto":
                    generation_kwargs["forced_decoder_ids"] = (
                        self.processor.get_decoder_prompt_ids(
                            language=self.language,
                            task="transcribe",
                        )
                    )
                
                predicted_ids = self.model.generate(
                    input_features["input_features"],
                    attention_mask=input_features["attention_mask"],
                    max_new_tokens=444,  # 448 (limite) - 4 (tokens especiais) = 444
                    num_beams=1,  # Greedy search para velocidade (ou 5 para melhor qualidade)
                    temperature=0.0,  # Determinístico
                    **generation_kwargs,
                )
            
            transcription = self.processor.batch_decode(predicted_ids, skip_special_tokens=True)[0]
            logger.info("Chunk %.1fs-%.1fs transcrito", start, end)
            
            return transcription
        
        finally:
            # Limpar arquivo temporário
            if os.path.exists(segment_path):
                os.remove(segment_path)
    
    def get_device(self) -> str:
        """Retorna o device usado pelo modelo."""
        if hasattr(self, 'device') and self.device:
            return str(self.device)
        elif self.model:
            return str(self.model.device)
        return "not loaded"

    def get_metadata(self) -> dict[str, str]:
        return {
            "engine": self.engine_name,
            "model": self.model_name,
            "device": self.get_device(),
            "compute_type": str(getattr(self.model, "dtype", settings.WHISPER_DTYPE)),
            "language": self.language,
        }


class AssemblyAIEngine:
    """Motor de transcrição usando AssemblyAI (cloud)."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._configure()
    
    def _configure(self):
        """Configura o cliente AssemblyAI."""
        try:
            logger.info("Configurando AssemblyAI...")
            aai.settings.api_key = self.api_key
            self.config = aai.TranscriptionConfig(language_code="pt")
            self.transcriber = aai.Transcriber(config=self.config)
            logger.info("AssemblyAI configurado")
        except Exception as e:
            logger.error(f"Erro ao configurar AssemblyAI: {e}")
            raise
    
    def transcribe_segment(
        self,
        audio_path: str,
        start: float = 0.0,
        end: float = None
    ) -> str:
        """
        Transcreve um segmento de áudio usando AssemblyAI.
        
        Args:
            audio_path: Caminho do arquivo de áudio
            start: Tempo de início (segundos)
            end: Tempo de fim (segundos, None = até o final)
            
        Returns:
            Texto transcrito
        """
        start_time = time.time()
        logger.info(f"Transcrevendo segmento {start}s-{end}s com AssemblyAI")
        
        try:
            # Carregar áudio
            audio = AudioSegment.from_file(audio_path)
            total_duration = len(audio) / 1000.0
            
            if end is None or end > total_duration:
                end = total_duration
            
            if start >= end:
                raise ValueError("Tempo de início deve ser menor que tempo de fim")
            
            # Extrair segmento
            start_ms = int(start * 1000)
            end_ms = int(end * 1000)
            segment_audio = audio[start_ms:end_ms]
            
            # Salvar temporariamente
            segment_path = f"temp_assemblyai_{start}_{end}.wav"
            segment_audio.export(segment_path, format="wav")
            
            try:
                # Transcrever
                transcript = self.transcriber.transcribe(segment_path)
                transcription = transcript.text.strip() if transcript.text else ""
                
                elapsed = time.time() - start_time
                logger.info("Transcrição AssemblyAI concluída em %.2fs", elapsed)
                
                return transcription
            
            finally:
                # Limpar arquivo temporário
                if os.path.exists(segment_path):
                    os.remove(segment_path)
        
        except Exception as e:
            logger.error(f"Erro na transcrição AssemblyAI: {e}")
            raise
    
    def get_device(self) -> str:
        """Retorna 'cloud' pois é um serviço externo."""
        return "cloud"
