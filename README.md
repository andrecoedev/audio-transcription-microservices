<a name="readme-top"></a>

<!-- PROJECT SHIELDS -->
[![Contributors][contributors-shield]][contributors-url]
[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]
[![MIT License][license-shield]][license-url]
[![LinkedIn][linkedin-shield]][linkedin-url]

<!-- PROJECT LOGO -->
<br />
<div align="center">
  <a href="https://github.com/Dec0XD/audio-transcription-microservices">
    <img src="imgs/Inicial.png" alt="Logo" width="1000" height="500">
  </a>
  <h3 align="center">Audio/Video Transcription with Speaker Diarization</h3>
  <p align="center">
    A GPU-accelerated transcription system with speaker diarization, built on Whisper, Pyannote, and FastAPI. Optimized for local execution with NVIDIA GPU support.
    <br />
    <a href="https://github.com/Dec0XD/audio-transcription-microservices"><strong>Explore the docs »</strong></a>
    <br />
    <br />
    <a href="https://github.com/Dec0XD/audio-transcription-microservices">View Demo</a>
    ·
    <a href="https://github.com/Dec0XD/audio-transcription-microservices/issues">Report Bug</a>
    ·
    <a href="https://github.com/Dec0XD/audio-transcription-microservices/issues">Request Feature</a>
  </p>
</div>

<!-- TABLE OF CONTENTS -->
<details>
  <summary>Table of Contents</summary>
  <ol>
    <li>
      <a href="#about-the-project">About The Project</a>
      <ul>
        <li><a href="#built-with">Built With</a></li>
      </ul>
    </li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#installation">Installation</a></li>
      </ul>
    </li>
    <li><a href="#usage">Usage</a></li>
    <li><a href="#roadmap">Roadmap</a></li>
    <li><a href="#contributing">Contributing</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#contact">Contact</a></li>
    <li><a href="#acknowledgments">Acknowledgments</a></li>
  </ol>
</details>

<!-- ABOUT THE PROJECT -->
## About The Project

This application uploads audio or video files, transcribes them using Faster-Whisper/CTranslate2 or AssemblyAI, and can perform speaker diarization with Pyannote. FastAPI is a lightweight HTTP/job service and all audio, ML, CUDA, FFmpeg and processing-client work belongs to a separate RQ worker. Faster-Whisper is the only local Whisper implementation; the former Hugging Face Transformers engine was removed after the P1-B PT-BR parity validation.

### API / Worker Architecture

The official flow is:

```text
React or Streamlit
        |
        v
FastAPI (auth, upload, database, jobs, queries)
        |
        v
Redis queue: transcriptions
        |
        v
RQ Worker (FFmpeg, Faster-Whisper, Pyannote, AssemblyAI, Gemini)
        |
        v
Database
```

The API process does not import or initialize Torch, Transformers, Whisper,
Pyannote, librosa, pydub or AssemblyAI. The worker initializes engines once
before consuming the queue and reuses them between jobs.

Relevant backend layout:

```
📁 Transcricao-de-audio/
├── 📁 modules/backend/
│   ├── 📁 src/
│   │   ├── main.py                    # Lightweight FastAPI (Port 2020)
│   │   ├── config.py                  # Configuration (.env, GPU settings)
│   │   ├── models.py                  # SQLAlchemy models
│   │   ├── security.py                # JWT authentication
│   │   ├── 📁 services/
│   │   │   ├── diarization_engine.py  # GPU-optimized Pyannote
│   │   │   ├── faster_whisper_engine.py # CTranslate2 adapter
│   │   │   ├── processing_engines.py  # Worker-only engine initialization
│   │   │   └── transcription_processing_service.py # Heavy pipeline
│   │   ├── 📁 workers/                # RQ jobs and persistence
│   │   └── 📁 utils/
│   │       └── gpu_utils.py           # CUDA/cuDNN optimizations
│   ├── requirements.api.txt           # API dependencies, no ML stack
│   ├── requirements.txt               # Full worker/test dependencies
│   ├── Dockerfile.api                 # CPU-only HTTP runtime
│   ├── Dockerfile.worker              # FFmpeg and ML runtime
│   ├── .env.example                   # Configuration template
│   └── 📁 database/                   # SQLite database
├── 📁 frontend/
│   └── app.py                         # Streamlit interface
└── .env                               # Main configuration
```

