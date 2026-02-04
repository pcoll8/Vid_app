# CLAUDE.md - ViralClip Development Guide

## Project Overview

ViralClip is an AI-powered viral content automation platform that transforms long-form videos into short, viral-potential clips for Instagram Reels and YouTube Shorts.

## Tech Stack

- **Backend**: FastAPI (Python 3.11+)
- **Frontend**: Vanilla HTML/CSS/JS with glassmorphism dark-mode UI
- **AI**: Google Gemini 2.5 Flash, Faster-Whisper, MediaPipe, YOLOv8
- **Video**: FFmpeg for rendering
- **Cloud**: AWS S3, ElevenLabs, Instagram/YouTube APIs

## Project Structure

```
Vid_app/
├── backend/
│   ├── main.py           # FastAPI app entry point
│   ├── config.py         # Pydantic settings
│   ├── models/           # Data models (Job, Clip, ScheduledPost)
│   ├── routers/          # API endpoints
│   ├── services/         # Core business logic
│   └── utils/            # Logging, exceptions, retry
├── frontend/
│   ├── index.html        # Single-page dashboard
│   ├── css/style.css     # Glassmorphism styles
│   └── js/app.js         # Client-side logic
├── Dockerfile            # Production container
├── railway.json          # Railway deployment config
└── docker-compose.yml    # Local development
```

## Common Commands

```bash
# Run development server
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Run with Docker
docker-compose up --build

# Test imports
python -c "from backend.main import app; print('OK')"
```

## Key Configuration

Environment variables in `.env`:
- `GEMINI_API_KEY` (required) - Google Gemini AI
- `WHISPER_MODEL` - tiny/base/small/medium/large
- `MIN_CLIP_DURATION` - Default 45 seconds
- `MAX_CLIP_DURATION` - Default 60 seconds

## Architecture Patterns

1. **Services**: Each major feature has a service class in `backend/services/`
2. **Lazy Loading**: AI models load on first use (`_ensure_initialized` pattern)
3. **Background Tasks**: FastAPI BackgroundTasks for async processing
4. **Scheduler**: `ScheduleService` runs background job every 60s

## API Structure

- `POST /api/jobs/` - Create processing job
- `GET /api/jobs/{id}` - Get job status
- `GET /api/clips/` - List generated clips
- `POST /api/schedules/` - Schedule social media post
- `WS /ws` - Real-time progress updates

## Code Style

- Type hints on all function signatures
- Docstrings for public methods
- Logging via `backend/utils/logger.py`
- Custom exceptions in `backend/utils/exceptions.py`

## Testing Changes

After making changes:
1. Verify imports: `python -c "from backend.main import app"`
2. Check API docs: `http://localhost:8000/docs`
3. Test frontend at: `http://localhost:8000`

## Notes

- TikTok integration was removed (only Instagram + YouTube supported)
- Video processing requires FFmpeg installed
- GPU optional but speeds up Whisper transcription
