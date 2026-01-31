"""
Clips Router
Handles clip management and social posting
"""

import os
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..models.clip import Clip
from ..services.social_poster import SocialPoster, Platform, PostResult
from ..utils.logger import get_logger

router = APIRouter(prefix="/api/clips", tags=["clips"])
logger = get_logger()

# Reference to the clips database from jobs router
# In production, use a proper database
from .jobs import clips_db

social_poster = SocialPoster()


class SocialPostRequest(BaseModel):
    """Request to post a clip to social media"""
    platforms: List[str]  # ["tiktok", "instagram", "youtube"]
    custom_title: Optional[str] = None
    custom_description: Optional[str] = None
    custom_hashtags: Optional[List[str]] = None


class SocialPostResponse(BaseModel):
    """Response from social posting"""
    results: List[dict]


@router.get("/", response_model=List[Clip])
async def list_all_clips():
    """List all clips across all jobs"""
    all_clips = []
    for clips in clips_db.values():
        all_clips.extend(clips)
    return all_clips


@router.get("/{clip_id}", response_model=Clip)
async def get_clip(clip_id: str):
    """Get a specific clip by ID"""
    for clips in clips_db.values():
        for clip in clips:
            if clip.id == clip_id:
                return clip
    raise HTTPException(404, "Clip not found")


@router.delete("/{clip_id}")
async def delete_clip(clip_id: str):
    """Delete a clip"""
    for job_id, clips in clips_db.items():
        for i, clip in enumerate(clips):
            if clip.id == clip_id:
                # Delete file if exists
                if clip.file_path and os.path.exists(clip.file_path):
                    os.remove(clip.file_path)
                    # Also delete thumbnail
                    thumb_path = clip.file_path.rsplit('.', 1)[0] + '_thumb.jpg'
                    if os.path.exists(thumb_path):
                        os.remove(thumb_path)
                
                clips.pop(i)
                return {"status": "deleted"}
    
    raise HTTPException(404, "Clip not found")


@router.post("/{clip_id}/post", response_model=SocialPostResponse)
async def post_clip_to_social(clip_id: str, request: SocialPostRequest):
    """Post a clip to social media platforms"""
    
    # Find the clip
    clip = None
    for clips in clips_db.values():
        for c in clips:
            if c.id == clip_id:
                clip = c
                break
        if clip:
            break
    
    if not clip:
        raise HTTPException(404, "Clip not found")
    
    if not clip.file_path or not os.path.exists(clip.file_path):
        raise HTTPException(400, "Clip file not found")
    
    # Prepare content
    title = request.custom_title or clip.title
    description = request.custom_description or clip.description
    hashtags = request.custom_hashtags or []
    
    # Parse platforms
    platforms = []
    for p in request.platforms:
        try:
            platforms.append(Platform(p.lower()))
        except ValueError:
            logger.warning(f"Invalid platform: {p}")
    
    if not platforms:
        raise HTTPException(400, "No valid platforms specified")
    
    # Post to platforms
    results = await social_poster.post_to_all(
        video_path=clip.file_path,
        title=title,
        description=description,
        hashtags=hashtags,
        platforms=platforms
    )
    
    # Store results in clip
    for result in results:
        clip.social_posts.append({
            "platform": result.platform.value,
            "success": result.success,
            "post_id": result.post_id,
            "post_url": result.post_url,
            "error": result.error_message
        })
    
    return SocialPostResponse(
        results=[
            {
                "platform": r.platform.value,
                "success": r.success,
                "post_id": r.post_id,
                "post_url": r.post_url,
                "error": r.error_message
            }
            for r in results
        ]
    )


@router.get("/{clip_id}/download")
async def get_clip_download_url(clip_id: str):
    """Get download URL for a clip"""
    for clips in clips_db.values():
        for clip in clips:
            if clip.id == clip_id:
                if clip.s3_url:
                    return {"url": clip.s3_url, "source": "s3"}
                elif clip.file_path and os.path.exists(clip.file_path):
                    # Return local file path (frontend will use /output/ static route)
                    filename = os.path.basename(clip.file_path)
                    return {"url": f"/output/{filename}", "source": "local"}
                else:
                    raise HTTPException(404, "Clip file not found")
    
    raise HTTPException(404, "Clip not found")