The four unconsumed synchronous processing endpoints (`/transcribe`,
`/diarize`, `/whisper/transcribe_segment`, and
`/assemblyai/transcribe_segment`) were removed. `/system/gpu` remains only as
a deprecated lightweight compatibility response; GPU details are logged by the
worker. Updating API keys requires restarting the worker, not FastAPI. See the
[P1-A architecture audit](modules/backend/P1A_ARCHITECTURE.md) for the complete
boundary and compatibility notes.

See the [final P1-B validation](modules/backend/P1B_FINAL_VALIDATION.md) for the
PT-BR quality, performance, diarization and engine-removal evidence.

### Core Features

- **Automatic Transcription**: Support for local Whisper and cloud-based AssemblyAI with model selection.
- **Speaker Diarization**: Identifies who speaks and when using Pyannote, with filtering for short or silent segments for improved robustness.
- **Intuitive Interface**: Streamlit provides a simple UI with model availability verification.
- **CPU/GPU Optimization**: Works on CPUs with adjusted processing times or GPUs for faster performance.
- **Terminal Progress**: Displays diarization progress in the terminal.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### Built With
- **Python 3.10+** - Core runtime
- **Streamlit** - Interactive web interface
- **FastAPI** - Backend REST API
- **Faster-Whisper + CTranslate2** - Default local Whisper Large v3 inference
- **PyTorch + CUDA** - Required by Pyannote
- **Pyannote.audio** - Speaker diarization
- **AssemblyAI** - Cloud transcription (alternative)
- **SQLAlchemy** - ORM for persistence
- **Pydantic** - Validation and configuration
- **librosa + pydub** - Audio processing
- **NVIDIA CUDA + cuDNN** - GPU acceleration

### System Architecture

```
┌─────────────┐
│  Frontend   │ Streamlit (Port 8501)
└──────┬──────┘
       │ HTTP REST
       ▼
┌────────────────────────────────────────────┐
│         Lightweight API                    │ FastAPI (Port 2020)
│  ┌──────────────────────────────────────┐  │
│  │  No ML models loaded                  │  │
│  │  ┌────────────┐ ┌────────────────┐  │  │
│  │  │ Auth/HTTP  │ │ Jobs/Queries   │  │  │
│  │  │ Upload/DB  │ │ Redis client   │  │  │
│  │  └────────────┘ └────────────────┘  │  │
│  │  ┌────────────────────────────────┐  │  │
│  │  │     Lightweight health         │  │  │
│  │  └────────────────────────────────┘  │  │
│  └──────────────────────────────────────┘  │
│  • RQ job orchestration                    │
│  • JWT Authentication                      │
│  • SQLite Persistence                      │
│  • Health Checks                           │
│  • No Torch/CUDA imports                   │
└────────────────────┬───────────────────────┘
                     │
                     ▼
            ┌────────────────┐
            │ Redis / RQ     │
            │ Worker + ML    │
            │ CUDA optional  │
            └────────────────┘
```

**Worker Workflow:**
1. **API startup**: No models or CUDA stack are loaded
2. **Upload**: Frontend → FastAPI → database and Redis
3. **Processing**: The separate RQ worker reuses its engines
4. **Diarization**: Pyannote identifies speakers on GPU
5. **Transcription**: Faster-Whisper uses bounded in-memory PCM windows
6. **Response**: Aggregated results persisted

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- GETTING STARTED -->
## Getting Started

### Prerequisites
- **Python 3.10+** (3.11 or 3.12 recommended for local development)
- **Hugging Face account** (token required for Pyannote)
- **AssemblyAI account** (optional, for cloud transcription)
- **FFmpeg** (audio/video conversion)
- **NVIDIA GPU** (recommended):
  - CUDA 12 runtime libraries
  - cuDNN 9
  - a recent NVIDIA driver compatible with CUDA 12
  - **Minimum VRAM**: 8GB

### Installation

#### Quick Installation (Recommended)

**1. Clone and Setup:**
```powershell
git clone https://github.com/Dec0XD/audio-transcription-microservices.git
cd audio-transcription-microservices
```

