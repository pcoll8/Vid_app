"""
Schedule Router
API endpoints for managing scheduled social media posts
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from ..services.schedule_service import get_scheduler
from ..models.scheduled_post import ScheduleStatus, Platform

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


# ============================================================================
# Pydantic Models for API
# ============================================================================

class CreateScheduleRequest(BaseModel):
    """Request to create a scheduled post"""
    clip_id: str = Field(..., description="ID of the clip to post")
    video_path: str = Field(..., description="Path to video file")
    title: str = Field(..., description="Post title")
    description: str = Field(..., description="Post description")
    scheduled_time: datetime = Field(..., description="When to post (ISO format)")
    platforms: List[str] = Field(..., description="Platforms: tiktok, instagram, youtube")
    hashtags: List[str] = Field(default=[], description="List of hashtags")
    timezone: str = Field(default="UTC", description="User timezone")
    
    # Platform-specific settings
    tiktok_settings: dict = Field(default={})
    instagram_settings: dict = Field(default={})
    youtube_settings: dict = Field(default={})


class UpdateScheduleRequest(BaseModel):
    """Request to update a scheduled post"""
    scheduled_time: Optional[datetime] = None
    title: Optional[str] = None
    description: Optional[str] = None
    hashtags: Optional[List[str]] = None
    platforms: Optional[List[str]] = None


class ScheduleResponse(BaseModel):
    """Response for a scheduled post"""
    id: str
    clip_id: str
    scheduled_time: str
    timezone: str
    platforms: List[str]
    title: str
    description: str
    hashtags: List[str]
    status: str
    retry_count: int
    post_results: dict
    error_message: Optional[str]
    created_at: str
    posted_at: Optional[str]


class ScheduleStatsResponse(BaseModel):
    """Response for scheduler statistics"""
    total: int
    pending: int
    completed: int
    failed: int
    retrying: int
    cancelled: int
    next_post: Optional[str]


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/", response_model=ScheduleResponse)
async def create_schedule(request: CreateScheduleRequest):
    """
    Create a new scheduled post
    
    Schedule a clip to be posted to social media at a specified time.
    """
    scheduler = get_scheduler()
    
    # Convert platform strings to enums
    platforms = []
    for p in request.platforms:
        try:
            platforms.append(Platform(p.lower()))
        except ValueError:
            raise HTTPException(400, f"Invalid platform: {p}")
    
    if not platforms:
        raise HTTPException(400, "At least one platform is required")
    
    post = scheduler.create_schedule(
        clip_id=request.clip_id,
        video_path=request.video_path,
        title=request.title,
        description=request.description,
        scheduled_time=request.scheduled_time,
        platforms=platforms,
        hashtags=request.hashtags,
        timezone=request.timezone,
        tiktok=request.tiktok_settings,
        instagram=request.instagram_settings,
        youtube=request.youtube_settings
    )
    
    return _to_response(post)


@router.get("/", response_model=List[ScheduleResponse])
async def list_schedules(
    status: Optional[str] = None,
    platform: Optional[str] = None,
    limit: int = 50
):
    """
    List all scheduled posts
    
    Filter by status (pending, completed, failed, etc.) or platform.
    """
    scheduler = get_scheduler()
    
    status_enum = None
    platform_enum = None
    
    if status:
        try:
            status_enum = ScheduleStatus(status.lower())
        except ValueError:
            raise HTTPException(400, f"Invalid status: {status}")
    
    if platform:
        try:
            platform_enum = Platform(platform.lower())
        except ValueError:
            raise HTTPException(400, f"Invalid platform: {platform}")
    
    posts = scheduler.list_schedules(status_enum, platform_enum, limit)
    return [_to_response(p) for p in posts]


@router.get("/stats", response_model=ScheduleStatsResponse)
async def get_schedule_stats():
    """Get scheduler statistics"""
    scheduler = get_scheduler()
    stats = scheduler.get_stats()
    
    return ScheduleStatsResponse(
        total=stats["total"],
        pending=stats["pending"],
        completed=stats["completed"],
        failed=stats["failed"],
        retrying=stats["retrying"],
        cancelled=stats["cancelled"],
        next_post=stats["next_post"].isoformat() if stats["next_post"] else None
    )


@router.get("/upcoming")
async def get_upcoming_schedules(hours: int = 24):
    """Get posts scheduled in the next N hours"""
    scheduler = get_scheduler()
    posts = scheduler.get_upcoming(hours)
    return [_to_response(p) for p in posts]


@router.get("/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(schedule_id: str):
    """Get a specific scheduled post"""
    scheduler = get_scheduler()
    post = scheduler.get_schedule(schedule_id)
    
    if not post:
        raise HTTPException(404, f"Schedule not found: {schedule_id}")
    
    return _to_response(post)


@router.put("/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(schedule_id: str, request: UpdateScheduleRequest):
    """
    Update a scheduled post
    
    Only pending posts can be updated.
    """
    scheduler = get_scheduler()
    
    platforms = None
    if request.platforms:
        platforms = []
        for p in request.platforms:
            try:
                platforms.append(Platform(p.lower()))
            except ValueError:
                raise HTTPException(400, f"Invalid platform: {p}")
    
    post = scheduler.update_schedule(
        schedule_id=schedule_id,
        scheduled_time=request.scheduled_time,
        title=request.title,
        description=request.description,
        hashtags=request.hashtags,
        platforms=platforms
    )
    
    if not post:
        raise HTTPException(404, f"Schedule not found or cannot be updated: {schedule_id}")
    
    return _to_response(post)


@router.post("/{schedule_id}/cancel")
async def cancel_schedule(schedule_id: str):
    """Cancel a scheduled post"""
    scheduler = get_scheduler()
    success = scheduler.cancel_schedule(schedule_id)
    
    if not success:
        raise HTTPException(404, f"Schedule not found or cannot be cancelled: {schedule_id}")
    
    return {"success": True, "message": f"Schedule {schedule_id} cancelled"}


@router.delete("/{schedule_id}")
async def delete_schedule(schedule_id: str):
    """Delete a scheduled post"""
    scheduler = get_scheduler()
    success = scheduler.delete_schedule(schedule_id)
    
    if not success:
        raise HTTPException(404, f"Schedule not found: {schedule_id}")
    
    return {"success": True, "message": f"Schedule {schedule_id} deleted"}


@router.post("/{schedule_id}/execute")
async def execute_schedule_now(schedule_id: str, background_tasks: BackgroundTasks):
    """
    Execute a scheduled post immediately
    
    Useful for testing or manual override.
    """
    scheduler = get_scheduler()
    post = scheduler.get_schedule(schedule_id)
    
    if not post:
        raise HTTPException(404, f"Schedule not found: {schedule_id}")
    
    if post.status not in [ScheduleStatus.PENDING, ScheduleStatus.RETRYING]:
        raise HTTPException(400, f"Cannot execute post with status: {post.status.value}")
    
    # Execute in background
    background_tasks.add_task(scheduler._execute_post, post)
    
    return {"success": True, "message": f"Post {schedule_id} execution started"}


# ============================================================================
# Helper Functions
# ============================================================================

def _to_response(post) -> ScheduleResponse:
    """Convert ScheduledPost to API response"""
    return ScheduleResponse(
        id=post.id,
        clip_id=post.clip_id,
        scheduled_time=post.scheduled_time.isoformat(),
        timezone=post.timezone,
        platforms=[p.value for p in post.platforms],
        title=post.title,
        description=post.description,
        hashtags=post.hashtags,
        status=post.status.value,
        retry_count=post.retry_count,
        post_results=post.post_results,
        error_message=post.error_message,
        created_at=post.created_at.isoformat(),
        posted_at=post.posted_at.isoformat() if post.posted_at else None
    )
