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

This application uploads audio or video files, transcribes them using Hugging Face Whisper or AssemblyAI, and can perform speaker diarization with Pyannote. Since P1-A, FastAPI is a lightweight HTTP/job service and all audio, ML, CUDA, FFmpeg and processing-client work belongs to a separate RQ worker.

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
RQ Worker (FFmpeg, Whisper, Pyannote, AssemblyAI, Gemini)
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
│   │   │   ├── transcription_engine.py # Whisper + AssemblyAI engines
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

### Core Features

- **Automatic Transcription**: Support for local Whisper and cloud-based AssemblyAI with model selection.
- **Speaker Diarization**: Identifies who speaks and when using Pyannote, with filtering for short or silent segments for improved robustness.
- **Intuitive Interface**: Streamlit provides a simple UI with model availability verification.
- **CPU/GPU Optimization**: Works on CPUs with adjusted processing times or GPUs for faster performance.
- **Terminal Progress**: Displays diarization progress in the terminal.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### Built With
- **Python 3.11+** - Core runtime
- **Streamlit** - Interactive web interface
- **FastAPI** - Backend REST API
- **PyTorch + CUDA** - ML framework with GPU acceleration
- **Transformers (Hugging Face)** - Whisper Large v3
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
5. **Transcription**: Whisper processes segments in float16
6. **Response**: Aggregated results persisted

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- GETTING STARTED -->
## Getting Started

### Prerequisites
- **Python 3.11+** (recommended for best compatibility)
- **Hugging Face account** (token required for Pyannote)
- **AssemblyAI account** (optional, for cloud transcription)
- **FFmpeg** (audio/video conversion)
- **NVIDIA GPU** (recommended):
  - CUDA Toolkit 11.8 or 12.x
  - cuDNN 8.9+
  - NVIDIA Driver 531+ (for RTX series)
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

**3. Configure API Keys:**
```powershell
# Copy and edit the .env file in the project root
copy modules\backend\.env.example .env
# OR edit existing .env in the root
```

**.env (required - located in project root):**
```ini
# Hugging Face (required for Pyannote)
HF_TOKEN=your_huggingface_token_here

# AssemblyAI (optional, for cloud transcription)
AAI_API_KEY=your_assemblyai_token_here

# GPU Settings (optional)
FORCE_CPU=false
GPU_MEMORY_FRACTION=0.8
WHISPER_DTYPE=auto
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
# Test PyTorch + CUDA
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"

# Check essential dependencies
python -c "import transformers, pyannote.audio, librosa; print('All dependencies OK')"
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

### Expected Performance

| Configuration | Whisper Large | Pyannote | 2min File |
|-------------|---------------|----------|--------------|
| **RTX 3060** | approximately 8s | approximately 15s | **approximately 25s total** |
| **RTX 4090** | approximately 4s | approximately 8s | **approximately 15s total** |
| **CPU only** | approximately 120s | approximately 300s | **approximately 7min total** |

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
- [x] **Complete GPU optimization** - CUDA, cuDNN, half-precision
- [x] **Whisper Large GPU** - approximately 10x faster than CPU
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
