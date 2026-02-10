"""
ViralClip - Viral Content Automation Platform
Main FastAPI Application Entry Point
"""

from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse

from .config import get_settings
from .utils.logger import setup_logger
from .routers import jobs_router, clips_router, settings_router, websocket_router, schedules_router
from .services.schedule_service import get_scheduler
from .services.job_queue import get_job_queue
from .routers.jobs import configure_job_queue, initialize_job_state
from .routers.websocket import set_broadcast_loop


# Set up logging
logger = setup_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    settings = get_settings()
    
    # Create required directories
    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.temp_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)

    # Initialize persistent job state and queue workers
    await initialize_job_state()
    configure_job_queue()

    job_queue = get_job_queue()
    await job_queue.start()

    logger.info("=" * 60)
    logger.info("ViralClip - Viral Content Automation Platform")
    logger.info("=" * 60)
    logger.info(f"Output directory: {settings.output_dir}")
    logger.info(f"Temp directory: {settings.temp_dir}")
    logger.info(f"Data directory: {settings.data_dir}")
    logger.info(f"Whisper model: {settings.whisper_model}")
    logger.info(f"Queue workers: {settings.job_worker_concurrency}")
    logger.info(f"Queue max pending jobs: {settings.max_pending_jobs}")
    
    # Check service configurations
    if settings.gemini_api_key:
        logger.info("[OK] Gemini AI configured")
    else:
        logger.warning("[!] Gemini API key not set")
    
    if settings.aws_access_key_id:
        logger.info("[OK] AWS S3 configured")
    else:
        logger.info("[-] AWS S3 not configured (uploads disabled)")
    
    if settings.elevenlabs_api_key:
        logger.info("[OK] ElevenLabs configured")
    else:
        logger.info("[-] ElevenLabs not configured (dubbing disabled)")

    if settings.api_key:
        logger.info("[OK] API key authentication enabled")
    else:
        logger.warning("[!] API key authentication disabled")
    
    logger.info("=" * 60)
    logger.info("Server started successfully!")
    logger.info("Dashboard: http://localhost:8000")
    logger.info("API Docs: http://localhost:8000/docs")
    logger.info("=" * 60)
    
    # Start the background scheduler for scheduled posts
    import asyncio
    set_broadcast_loop(asyncio.get_running_loop())
    scheduler = get_scheduler()
    scheduler.start_background(check_interval=60)
    logger.info("[OK] Scheduler started for scheduled social media posts")
    
    yield
    
    # Cleanup on shutdown
    scheduler.stop_scheduler()
    await job_queue.stop()
    logger.info("Shutting down ViralClip...")


# Create FastAPI app
app = FastAPI(
    title="ViralClip",
    description="Viral Content Automation Platform - Transform long videos into viral short clips",
    version=get_settings().app_version,
    lifespan=lifespan
)

# CORS middleware
settings = get_settings()
cors_origins = settings.cors_allowed_origins or ["http://localhost:8000", "http://127.0.0.1:8000"]
cors_allow_credentials = "*" not in cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Global Exception Handlers
# ============================================================================

from .utils.exceptions import ViralClipError


PUBLIC_PATHS = {
    "/",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/settings/health",
    "/favicon.ico",
}
PUBLIC_PREFIXES = ("/static", "/output")


def _extract_api_key(request: Request) -> str:
    api_key = request.headers.get("x-api-key", "").strip()
    if api_key:
        return api_key

    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return ""


@app.middleware("http")
async def api_key_auth_middleware(request: Request, call_next):
    settings = get_settings()
    if not settings.api_key:
        return await call_next(request)

    path = request.url.path
    if path in PUBLIC_PATHS or any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES):
        return await call_next(request)

    provided_key = _extract_api_key(request)
    if provided_key != settings.api_key:
        return JSONResponse(
            status_code=401,
            content={"detail": "Unauthorized: invalid or missing API key"},
        )

    return await call_next(request)


@app.exception_handler(ViralClipError)
async def viralclip_exception_handler(request: Request, exc: ViralClipError):
    """Handle all ViralClip custom exceptions"""
    logger.error(f"ViralClipError [{exc.code}]: {exc.message}")
    return JSONResponse(
        status_code=400 if exc.recoverable else 500,
        content=exc.to_dict()
    )


@app.exception_handler(ValueError)
async def validation_exception_handler(request: Request, exc: ValueError):
    """Handle validation errors"""
    logger.warning(f"Validation error: {exc}")
    return JSONResponse(
        status_code=400,
        content={
            "error": "VALIDATION_ERROR",
            "message": str(exc),
            "recoverable": True,
            "recovery_hint": "Check your input parameters and try again."
        }
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle any unhandled exceptions"""
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_ERROR",
            "message": "An unexpected error occurred. Please try again.",
            "recoverable": True,
            "recovery_hint": "If this persists, check the server logs for details."
        }
    )


# Include routers
app.include_router(jobs_router)
app.include_router(clips_router)
app.include_router(settings_router)
app.include_router(websocket_router)
app.include_router(schedules_router)

# Static file serving for output clips
output_path = Path(settings.output_dir)
output_path.mkdir(parents=True, exist_ok=True)
app.mount("/output", StaticFiles(directory=str(output_path)), name="output")

# Serve frontend
frontend_path = Path(__file__).parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")


@app.get("/")
async def serve_frontend():
    """Serve the main dashboard"""
    index_path = frontend_path / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "ViralClip API", "docs": "/docs"}


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "app": "ViralClip"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
