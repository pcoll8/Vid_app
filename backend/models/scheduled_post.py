"""
Scheduled Post Model
Data model for scheduled social media uploads
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import uuid


class ScheduleStatus(str, Enum):
    """Status of a scheduled post"""
    PENDING = "pending"       # Waiting to be posted
    PROCESSING = "processing" # Currently being posted  
    COMPLETED = "completed"   # Successfully posted
    FAILED = "failed"         # Failed to post
    CANCELLED = "cancelled"   # Cancelled by user
    RETRYING = "retrying"     # Failed, will retry


class Platform(str, Enum):
    """Supported social media platforms"""
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"
    YOUTUBE = "youtube"


@dataclass
class ScheduledPost:
    """Represents a scheduled social media post"""
    
    # Core identifiers
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    clip_id: str = ""
    
    # Scheduling
    scheduled_time: datetime = field(default_factory=datetime.now)
    timezone: str = "UTC"
    
    # Platform targeting
    platforms: List[Platform] = field(default_factory=list)
    
    # Content
    video_path: str = ""
    title: str = ""
    description: str = ""
    hashtags: List[str] = field(default_factory=list)
    
    # Platform-specific settings
    tiktok_settings: Dict[str, Any] = field(default_factory=dict)
    instagram_settings: Dict[str, Any] = field(default_factory=dict)
    youtube_settings: Dict[str, Any] = field(default_factory=dict)
    
    # Status tracking
    status: ScheduleStatus = ScheduleStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    
    # Results
    post_results: Dict[str, Dict] = field(default_factory=dict)
    error_message: Optional[str] = None
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    posted_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary"""
        return {
            "id": self.id,
            "clip_id": self.clip_id,
            "scheduled_time": self.scheduled_time.isoformat(),
            "timezone": self.timezone,
            "platforms": [p.value for p in self.platforms],
            "video_path": self.video_path,
            "title": self.title,
            "description": self.description,
            "hashtags": self.hashtags,
            "status": self.status.value,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "post_results": self.post_results,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "posted_at": self.posted_at.isoformat() if self.posted_at else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduledPost":
        """Create from dictionary"""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            clip_id=data.get("clip_id", ""),
            scheduled_time=datetime.fromisoformat(data["scheduled_time"]) if isinstance(data.get("scheduled_time"), str) else data.get("scheduled_time", datetime.now()),
            timezone=data.get("timezone", "UTC"),
            platforms=[Platform(p) for p in data.get("platforms", [])],
            video_path=data.get("video_path", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            hashtags=data.get("hashtags", []),
            tiktok_settings=data.get("tiktok_settings", {}),
            instagram_settings=data.get("instagram_settings", {}),
            youtube_settings=data.get("youtube_settings", {}),
            status=ScheduleStatus(data.get("status", "pending")),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            post_results=data.get("post_results", {}),
            error_message=data.get("error_message"),
            created_at=datetime.fromisoformat(data["created_at"]) if isinstance(data.get("created_at"), str) else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if isinstance(data.get("updated_at"), str) else datetime.now(),
            posted_at=datetime.fromisoformat(data["posted_at"]) if data.get("posted_at") else None
        )
    
    def is_due(self) -> bool:
        """Check if post is due to be published"""
        return (
            self.status == ScheduleStatus.PENDING and 
            datetime.now() >= self.scheduled_time
        )
    
    def can_retry(self) -> bool:
        """Check if post can be retried"""
        return (
            self.status == ScheduleStatus.FAILED and
            self.retry_count < self.max_retries
        )
