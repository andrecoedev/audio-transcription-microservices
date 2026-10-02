import streamlit as st
import requests
from pydub import AudioSegment
import os
import subprocess
import json
import time
from datetime import datetime
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from io import BytesIO
import base64

# Configuração da página
st.set_page_config(
    page_title="🎙️ Transcritor AI",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS customizado para melhorar a aparência
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 2rem;
        text-align: center;
        color: white;
    }
    
    .service-card {
        background: black;
        padding: 1rem;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin: 0.5rem 0;
        border-left: 4px solid #667eea;
    }
    
    .service-card.available {
        border-left-color: #28a745;
    }
    
    .service-card.unavailable {
        border-left-color: #dc3545;
    }
    
    .result-card {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
        border-left: 4px solid #667eea;
    }
    
    .speaker-segment {
        background: white;
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    
    .stats-container {
        display: flex;
        justify-content: space-around;
        margin: 1rem 0;
    }
    
    .stat-item {
        text-align: center;
        padding: 1rem;
        background: white;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        min-width: 120px;
    }
</style>
""", unsafe_allow_html=True)

def check_ffmpeg():
    """Verifica se o FFmpeg está instalado"""
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return True
    except FileNotFoundError:
        return False

def check_service_health(url, service_name):
    """Verifica a saúde do backend integrado"""
    try:
        response = requests.get(f"{url}/health", timeout=5)
        response.raise_for_status()
        data = response.json()
        
        # Verificar status dos modelos carregados
        models = data.get('models', {})
        status_parts = []
        
        if models.get('diarization', {}).get('loaded'):
            status_parts.append(f"Diarização: {models['diarization'].get('device', 'OK')}")
        
        if models.get('whisper', {}).get('loaded'):
            status_parts.append(f"Whisper: {models['whisper'].get('device', 'OK')}")
        
        if models.get('assemblyai', {}).get('loaded'):
            status_parts.append(f"AssemblyAI: {models['assemblyai'].get('device', 'OK')}")
        
        status_info = " | ".join(status_parts) if status_parts else "Nenhum modelo carregado"
        return True, status_info, models
    except requests.exceptions.RequestException as e:
        return False, f"Erro: {str(e)}", {}

def convert_to_wav(input_path, output_path="audio.wav"):
    """Converte arquivo de áudio para WAV"""
    try:
        audio = AudioSegment.from_file(input_path)
        audio.export(output_path, format="wav")
        return output_path, len(audio) / 1000.0  # Retorna também a duração
    except Exception as e:
        st.error(f"Erro ao converter arquivo de áudio: {str(e)}")
        return None, 0

def create_audio_waveform(audio_path):
    """Cria visualização da forma de onda do áudio"""
    try:
        audio = AudioSegment.from_file(audio_path)
        samples = audio.get_array_of_samples()
        
        # Converter array.array para lista Python (compatível com Plotly)
        samples_list = list(samples)
        
        # Reduzir amostragem para visualização (máximo 1000 pontos)
        step = max(1, len(samples_list) // 1000)
        samples_reduced = samples_list[::step]
        
        # Criar timestamps
        duration = len(audio) / 1000.0
        timestamps = [i * duration / len(samples_reduced) for i in range(len(samples_reduced))]
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=timestamps,
            y=samples_reduced,
            mode='lines',
            name='Forma de Onda',
            line=dict(color='#667eea', width=1)
        ))
        
        fig.update_layout(
            title="Visualização do Áudio",
            xaxis_title="Tempo (s)",
            yaxis_title="Amplitude",
            height=200,
            margin=dict(l=0, r=0, t=30, b=0)
        )
        
        return fig
    except Exception as e:
        st.error(f"Erro ao criar visualização: {str(e)}")
        return None

def save_transcription_history(filename, transcription_data):
    """Salva histórico de transcrições"""
    history_file = "transcription_history.json"
    
    # Carregar histórico existente
    history = []
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
        except:
            history = []
    
    # Adicionar nova transcrição
    history.append({
        "timestamp": datetime.now().isoformat(),
        "filename": filename,
        "data": transcription_data
    })
    
    # Manter apenas os últimos 50 registros
    history = history[-50:]
    
    # Salvar histórico atualizado
    with open(history_file, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def load_transcription_history():
    """Carrega histórico de transcrições"""
    history_file = "transcription_history.json"
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

def create_download_link(content, filename, file_type="text"):
    """Cria link de download para conteúdo"""
    if file_type == "json":
        content = json.dumps(content, ensure_ascii=False, indent=2)
        mime_type = "application/json"
    else:
        mime_type = "text/plain"
    
    b64 = base64.b64encode(content.encode()).decode()
    href = f'<a href="data:{mime_type};base64,{b64}" download="{filename}">📥 Baixar {filename}</a>'
    return href

# Verificar FFmpeg
if not check_ffmpeg():
    st.error("⚠️ FFmpeg não encontrado. Instale o FFmpeg e adicione ao PATH.")
    st.info("💡 **Como instalar FFmpeg:**")
    st.code("sudo apt update && sudo apt install ffmpeg")
    st.stop()

# Header principal
st.markdown("""
<div class="main-header">
    <h1>🎙️ Transcritor AI</h1>
    <p>Sistema Inteligente de Transcrição de Áudio e Vídeo</p>
</div>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.header("⚙️ Configurações")
    
    # Configurações de qualidade
    st.subheader("Qualidade da Transcrição")
    quality_mode = st.selectbox(
        "Modo de Qualidade",
        ["Rápido", "Balanceado", "Alta Qualidade"],
        index=1
    )
    
    # Configurações de idioma
    language = st.selectbox(
        "Idioma Principal",
        ["Português", "Inglês", "Espanhol", "Francês", "Auto-detectar"],
        index=0
    )
    
    # Configurações avançadas
    st.subheader("Configurações Avançadas")
    enable_timestamps = st.checkbox("Incluir timestamps", value=True)
    enable_confidence = st.checkbox("Mostrar confiança", value=False)
    
    # Histórico
    st.subheader("📚 Histórico")
    history = load_transcription_history()
    if history:
        st.write(f"Total de transcrições: {len(history)}")
        if st.button("Limpar Histórico"):
            if os.path.exists("transcription_history.json"):
                os.remove("transcription_history.json")
            st.success("Histórico limpo!")
            st.rerun()
    else:
        st.write("Nenhuma transcrição no histórico")

# Área principal
col1, col2 = st.columns([2, 1])

with col1:
    st.header("🔍 Status do Backend")
    
    # Verificar status do backend integrado (porta 2020)
    backend_url = "http://localhost:2020"
    is_available, status_info, models_status = check_service_health(backend_url, "Backend Integrado")
    
    status_class = "available" if is_available else "unavailable"
    status_text = "Disponível" if is_available else "Indisponível"
    status_color = "🟢" if is_available else "🔴"
    
    st.markdown(f"""
    <div class="service-card {status_class}">
        <h4>🧠 Backend Integrado (Porta 2020) {status_color}</h4>
        <p><strong>Status:</strong> {status_text}</p>
        <p><strong>Modelos:</strong> {status_info}</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Mostrar status individual dos modelos
    if is_available and models_status:
        col_a, col_b, col_c = st.columns(3)
        
        with col_a:
            diar_loaded = models_status.get('diarization', {}).get('loaded', False)
            st.metric(
                "🎯 Diarização",
                "Ativo" if diar_loaded else "Inativo",
                delta="Pyannote" if diar_loaded else None
            )
        
        with col_b:
            whisper_loaded = models_status.get('whisper', {}).get('loaded', False)
            st.metric(
                "🎙️ Whisper",
                "Ativo" if whisper_loaded else "Inativo",
                delta=models_status.get('whisper', {}).get('device', '') if whisper_loaded else None
            )
        
        with col_c:
            aai_loaded = models_status.get('assemblyai', {}).get('loaded', False)
            st.metric(
                "☁️ AssemblyAI",
                "Ativo" if aai_loaded else "Inativo",
                delta="Cloud" if aai_loaded else None
            )

with col2:
    st.header("📊 Estatísticas")
    
    # Estatísticas do histórico
    if history:
        total_files = len(history)
        recent_files = len([h for h in history if (datetime.now() - datetime.fromisoformat(h['timestamp'])).days < 7])
        
        st.markdown(f"""
        <div class="stats-container">
            <div class="stat-item">
                <h3>{total_files}</h3>
                <p>Total de Arquivos</p>
            </div>
            <div class="stat-item">
                <h3>{recent_files}</h3>
                <p>Esta Semana</p>
            </div>
        </div>
        """, unsafe_allow_html=True)

# Verificar disponibilidade do backend e modelos
backend_available = is_available
has_whisper = models_status.get('whisper', {}).get('loaded', False) if is_available else False
has_assemblyai = models_status.get('assemblyai', {}).get('loaded', False) if is_available else False
has_diarization = models_status.get('diarization', {}).get('loaded', False) if is_available else False

# Área de upload
st.header("📁 Upload de Arquivo")

if not backend_available:
    st.error("⚠️ Backend não está disponível. Inicie o servidor na porta 2020.")
    st.info("💡 **Como iniciar o backend:**")
    st.code("""
cd modules/backend
uvicorn src.main:app --host 0.0.0.0 --port 2020
    """)
elif not (has_whisper or has_assemblyai):
    st.warning("⚠️ Nenhum modelo de transcrição carregado. Configure HF_TOKEN (Whisper) ou AAI_API_KEY (AssemblyAI) no arquivo .env")
    st.info("💡 **Configuração necessária:**")
    st.code("""
# No arquivo modules/backend/.env
HF_TOKEN=seu_token_huggingface
AAI_API_KEY=sua_chave_assemblyai
    """)
else:
    uploaded_file = st.file_uploader(
        "Escolha um arquivo de áudio ou vídeo",
        type=["mp3", "wav", "mp4", "mpeg", "m4a", "flac"],
        help="Formatos suportados: MP3, WAV, MP4, MPEG, M4A, FLAC"
    )

    if uploaded_file:
        # Mostrar informações do arquivo sem carregar tudo em memória
        # Preferir atributo .size quando disponível (bytes)
        try:
            file_size_bytes = uploaded_file.size
        except Exception:
            try:
                file_size_bytes = len(uploaded_file.getbuffer())
            except Exception:
                # Último recurso: ler e resetar (poderá consumir memória)
                file_content = uploaded_file.read()
                file_size_bytes = len(file_content)
                uploaded_file.seek(0)

        file_size = file_size_bytes / (1024 * 1024)  # MB

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Nome do Arquivo", uploaded_file.name)
        with col2:
            st.metric("Tamanho", f"{file_size:.2f} MB")
        with col3:
            estimated_time = max(1, int(file_size * 0.5))  # Estimativa simples
            st.metric("Tempo Estimado", f"~{estimated_time} min")

    # Configurações de transcrição
    st.header("🎛️ Configurações de Transcrição")

    col1, col2 = st.columns(2)

    with col1:
        # Seleção do modelo
        available_models = []
        if has_whisper:
            available_models.append("whisper")
        if has_assemblyai:
            available_models.append("assemblyai")
        
        if len(available_models) > 1:
            transcription_model = st.selectbox(
                "Modelo de Transcrição",
                available_models,
                format_func=lambda x: "🎙️ Whisper (Local)" if x == "whisper" else "☁️ AssemblyAI (Cloud)",
                help="Whisper é mais rápido (local), AssemblyAI tem maior precisão (cloud)"
            )
        elif len(available_models) == 1:
            transcription_model = available_models[0]
            model_name = "🎙️ Whisper (Local)" if transcription_model == "whisper" else "☁️ AssemblyAI (Cloud)"
            st.info(f"Modelo selecionado: {model_name}")
        else:
            transcription_model = None
            st.warning("Nenhum modelo de transcrição disponível")

    with col2:
        # Opção de diarização
        use_diarization = st.checkbox(
            "🎯 Segmentação de Falantes",
            value=has_diarization,
            disabled=not has_diarization,
            help="Identifica diferentes falantes no áudio (requer Pyannote com HF_TOKEN configurado)"
        )
        
        if not has_diarization:
            st.caption("⚠️ Diarização indisponível - Configure HF_TOKEN")

    # Processamento
    if uploaded_file and transcription_model and st.button("🚀 Iniciar Transcrição", type="primary"):
        start_time = time.time()
        
        with st.spinner("Processando arquivo..."):
            # Salvar arquivo temporário por streaming (chunks) para evitar usar muita memória
            temp_path = f"temp_{uploaded_file.name}"
            CHUNK_SIZE = 4 * 1024 * 1024  # 4MB
            uploaded_file.seek(0)
            with open(temp_path, "wb") as f:
                while True:
                    chunk = uploaded_file.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    f.write(chunk)
            # Garantir ponteiro no início
            uploaded_file.seek(0)
            
            # Converter para WAV
            audio_path, duration = convert_to_wav(temp_path)

            if audio_path:
                # Mostrar visualização do áudio
                st.subheader("🌊 Visualização do Áudio")
                waveform_fig = create_audio_waveform(audio_path)
                if waveform_fig:
                    st.plotly_chart(waveform_fig, use_container_width=True)

                # Preparar dados para salvar no histórico
                transcription_data = {
                    "filename": uploaded_file.name,
                    "duration": duration,
                    "model": "TranscriberCore",
                    "diarization": use_diarization,
                    "segments": []
                }

                # Enfileirar no fluxo assíncrono oficial e aguardar o resultado.
                backend_url = "http://localhost:2020"
                try:
                    with open(audio_path, "rb") as f:
                        files = {"file": (uploaded_file.name, f, "audio/mpeg")}
                        data = {"use_diarization": str(use_diarization).lower()}
                        resp = requests.post(
                            f"{backend_url}/transcriptions/jobs",
                            files=files,
                            data=data,
                            timeout=60,
                        )
                        resp.raise_for_status()
                        job = resp.json()

                    deadline = time.time() + 600
                    while time.time() < deadline:
                        status_response = requests.get(
                            f"{backend_url}{job['status_url']}", timeout=15
                        )
                        status_response.raise_for_status()
                        job_status = status_response.json().get("job_status")
                        if job_status == "completed":
                            result_response = requests.get(
                                f"{backend_url}{job['result_url']}", timeout=30
                            )
                            result_response.raise_for_status()
                            result = result_response.json()
                            break
                        if job_status == "failed":
                            raise RuntimeError("O worker não conseguiu processar o áudio")
                        time.sleep(2)
                    else:
                        raise TimeoutError("Tempo limite aguardando o worker")

                    # Preencher transcription_data com o resultado
                    transcription_data["segments"] = result.get("segments", [])
                    transcription_data["diarization"] = result.get("diarization")

                    # Mostrar resultados na UI
                    if transcription_data["segments"]:
                        st.subheader("📝 Transcrição")
                        for seg in transcription_data["segments"]:
                            st.markdown(f"""
                            <div class="speaker-segment">
                                <h5>� Falante {seg.get('speaker', 'N/A')}</h5>
                                <p><strong>Tempo:</strong> {seg.get('start', 0):.1f}s - {seg.get('end', 0) if seg.get('end') else duration:.1f}s</p>
                                <p><strong>Transcrição:</strong> {seg.get('text','')}</p>
                            </div>
                            """, unsafe_allow_html=True)
                    else:
                        st.warning("Nenhum segmento retornado pelo backend.")

                except requests.exceptions.RequestException as e:
                    st.error(f"Erro ao chamar backend TranscriberCore: {e}")
                except (RuntimeError, TimeoutError) as e:
                    st.error(str(e))

                # Salvar no histórico
                save_transcription_history(uploaded_file.name, transcription_data)

                # Estatísticas finais
                processing_time = transcription_data.get("processing_time", time.time() - start_time)
                word_count = transcription_data.get("word_count", 0)
                
                st.markdown("---")
                st.subheader("📊 Estatísticas Finais")

                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("⏱️ Duração do Áudio", f"{duration:.1f}s")
                with col2:
                    st.metric("⚡ Tempo de Processamento", f"{processing_time:.1f}s")
                with col3:
                    st.metric("📝 Palavras Transcritas", word_count)
                with col4:
                    num_speakers = transcription_data.get("num_speakers", 1)
                    st.metric("🗣️ Falantes", num_speakers)

                # Opções de download
                st.subheader("💾 Download dos Resultados")

                col1, col2, col3 = st.columns(3)

                with col1:
                    # Download como texto
                    text_content = "\n\n".join([
                        f"Falante {seg.get('speaker')} ({seg.get('start',0):.1f}s - {seg.get('end',0):.1f}s):\n{seg.get('text','')}"
                        for seg in transcription_data["segments"]
                    ])
                    st.markdown(
                        create_download_link(text_content, f"{uploaded_file.name}_transcricao.txt"),
                        unsafe_allow_html=True
                    )

                with col2:
                    # Download como JSON
                    st.markdown(
                        create_download_link(transcription_data, f"{uploaded_file.name}_transcricao.json", "json"),
                        unsafe_allow_html=True
                    )

                with col3:
                    # Download como SRT (legendas)
                    srt_content = ""
                    for i, seg in enumerate(transcription_data["segments"], 1):
                        start_time = f"{int(seg.get('start',0)//3600):02d}:{int((seg.get('start',0)%3600)//60):02d}:{seg.get('start',0)%60:06.3f}".replace('.', ',')
                        end_time = f"{int((seg.get('end',0) or duration)//3600):02d}:{int(((seg.get('end',0) or duration)%3600)//60):02d}:{(seg.get('end',0) or duration)%60:06.3f}".replace('.', ',')
                        srt_content += f"{i}\n{start_time} --> {end_time}\n{seg.get('text','')}\n\n"

                    st.markdown(
                        create_download_link(srt_content, f"{uploaded_file.name}_legendas.srt"),
                        unsafe_allow_html=True
                    )

                # Limpar arquivos temporários
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                if os.path.exists(audio_path):
                    os.remove(audio_path)
                
                st.success("🎉 Transcrição concluída com sucesso!")

# Footer
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; padding: 1rem;">
    <p>🎙️ Transcritor AI - Sistema Inteligente de Transcrição</p>
    <p>Desenvolvido com Streamlit • Whisper • AssemblyAI • Pyannote</p>
</div>
""", unsafe_allow_html=True)

