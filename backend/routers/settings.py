"""
Settings Router
Handles application configuration and API key management
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import get_settings
from ..services.job_queue import get_job_queue
from ..services.voice_dubber import VoiceDubber
from ..utils.logger import get_logger

router = APIRouter(prefix="/api/settings", tags=["settings"])
logger = get_logger()


class ServiceStatus(BaseModel):
    """Status of an external service"""
    name: str
    configured: bool
    status: str


class SettingsResponse(BaseModel):
    """Current settings response"""
    whisper_model: str
    min_clip_duration: int
    max_clip_duration: int
    viral_moments_count: int
    services: List[ServiceStatus]


class SettingsUpdate(BaseModel):
    """Request to update settings"""
    whisper_model: Optional[str] = None
    min_clip_duration: Optional[int] = None
    max_clip_duration: Optional[int] = None
    viral_moments_count: Optional[int] = None


@router.get("/", response_model=SettingsResponse)
async def get_current_settings():
    """Get current application settings and service status"""
    settings = get_settings()
    social_beta_enabled = settings.enable_beta_social_posting
    
    services = [
        ServiceStatus(
            name="Gemini AI",
            configured=bool(settings.gemini_api_key),
            status="Ready" if settings.gemini_api_key else "API key required"
        ),
        ServiceStatus(
            name="AWS S3",
            configured=bool(settings.aws_access_key_id and settings.s3_bucket_name),
            status="Ready" if settings.aws_access_key_id else "Credentials required"
        ),
        ServiceStatus(
            name="ElevenLabs",
            configured=bool(settings.elevenlabs_api_key),
            status="Ready" if settings.elevenlabs_api_key else "API key required"
        ),
        ServiceStatus(
            name="Instagram",
            configured=bool(settings.instagram_access_token),
            status=(
                "Ready" if (social_beta_enabled and settings.instagram_access_token)
                else "Beta disabled" if not social_beta_enabled
                else "Not configured"
            )
        ),
        ServiceStatus(
            name="YouTube",
            configured=bool(settings.youtube_client_id),
            status=(
                "Ready" if (social_beta_enabled and settings.youtube_client_id)
                else "Beta disabled" if not social_beta_enabled
                else "Not configured"
            )
        ),
        ServiceStatus(
            name="API Security",
            configured=bool(settings.api_key),
            status="API key protected" if settings.api_key else "API key disabled"
        )
    ]
    
    return SettingsResponse(
        whisper_model=settings.whisper_model,
        min_clip_duration=settings.min_clip_duration,
        max_clip_duration=settings.max_clip_duration,
        viral_moments_count=settings.viral_moments_count,
        services=services
    )


@router.get("/languages")
async def get_supported_languages():
    """Get list of supported dubbing languages"""
    return VoiceDubber.get_supported_languages()


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": get_app_version(),
        "app": "ViralClip"
    }


@router.get("/version")
async def get_version_info():
    """Get application version control info"""
    settings = get_settings()
    return {
        "version": settings.app_version,
        "git_commit": get_git_revision(),
        "environment": "production"  # In a real app, read from env var
    }


def get_git_revision():
    """Get the current git commit hash (short)"""
    import os
    
    # Try Railway env var first
    commit_sha = os.getenv('RAILWAY_GIT_COMMIT_SHA') or os.getenv('GIT_COMMIT_SHA')
    
    if commit_sha:
        return commit_sha[:7]  # Return short hash
        
    return "dev"

def get_app_version():
    """Get formatted app version"""
    settings = get_settings()
    git_hash = get_git_revision()
    return f"{settings.app_version}-{git_hash}"


@router.get("/system-status")
async def get_system_status():
    """Get detailed system status"""
    import shutil
    import psutil
    
    # Check FFmpeg
    ffmpeg_available = shutil.which("ffmpeg") is not None
    
    # Get disk space
    disk = psutil.disk_usage('/')
    
    # Get memory
    memory = psutil.virtual_memory()
    queue_stats = get_job_queue().stats()
    
    return {
        "ffmpeg": {
            "available": ffmpeg_available,
            "status": "Ready" if ffmpeg_available else "Not installed"
        },
        "disk": {
            "total_gb": round(disk.total / (1024**3), 1),
            "free_gb": round(disk.free / (1024**3), 1),
            "used_percent": disk.percent
        },
        "memory": {
            "total_gb": round(memory.total / (1024**3), 1),
            "available_gb": round(memory.available / (1024**3), 1),
            "used_percent": memory.percent
        },
        "jobs_queue": {
            "pending": queue_stats["pending"],
            "active": queue_stats["active"],
            "max_pending": queue_stats["max_pending"],
            "workers": queue_stats["workers"],
            "running": queue_stats["running"]
        }
    }
