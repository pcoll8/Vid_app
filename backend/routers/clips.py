"""
Clips Router
Handles clip management and social posting.
"""

import os
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from ..config import get_settings
from ..models.clip import Clip
from ..services.job_store import get_job_store
from ..services.social_poster import Platform, SocialPoster
from ..utils.logger import get_logger
from .jobs import clips_db, delete_clip_record

router = APIRouter(prefix="/api/clips", tags=["clips"])
logger = get_logger()

social_poster = SocialPoster()
job_store = get_job_store()


class SocialPostRequest(BaseModel):
    """Request to post a clip to social media."""
    platforms: List[str]
    custom_title: Optional[str] = None
    custom_description: Optional[str] = None
    custom_hashtags: Optional[List[str]] = None


class SocialPostResponse(BaseModel):
    """Response from social posting."""
    results: List[dict]


@router.get("/", response_model=List[Clip])
async def list_all_clips():
    """List all clips across all jobs."""
    all_clips: List[Clip] = []
    for clips in clips_db.values():
        all_clips.extend(clips)
    return sorted(all_clips, key=lambda clip: clip.created_at, reverse=True)


@router.get("/{clip_id}", response_model=Clip)
async def get_clip(clip_id: str):
    """Get a specific clip by ID."""
    for clips in clips_db.values():
        for clip in clips:
            if clip.id == clip_id:
                return clip
    raise HTTPException(404, "Clip not found")


@router.delete("/{clip_id}")
async def delete_clip(clip_id: str):
    """Delete a clip and associated files."""
    deleted = await delete_clip_record(clip_id)
    if not deleted:
        raise HTTPException(404, "Clip not found")
    return {"status": "deleted"}


@router.post("/{clip_id}/post", response_model=SocialPostResponse)
async def post_clip_to_social(clip_id: str, request: SocialPostRequest):
    """Post a clip to social media platforms (beta feature gate)."""
    settings = get_settings()
    if not settings.enable_beta_social_posting:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Social posting is beta-disabled. Set ENABLE_BETA_SOCIAL_POSTING=true to enable.",
        )

    clip = None
    for clips in clips_db.values():
        for candidate in clips:
            if candidate.id == clip_id:
                clip = candidate
                break
        if clip:
            break

    if not clip:
        raise HTTPException(404, "Clip not found")

    if not clip.file_path or not os.path.exists(clip.file_path):
        raise HTTPException(400, "Clip file not found")

    title = request.custom_title or clip.title
    description = request.custom_description or clip.description
    hashtags = request.custom_hashtags or []

    platforms = []
    for platform in request.platforms:
        try:
            platforms.append(Platform(platform.lower()))
        except ValueError:
            logger.warning(f"Invalid platform: {platform}")

    if not platforms:
        raise HTTPException(400, "No valid platforms specified")

    results = await social_poster.post_to_all(
        video_path=clip.file_path,
        title=title,
        description=description,
        hashtags=hashtags,
        platforms=platforms,
    )

    for result in results:
        clip.social_posts.append(
            {
                "platform": result.platform.value,
                "success": result.success,
                "post_id": result.post_id,
                "post_url": result.post_url,
                "error": result.error_message,
            }
        )

    await job_store.upsert_clip(clip)

    return SocialPostResponse(
        results=[
            {
                "platform": result.platform.value,
                "success": result.success,
                "post_id": result.post_id,
                "post_url": result.post_url,
                "error": result.error_message,
            }
            for result in results
        ]
    )


@router.get("/{clip_id}/download")
async def get_clip_download_url(clip_id: str):
    """Get download URL for a clip."""
    for clips in clips_db.values():
        for clip in clips:
            if clip.id != clip_id:
                continue

            if clip.s3_url:
                return {"url": clip.s3_url, "source": "s3"}
            if clip.file_path and os.path.exists(clip.file_path):
                filename = os.path.basename(clip.file_path)
                return {"url": f"/output/{filename}", "source": "local"}

            raise HTTPException(404, "Clip file not found")

    raise HTTPException(404, "Clip not found")
