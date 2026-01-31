"""
Job Data Models
Represents a video processing job
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
from datetime import datetime
import uuid


class JobStatus(str, Enum):
    """Job processing status"""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    ANALYZING = "analyzing"
    CROPPING = "cropping"
    RENDERING = "rendering"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"


class JobCreate(BaseModel):
    """Request model for creating a new job"""
    source_url: Optional[str] = Field(None, description="YouTube URL to process")
    source_file: Optional[str] = Field(None, description="Local file path")
    clip_count: int = Field(default=5, ge=1, le=15, description="Number of clips to generate")
    min_duration: int = Field(default=45, ge=30, le=60, description="Minimum clip duration")
    max_duration: int = Field(default=60, ge=30, le=180, description="Maximum clip duration")
    enable_dubbing: bool = Field(default=False, description="Enable voice dubbing")
    dubbing_language: Optional[str] = Field(None, description="Target language for dubbing")
    upload_to_s3: bool = Field(default=True, description="Upload clips to S3")


class Job(BaseModel):
    """Complete job model with all fields"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: JobStatus = JobStatus.PENDING
    progress: float = Field(default=0.0, ge=0, le=100)
    source_url: Optional[str] = None
    source_file: Optional[str] = None
    video_title: Optional[str] = None
    video_duration: Optional[float] = None
    clip_count: int = 5
    min_duration: int = 45
    max_duration: int = 60
    enable_dubbing: bool = False
    dubbing_language: Optional[str] = None
    upload_to_s3: bool = True
    clips: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    class Config:
        use_enum_values = True
