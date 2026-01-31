"""
ViralClip - Viral Content Automation Platform
Main FastAPI Application Entry Point
"""

import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .config import get_settings
from .utils.logger import setup_logger
from .routers import jobs_router, clips_router, settings_router, websocket_router


# Set up logging
logger = setup_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    settings = get_settings()
    
    # Create required directories
    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.temp_dir).mkdir(parents=True, exist_ok=True)
    
    logger.info("=" * 60)
    logger.info("ViralClip - Viral Content Automation Platform")
    logger.info("=" * 60)
    logger.info(f"Output directory: {settings.output_dir}")
    logger.info(f"Temp directory: {settings.temp_dir}")
    logger.info(f"Whisper model: {settings.whisper_model}")
    
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
    
    logger.info("=" * 60)
    logger.info("Server started successfully!")
    logger.info("Dashboard: http://localhost:8000")
    logger.info("API Docs: http://localhost:8000/docs")
    logger.info("=" * 60)
    
    yield
    
    # Cleanup on shutdown
    logger.info("Shutting down ViralClip...")


# Create FastAPI app
app = FastAPI(
    title="ViralClip",
    description="Viral Content Automation Platform - Transform long videos into viral short clips",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Global Exception Handlers
# ============================================================================

from fastapi import Request
from fastapi.responses import JSONResponse
from .utils.exceptions import ViralClipError


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

# Static file serving for output clips
settings = get_settings()
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