**2. Configure Environment:**
```powershell
cd modules\backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt  # worker + desenvolvimento/testes
# Para executar somente a API em outro ambiente:
# pip install -r requirements.api.txt

# For NVIDIA GPU (recommended)
pip uninstall -y torch torchvision torchaudio
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

The PyTorch command above is for Pyannote. Faster-Whisper uses CTranslate2 and
has its own CUDA 12/cuDNN 9 runtime requirement. On a local Windows host, make
sure `cublas64_12.dll` and the cuDNN 9 libraries are visible on `PATH`. The
worker Docker image already starts from a CUDA 12.3/cuDNN 9 runtime image.

**3. Configure API Keys:**
```powershell
# From modules\backend, copy and edit the worker/API environment file
copy .env.example .env
```

**.env (required - located in `modules/backend`):**
```ini
# Hugging Face (required for Pyannote)
HF_TOKEN=your_huggingface_token_here

# AssemblyAI (optional, for cloud transcription)
AAI_API_KEY=your_assemblyai_token_here

# GPU Settings (optional)
FORCE_CPU=false
GPU_MEMORY_FRACTION=0.8
WHISPER_MODEL=large-v3
WHISPER_DEVICE=auto
WHISPER_COMPUTE_TYPE=auto
WHISPER_LANGUAGE=pt
WHISPER_MAX_DECODE_CHUNK_SECONDS=300
MIN_SEGMENT_DURATION=0.5
SILENCE_THRESHOLD=-40
```

**4. Run API, worker and frontend:**

Terminal 1 - Backend:
```powershell
cd modules\backend
python -m uvicorn src.main:app --host 0.0.0.0 --port 2020
```

Terminal 2 - RQ Worker (loads FFmpeg/Whisper/Pyannote):
```powershell
cd modules\backend
python run_worker.py
```

Docker Compose defaults to a CPU/auto worker. To explicitly expose an NVIDIA
GPU and select CUDA/FP16, apply the GPU overlay:

```powershell
docker compose -f modules/backend/docker-compose.yml `
  -f modules/backend/docker-compose.gpu.yml up --build
```

These files under `modules/backend/` are the only supported Compose
configuration. The obsolete root Compose, which started a monolithic backend
without the Redis/RQ boundary, was removed.

Terminal 3 - Frontend:
```powershell
cd modules\frontend
streamlit run app.py
```

**URLs:**
- **Frontend**: http://localhost:8501
- **API Docs**: http://localhost:2020/docs
- **Health Check**: http://localhost:2020/health

#### Useful Commands

Verify models are working:

```powershell
# Test CTranslate2 devices/compute types
python -c "import ctranslate2; print(ctranslate2.get_cuda_device_count()); print(ctranslate2.get_supported_compute_types('cpu'))"

# Check worker dependencies
python -c "import faster_whisper, ctranslate2, pyannote.audio; print('Worker dependencies OK')"
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- USAGE EXAMPLES -->
## Usage

### Web Interface (Streamlit)

1. **Access** http://localhost:8501
2. **Verify** model status in the sidebar:
   - Pyannote (GPU) - Diarization
   - Whisper Large (GPU) - Local transcription  
   - AssemblyAI - Cloud transcription
3. **Upload** audio/video files (MP3, WAV, MP4, etc.)
4. **Configure** processing options
5. **Monitor** real-time progress

### Output Examples

**With Diarization (GPU approximately 30s for 2min audio):**
```
File: meeting.mp3 (2.5 MB, 2:15min)
Processing: 28.3s total

Speakers detected: 3
SPEAKER_00 (0.0s - 15.2s): Good morning everyone, let's start today's meeting...
SPEAKER_01 (15.5s - 45.8s): Perfect, I have some important points to discuss...
SPEAKER_02 (46.2s - 2:15.0s): I completely agree with this approach...
```

**Without Diarization (GPU approximately 15s):**
```
Full transcription:
Good morning everyone, let's start today's meeting. Perfect, I have some important points to discuss. I completely agree with this approach...
```

### Performance

Repeatable measurements are documented in
`modules/backend/P1B_FINAL_VALIDATION.md`. Use
`modules/backend/benchmarks/benchmark_transcription.py` for Faster-Whisper and
`modules/backend/benchmarks/diagnose_diarization.py` for filter diagnostics.

### REST API (Optional)

```bash
# Health check
curl http://localhost:2020/health

