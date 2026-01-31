"""
Clip Data Models
Represents a generated video clip
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import uuid


class ClipCreate(BaseModel):
    """Request model for creating a clip record"""
    job_id: str
    title: str
    description: str
    start_time: float
    end_time: float
    viral_score: float = Field(ge=0, le=100)
    cropping_mode: str = Field(description="TRACK or GENERAL")


class Clip(BaseModel):
    """Complete clip model"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str
    title: str
    description: str
    start_time: float
    end_time: float
    duration: float = 0
    viral_score: float = 0
    cropping_mode: str = "TRACK"
    file_path: Optional[str] = None
    s3_url: Optional[str] = None
    thumbnail_path: Optional[str] = None
    subtitles_path: Optional[str] = None
    dubbed_audio_path: Optional[str] = None
    social_posts: List[dict] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def __init__(self, **data):
        super().__init__(**data)
        if self.duration == 0:
            self.duration = self.end_time - self.start_time
