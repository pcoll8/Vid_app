# ViralClip 🎬⚡

**AI-Powered Viral Content Automation Platform**

Transform long-form YouTube videos or local files into short, viral-potential clips optimized for Instagram Reels and YouTube Shorts.

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

---

## ✨ Features

### 🎯 Viral Moment Detection
- **Faster-Whisper Transcription** - Fast, accurate speech-to-text with word-level timestamps
- **Gemini 2.0 Flash AI** - Identifies 3-15 most viral moments based on hooks, emotional peaks, and engagement potential
- **SEO-Optimized Copywriting** - Auto-generates catchy titles and descriptions for each clip

### ✂️ Smart AI Cropping & Tracking
- **Dual-Mode Strategy**:
  - **TRACK Mode** - Single subject tracking with face detection (MediaPipe) and person detection (YOLOv8)
  - **GENERAL Mode** - Professional blurred-background layout for groups or landscapes
- **Heavy Tripod Stabilization** - Cinematic, smooth reframing with velocity clamping and exponential smoothing
- **Speaker Identification** - Automatically focuses on the active speaker

### 🎬 Video Rendering
- **9:16 Vertical Format** - Optimized for Reels and Shorts
- **Blurred Background** - Professional aesthetic for GENERAL mode clips
- **Subtitle Overlay** - Burned-in captions for accessibility

### ☁️ Cloud & Distribution
- **AWS S3 Backup** - Automatic silent uploads with multipart support
- **Social Media Posting** - Direct publishing to Instagram and YouTube
- **Multi-Account Support** - Manage multiple social media profiles

### 🎙️ AI Voice Dubbing
- **ElevenLabs Integration** - High-quality voice synthesis
- **30+ Languages** - Translate and dub clips for global reach
- **Voice Cloning** - Maintain original speaker's voice characteristics
- **Auto-Subtitles** - Generate subtitles for dubbed content

### 🖥️ Modern Web Dashboard
- **Glassmorphism Dark-Mode UI** - Premium, visually stunning interface
- **Real-Time Progress** - Step-by-step processing visualization
- **Live Log Streaming** - WebSocket-powered instant updates
- **Clip Gallery** - Preview, download, and manage generated clips

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+**
- **FFmpeg** - Required for video processing
  ```bash
  # Windows (with Chocolatey)
  choco install ffmpeg
  
  # macOS
  brew install ffmpeg
  
  # Ubuntu/Debian
  sudo apt install ffmpeg
  ```

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/pcoll8/Vid_app.git
   cd Vid_app
   ```

2. **Install dependencies**
   ```bash
   pip install -r backend/requirements.txt
   ```

3. **Install optional AI packages** (for full functionality)
   ```bash
   pip install faster-whisper mediapipe ultralytics google-generativeai elevenlabs
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

5. **Start the server**
   ```bash
   python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
   ```

6. **Open the dashboard**
   
   Navigate to: **http://localhost:8000**

---

## ⚙️ Configuration

Copy `.env.example` to `.env` and configure the following:

### Required API Keys

