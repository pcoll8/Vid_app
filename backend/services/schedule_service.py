"""
Schedule Service
Manages scheduled social media posts with background execution
"""

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Callable, Dict, Any

from ..utils.logger import get_logger
from ..config import get_settings
from ..models.scheduled_post import ScheduledPost, ScheduleStatus, Platform
from .social_poster import SocialPoster, PostResult

logger = get_logger()


class ScheduleService:
    """
    Manages scheduled posts with persistence and background execution
    
    Features:
    - Schedule posts for future times
    - Automatic retry on failure
    - Background job runner
    - Persistence via JSON (can be upgraded to SQLite/PostgreSQL)
    """
    
    def __init__(self, data_dir: str = "data"):
        self.settings = get_settings()
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.schedule_file = self.data_dir / "scheduled_posts.json"
        
        self._posts: Dict[str, ScheduledPost] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self.social_poster = SocialPoster()
        
        # Load existing schedules
        self._load_schedules()
    
    def _load_schedules(self):
        """Load scheduled posts from disk"""
        if self.schedule_file.exists():
            try:
                with open(self.schedule_file, 'r') as f:
                    data = json.load(f)
                    for post_data in data:
                        post = ScheduledPost.from_dict(post_data)
                        self._posts[post.id] = post
                logger.info(f"Loaded {len(self._posts)} scheduled posts")
            except Exception as e:
                logger.error(f"Failed to load schedules: {e}")
    
    def _save_schedules(self):
        """Persist scheduled posts to disk"""
        try:
            data = [post.to_dict() for post in self._posts.values()]
            with open(self.schedule_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save schedules: {e}")
    
    # =========================================================================
    # CRUD Operations
    # =========================================================================
    
    def create_schedule(
        self,
        clip_id: str,
        video_path: str,
        title: str,
        description: str,
        scheduled_time: datetime,
        platforms: List[Platform],
        hashtags: List[str] = None,
        timezone: str = "UTC",
        **platform_settings
    ) -> ScheduledPost:
        """
        Schedule a new post
        
        Args:
            clip_id: ID of the clip to post
            video_path: Path to the video file
            title: Post title
            description: Post description
            scheduled_time: When to post (UTC)
            platforms: List of platforms to post to
            hashtags: Optional list of hashtags
            timezone: User's timezone
            **platform_settings: Platform-specific settings
        
        Returns:
            ScheduledPost object
        """
        post = ScheduledPost(
            clip_id=clip_id,
            video_path=video_path,
            title=title,
            description=description,
            scheduled_time=scheduled_time,
            platforms=platforms,
            hashtags=hashtags or [],
            timezone=timezone,
            tiktok_settings=platform_settings.get("tiktok", {}),
            instagram_settings=platform_settings.get("instagram", {}),
            youtube_settings=platform_settings.get("youtube", {})
        )
        
        self._posts[post.id] = post
        self._save_schedules()
        
        logger.info(f"Created scheduled post {post.id} for {scheduled_time}")
        return post
    
    def get_schedule(self, schedule_id: str) -> Optional[ScheduledPost]:
        """Get a specific scheduled post"""
        return self._posts.get(schedule_id)
    
    def list_schedules(
        self,
        status: Optional[ScheduleStatus] = None,
        platform: Optional[Platform] = None,
        limit: int = 50
    ) -> List[ScheduledPost]:
        """List scheduled posts with optional filters"""
        posts = list(self._posts.values())
        
        if status:
            posts = [p for p in posts if p.status == status]
        
        if platform:
            posts = [p for p in posts if platform in p.platforms]
        
        # Sort by scheduled time
        posts.sort(key=lambda p: p.scheduled_time)
        
        return posts[:limit]
    
    def update_schedule(
        self,
        schedule_id: str,
        scheduled_time: Optional[datetime] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        hashtags: Optional[List[str]] = None,
        platforms: Optional[List[Platform]] = None
    ) -> Optional[ScheduledPost]:
        """Update a scheduled post (only if still pending)"""
        post = self._posts.get(schedule_id)
        
        if not post:
            return None
        
        if post.status != ScheduleStatus.PENDING:
            logger.warning(f"Cannot update non-pending post {schedule_id}")
            return None
        
        if scheduled_time:
            post.scheduled_time = scheduled_time
        if title:
            post.title = title
        if description:
            post.description = description
        if hashtags is not None:
            post.hashtags = hashtags
        if platforms:
            post.platforms = platforms
        
        post.updated_at = datetime.now()
        self._save_schedules()
        
        logger.info(f"Updated scheduled post {schedule_id}")
        return post
    
    def cancel_schedule(self, schedule_id: str) -> bool:
        """Cancel a scheduled post"""
        post = self._posts.get(schedule_id)
        
        if not post:
            return False
        
        if post.status not in [ScheduleStatus.PENDING, ScheduleStatus.RETRYING]:
            logger.warning(f"Cannot cancel post {schedule_id} with status {post.status}")
            return False
        
        post.status = ScheduleStatus.CANCELLED
        post.updated_at = datetime.now()
        self._save_schedules()
        
        logger.info(f"Cancelled scheduled post {schedule_id}")
        return True
    
    def delete_schedule(self, schedule_id: str) -> bool:
        """Delete a scheduled post"""
        if schedule_id in self._posts:
            del self._posts[schedule_id]
            self._save_schedules()
            logger.info(f"Deleted scheduled post {schedule_id}")
            return True
        return False
    
    # =========================================================================
    # Background Job Runner
    # =========================================================================
    
    async def start_scheduler(self, check_interval: int = 60):
        """
        Start the background scheduler
        
        Args:
            check_interval: How often to check for due posts (seconds)
        """
        if self._running:
            logger.warning("Scheduler already running")
            return
        
        self._running = True
        logger.info(f"Starting scheduler (interval: {check_interval}s)")
        
        while self._running:
            try:
                await self._process_due_posts()
            except Exception as e:
                logger.exception(f"Scheduler error: {e}")
            
            await asyncio.sleep(check_interval)
    
    def stop_scheduler(self):
        """Stop the background scheduler"""
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("Scheduler stopped")
    
    async def _process_due_posts(self):
        """Process all posts that are due"""
        due_posts = [p for p in self._posts.values() if p.is_due()]
        
        if not due_posts:
            return
        
        logger.info(f"Processing {len(due_posts)} due posts")
        
        for post in due_posts:
            await self._execute_post(post)
    
    async def _execute_post(self, post: ScheduledPost):
        """Execute a single scheduled post"""
        logger.info(f"Executing scheduled post {post.id} to {[p.value for p in post.platforms]}")
        
        post.status = ScheduleStatus.PROCESSING
        post.updated_at = datetime.now()
        self._save_schedules()
        
        try:
            # Post to each platform
            results = await self.social_poster.post_to_all(
                video_path=post.video_path,
                title=post.title,
                description=post.description,
                hashtags=post.hashtags,
                platforms=post.platforms
            )
            
            # Store results
            all_success = True
            for result in results:
                post.post_results[result.platform.value] = {
                    "success": result.success,
                    "post_id": result.post_id,
                    "post_url": result.post_url,
                    "error": result.error_message
                }
                if not result.success:
                    all_success = False
            
            if all_success:
                post.status = ScheduleStatus.COMPLETED
                post.posted_at = datetime.now()
                logger.info(f"Successfully posted {post.id}")
            else:
                # Some platforms failed
                if post.can_retry():
                    post.status = ScheduleStatus.RETRYING
                    post.retry_count += 1
                    # Retry in 5 minutes
                    post.scheduled_time = datetime.now() + timedelta(minutes=5)
                    logger.warning(f"Post {post.id} partially failed, retry {post.retry_count}/{post.max_retries}")
                else:
                    post.status = ScheduleStatus.FAILED
                    post.error_message = "Max retries exceeded"
                    logger.error(f"Post {post.id} failed after {post.retry_count} retries")
        
        except Exception as e:
            logger.exception(f"Error executing post {post.id}: {e}")
            post.status = ScheduleStatus.FAILED
            post.error_message = str(e)
        
        post.updated_at = datetime.now()
        self._save_schedules()
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def get_upcoming(self, hours: int = 24) -> List[ScheduledPost]:
        """Get posts scheduled in the next N hours"""
        cutoff = datetime.now() + timedelta(hours=hours)
        return [
            p for p in self._posts.values()
            if p.status == ScheduleStatus.PENDING and p.scheduled_time <= cutoff
        ]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get scheduler statistics"""
        posts = list(self._posts.values())
        return {
            "total": len(posts),
            "pending": sum(1 for p in posts if p.status == ScheduleStatus.PENDING),
            "completed": sum(1 for p in posts if p.status == ScheduleStatus.COMPLETED),
            "failed": sum(1 for p in posts if p.status == ScheduleStatus.FAILED),
            "retrying": sum(1 for p in posts if p.status == ScheduleStatus.RETRYING),
            "cancelled": sum(1 for p in posts if p.status == ScheduleStatus.CANCELLED),
            "next_post": min(
                (p.scheduled_time for p in posts if p.status == ScheduleStatus.PENDING),
                default=None
            )
        }


# Global scheduler instance
_scheduler: Optional[ScheduleService] = None


def get_scheduler() -> ScheduleService:
    """Get or create the global scheduler instance"""
    global _scheduler
    if _scheduler is None:
        _scheduler = ScheduleService()
    return _scheduler
