"""
Custom Exceptions for ViralClip
Structured error handling with recovery hints
"""

from typing import Optional, Dict, Any


class ViralClipError(Exception):
    """Base exception for all ViralClip errors"""
    
    def __init__(
        self, 
        message: str, 
        code: str = "UNKNOWN_ERROR",
        recoverable: bool = False,
        recovery_hint: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.recoverable = recoverable
        self.recovery_hint = recovery_hint
        self.details = details or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to JSON-serializable dict"""
        return {
            "error": self.code,
            "message": self.message,
            "recoverable": self.recoverable,
            "recovery_hint": self.recovery_hint,
            "details": self.details
        }


# ============================================================================
# Video Processing Errors
# ============================================================================

class VideoDownloadError(ViralClipError):
    """Error during video download"""
    
    def __init__(self, message: str, url: Optional[str] = None, **kwargs):
        super().__init__(
            message=message,
            code="VIDEO_DOWNLOAD_ERROR",
            recoverable=True,
            recovery_hint="Check if the video URL is valid and accessible. Try again or use a different video.",
            details={"url": url, **kwargs}
        )


class VideoNotFoundError(ViralClipError):
    """Video file not found"""
    
    def __init__(self, path: str):
        super().__init__(
            message=f"Video file not found: {path}",
            code="VIDEO_NOT_FOUND",
            recoverable=False,
            recovery_hint="Ensure the video file exists and the path is correct.",
            details={"path": path}
        )


class UnsupportedFormatError(ViralClipError):
    """Unsupported video/audio format"""
    
    def __init__(self, format_type: str, supported: list):
        super().__init__(
            message=f"Unsupported format: {format_type}",
            code="UNSUPPORTED_FORMAT",
            recoverable=True,
            recovery_hint=f"Convert to a supported format: {', '.join(supported)}",
            details={"format": format_type, "supported": supported}
        )


# ============================================================================
# Transcription Errors
# ============================================================================

class TranscriptionError(ViralClipError):
    """Error during audio transcription"""
    
    def __init__(self, message: str, audio_path: Optional[str] = None, **kwargs):
        super().__init__(
            message=message,
            code="TRANSCRIPTION_ERROR",
            recoverable=True,
            recovery_hint="Try with a different audio source or check if the audio is clear.",
            details={"audio_path": audio_path, **kwargs}
        )


class NoSpeechDetectedError(ViralClipError):
    """No speech detected in audio"""
    
    def __init__(self, duration: float):
        super().__init__(
            message="No speech detected in the audio",
            code="NO_SPEECH_DETECTED",
            recoverable=False,
            recovery_hint="Ensure the video contains clear speech. Music-only or silent videos cannot be processed.",
            details={"duration": duration}
        )


class ModelLoadError(ViralClipError):
    """Error loading AI model"""
    
    def __init__(self, model_name: str, reason: str):
        super().__init__(
            message=f"Failed to load model '{model_name}': {reason}",
            code="MODEL_LOAD_ERROR",
            recoverable=True,
            recovery_hint="Check if the model is installed correctly. Try reinstalling the package.",
            details={"model": model_name, "reason": reason}
        )


# ============================================================================
# AI Processing Errors
# ============================================================================

class ViralDetectionError(ViralClipError):
    """Error during viral moment detection"""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message=message,
            code="VIRAL_DETECTION_ERROR",
            recoverable=True,
            recovery_hint="Check your Gemini API key configuration. The AI service may be temporarily unavailable.",
            details=kwargs
        )


class APIKeyError(ViralClipError):
    """Missing or invalid API key"""
    
    def __init__(self, service: str):
        super().__init__(
            message=f"API key for {service} is missing or invalid",
            code="API_KEY_ERROR",
            recoverable=True,
            recovery_hint=f"Configure the {service} API key in Settings or the .env file.",
            details={"service": service}
        )


class RateLimitError(ViralClipError):
    """API rate limit exceeded"""
    
    def __init__(self, service: str, retry_after: Optional[int] = None):
        hint = f"Wait and try again."
        if retry_after:
            hint = f"Wait {retry_after} seconds before retrying."
        
        super().__init__(
            message=f"Rate limit exceeded for {service}",
            code="RATE_LIMIT_ERROR",
            recoverable=True,
            recovery_hint=hint,
            details={"service": service, "retry_after": retry_after}
        )


# ============================================================================
# Rendering Errors
# ============================================================================

class RenderingError(ViralClipError):
    """Error during video rendering"""
    
    def __init__(self, message: str, output_path: Optional[str] = None, **kwargs):
        super().__init__(
            message=message,
            code="RENDERING_ERROR",
            recoverable=True,
            recovery_hint="Check if FFmpeg is installed correctly and there's enough disk space.",
            details={"output_path": output_path, **kwargs}
        )


class FFmpegError(ViralClipError):
    """FFmpeg execution error"""
    
    def __init__(self, message: str, command: Optional[str] = None, stderr: Optional[str] = None):
        super().__init__(
            message=message,
            code="FFMPEG_ERROR",
            recoverable=True,
            recovery_hint="Ensure FFmpeg is installed and in PATH. Check the video file isn't corrupted.",
            details={"command": command, "stderr": stderr[-500:] if stderr else None}
        )


class DiskSpaceError(ViralClipError):
    """Insufficient disk space"""
    
    def __init__(self, required_gb: float, available_gb: float):
        super().__init__(
            message=f"Insufficient disk space: need {required_gb:.1f}GB, have {available_gb:.1f}GB",
            code="DISK_SPACE_ERROR",
            recoverable=True,
            recovery_hint="Free up disk space or change the output directory to a drive with more space.",
            details={"required_gb": required_gb, "available_gb": available_gb}
        )


# ============================================================================
# Cloud & Upload Errors
# ============================================================================

class S3UploadError(ViralClipError):
    """Error uploading to S3"""
    
    def __init__(self, message: str, bucket: Optional[str] = None, key: Optional[str] = None):
        super().__init__(
            message=message,
            code="S3_UPLOAD_ERROR",
            recoverable=True,
            recovery_hint="Check AWS credentials and bucket permissions. Retry the upload.",
            details={"bucket": bucket, "key": key}
        )


class SocialMediaPostError(ViralClipError):
    """Error posting to social media"""
    
    def __init__(self, platform: str, message: str, **kwargs):
        super().__init__(
            message=f"{platform}: {message}",
            code="SOCIAL_MEDIA_ERROR",
            recoverable=True,
            recovery_hint=f"Check your {platform} API credentials and account permissions.",
            details={"platform": platform, **kwargs}
        )


# ============================================================================
# Job Processing Errors
# ============================================================================

class JobNotFoundError(ViralClipError):
    """Job not found"""
    
    def __init__(self, job_id: str):
        super().__init__(
            message=f"Job not found: {job_id}",
            code="JOB_NOT_FOUND",
            recoverable=False,
            details={"job_id": job_id}
        )


class JobCancelledError(ViralClipError):
    """Job was cancelled"""
    
    def __init__(self, job_id: str):
        super().__init__(
            message=f"Job was cancelled: {job_id}",
            code="JOB_CANCELLED",
            recoverable=False,
            details={"job_id": job_id}
        )


class JobTimeoutError(ViralClipError):
    """Job processing timeout"""
    
    def __init__(self, job_id: str, timeout_seconds: int):
        super().__init__(
            message=f"Job timed out after {timeout_seconds}s",
            code="JOB_TIMEOUT",
            recoverable=True,
            recovery_hint="Try processing a shorter video or increase the timeout setting.",
            details={"job_id": job_id, "timeout_seconds": timeout_seconds}
        )