| Key | Description | Get it from |
|-----|-------------|-------------|
| `GEMINI_API_KEY` | Google Gemini AI for viral detection | [Google AI Studio](https://makersuite.google.com/app/apikey) |

### Optional Services

| Key | Description | Get it from |
|-----|-------------|-------------|
| `AWS_ACCESS_KEY_ID` | S3 backup access key | [AWS Console](https://console.aws.amazon.com/iam/) |
| `AWS_SECRET_ACCESS_KEY` | S3 backup secret key | AWS Console |
| `S3_BUCKET_NAME` | S3 bucket name | AWS Console |
| `ELEVENLABS_API_KEY` | Voice dubbing | [ElevenLabs](https://elevenlabs.io/) |
| `INSTAGRAM_ACCESS_TOKEN` | Instagram posting | [Meta for Developers](https://developers.facebook.com/) |
| `YOUTUBE_CLIENT_ID` | YouTube posting | [Google Cloud Console](https://console.cloud.google.com/) |

### Processing Settings

```env
# Clip settings
MIN_CLIP_DURATION=45
MAX_CLIP_DURATION=60
DEFAULT_CLIP_COUNT=5

# AI Cropping
FACE_DETECTION_CONFIDENCE=0.7
TRACK_SMOOTHING_FACTOR=0.15
MAX_VELOCITY=0.08
```

---

## 📖 Usage

### Web Dashboard

1. **Enter a YouTube URL** or **upload a local video file**
2. **Configure options**:
   - Number of clips (1-15)
   - Min/Max duration
   - Enable S3 backup
   - Enable voice dubbing (select target language)
3. **Click "Generate Viral Clips"**
4. **Monitor progress** in real-time
5. **Preview and download** clips from the gallery

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/jobs/` | POST | Create a new processing job |
| `/api/jobs/` | GET | List all jobs |
| `/api/jobs/{id}` | GET | Get job details |
| `/api/jobs/{id}/clips` | GET | Get clips for a job |
| `/api/clips/{id}` | GET | Get clip details |
| `/api/clips/{id}/download` | GET | Get download URL |
| `/api/settings/` | GET | Get service configuration |
| `/api/settings/system-status` | GET | Get system health |
| `/ws` | WebSocket | Real-time updates |

### API Documentation

Interactive docs available at: **http://localhost:8000/docs**

---

## 🏗️ Architecture

```
Vid_app/
├── backend/
│   ├── main.py              # FastAPI application entry point
│   ├── config.py            # Pydantic settings management
│   ├── models/
│   │   ├── job.py           # Job data model
│   │   └── clip.py          # Clip data model
│   ├── routers/
│   │   ├── jobs.py          # Job CRUD endpoints
│   │   ├── clips.py         # Clip management endpoints
│   │   ├── settings.py      # Configuration endpoints
│   │   └── websocket.py     # Real-time updates
│   ├── services/
│   │   ├── youtube_downloader.py  # yt-dlp integration
│   │   ├── transcription.py       # Faster-Whisper STT
│   │   ├── viral_detector.py      # Gemini AI analysis
│   │   ├── ai_cropping.py         # MediaPipe + YOLOv8
│   │   ├── video_renderer.py      # FFmpeg rendering
│   │   ├── s3_uploader.py         # AWS S3 uploads
│   │   ├── voice_dubber.py        # ElevenLabs dubbing
│   │   └── social_poster.py       # Social media APIs
│   └── utils/
│       ├── logger.py        # Structured logging
│       └── stabilizer.py    # Heavy Tripod engine
├── frontend/
│   ├── index.html           # Dashboard HTML
│   ├── css/style.css        # Glassmorphism styles
│   └── js/app.js            # Client-side logic
├── output/                  # Generated clips
├── temp/                    # Temporary processing files
├── .env.example             # Environment template
└── requirements.txt         # Python dependencies
```

---

## 🔧 Processing Pipeline

```mermaid
graph LR
    A[Video Input] --> B[Download/Load]
    B --> C[Transcription]
    C --> D[AI Analysis]
    D --> E[Moment Detection]
    E --> F[AI Cropping]
    F --> G[Video Rendering]
    G --> H[S3 Upload]
    H --> I[Social Posting]
```

1. **Download/Load** - Fetch from YouTube or load local file
2. **Transcription** - Extract speech with word timestamps
3. **AI Analysis** - Gemini identifies viral moments
4. **Moment Detection** - Score and rank potential clips
5. **AI Cropping** - Track subjects and compute crop regions
6. **Video Rendering** - FFmpeg produces 9:16 vertical clips
7. **S3 Upload** - Background upload to cloud storage
8. **Social Posting** - Distribute to configured platforms

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - Video downloading
- [Faster-Whisper](https://github.com/guillaumekln/faster-whisper) - Speech recognition
- [MediaPipe](https://mediapipe.dev/) - Face detection
- [Ultralytics YOLOv8](https://ultralytics.com/) - Object detection
- [ElevenLabs](https://elevenlabs.io/) - Voice synthesis
- [Google Gemini](https://deepmind.google/technologies/gemini/) - AI analysis