# Create asynchronous transcription job
curl -X POST "http://localhost:2020/transcriptions/jobs" \
  -F "file=@audio.mp3" \
  -F "use_diarization=true" \
  -F "transcription_model=whisper"
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- ROADMAP -->
## Roadmap

### Completed
- [x] **Isolated architecture** - Lightweight FastAPI plus a separate RQ worker
- [x] **Configurable Faster-Whisper runtime** - CUDA/FP16 or CPU/INT8
- [x] **Pyannote GPU** - Accelerated diarization
- [x] **Streamlit interface** - Health checks and progress
- [x] **Automated scripts** - PowerShell for Windows
- [x] **FastAPI REST API** - Documented endpoints
- [x] **SQLite persistence** - Transcription history
- [x] **.env configuration** - GPU settings, API keys
- [x] **Detailed logging** - VRAM, timings, device info
- [x] **Automated boundary tests** - Job lifecycle and API/worker isolation
- [x] **Split Docker runtimes** - API image without ML and full worker image

### In Progress
- [x] **P1-B PT-BR parity/performance evidence** - validated with public FLEURS speech
- [ ] **Rate limiting** - API protection

### Planned
- [ ] **Multi-GPU support** - Load distribution
- [ ] **INT8 quantization** - Lower VRAM usage
- [ ] **Streaming transcription** - Real-time
- [ ] **Whisper fine-tuning** - Brazilian Portuguese
- [ ] **Batch processing** - Multiple files
- [ ] **Export formats** - SRT, VTT, JSON
- [ ] **Real-time diarization** - Live microphone
- [ ] **Cloud deployment** - AWS/GCP/Azure guides

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- CONTRIBUTING -->
## Contributing

1. Fork the repository
2. `git checkout -b feature/AmazingFeature`
3. `git commit -m 'Add AmazingFeature'`
4. `git push origin feature/AmazingFeature`
5. Open a Pull Request

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- LICENSE -->
## License

Distributed under the MIT License. See `LICENSE.txt` for more information.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- CONTACT -->
## Contact

André Coêlho - [Instagram](https://www.instagram.com/coelhoandrelucas/) - andrecoedev@gmail.com  
Project: [https://github.com/Dec0XD/audio-transcription-microservices](https://github.com/Dec0XD/audio-transcription-microservices)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- ACKNOWLEDGMENTS -->
## Acknowledgments

- Streamlit
- FastAPI
- Whisper
- AssemblyAI
- Pyannote
- PyTorch
- Faster-Whisper
- CTranslate2
- NVIDIA CUDA
- FFmpeg

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- MARKDOWN LINKS & IMAGES -->
[contributors-shield]: https://img.shields.io/github/contributors/Dec0XD/audio-transcription-microservices.svg?style=for-the-badge
[contributors-url]: https://github.com/Dec0XD/audio-transcription-microservices/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/Dec0XD/audio-transcription-microservices.svg?style=for-the-badge
[forks-url]: https://github.com/Dec0XD/audio-transcription-microservices/network/members
[stars-shield]: https://img.shields.io/github/stars/Dec0XD/audio-transcription-microservices.svg?style=for-the-badge
[stars-url]: https://github.com/Dec0XD/audio-transcription-microservices/stargazers
[issues-shield]: https://img.shields.io/github/issues/Dec0XD/audio-transcription-microservices.svg?style=for-the-badge
[issues-url]: https://github.com/Dec0XD/audio-transcription-microservices/issues
[license-shield]: https://img.shields.io/github/license/Dec0XD/audio-transcription-microservices.svg?style=for-the-badge
[license-url]: https://github.com/Dec0XD/audio-transcription-microservices/blob/master/LICENSE.txt
[linkedin-shield]: https://img.shields.io/badge/-LinkedIn-black.svg?style=for-the-badge&logo=linkedin&colorB=555
[linkedin-url]: https://www.linkedin.com/in/andré-coêlho-b55b0622a/
