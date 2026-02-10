"""
Social Media Posting Service
Direct posting to Instagram and YouTube
"""

import asyncio
from typing import Optional, Callable, Dict, List
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

from ..utils.logger import get_logger
from ..config import get_settings

logger = get_logger()


class Platform(str, Enum):
    """Supported social media platforms"""
    INSTAGRAM = "instagram"
    YOUTUBE = "youtube"


@dataclass
class PostResult:
    """Result of a social media post"""
    platform: Platform
    success: bool
    post_id: Optional[str] = None
    post_url: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class SocialProfile:
    """Social media profile configuration"""
    platform: Platform
    account_name: str
    is_active: bool = True
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    account_id: Optional[str] = None


class SocialPoster:
    """Handles posting to multiple social media platforms"""
    
    def __init__(self):
        self.settings = get_settings()
        self.beta_enabled = self.settings.enable_beta_social_posting
        self._profiles: Dict[str, SocialProfile] = {}

    def _beta_disabled_result(self, platform: Platform) -> PostResult:
        return PostResult(
            platform=platform,
            success=False,
            error_message=(
                "Social posting is beta-disabled. "
                "Set ENABLE_BETA_SOCIAL_POSTING=true to enable."
            )
        )
    
    def add_profile(self, profile: SocialProfile):
        """Add or update a social profile"""
        key = f"{profile.platform}_{profile.account_name}"
        self._profiles[key] = profile
        logger.info(f"Added profile: {profile.platform} - {profile.account_name}")
    
    def get_profiles(self, platform: Optional[Platform] = None) -> List[SocialProfile]:
        """Get configured profiles, optionally filtered by platform"""
        profiles = list(self._profiles.values())
        if platform:
            profiles = [p for p in profiles if p.platform == platform]
        return profiles
    
    async def post_to_instagram(
        self,
        video_path: str,
        caption: str,
        hashtags: List[str] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> PostResult:
        """
        Post video to Instagram Reels
        
        Uses Instagram Graph API (requires Facebook Business account)
        """
        if not self.beta_enabled:
            return self._beta_disabled_result(Platform.INSTAGRAM)

        logger.info(f"Posting to Instagram: {caption[:50]}...")
        
        if not self.settings.instagram_access_token:
            return PostResult(
                platform=Platform.INSTAGRAM,
                success=False,
                error_message="Instagram API not configured"
            )
        
        if progress_callback:
            progress_callback(0, "Preparing Instagram upload...")
        
        try:
            import aiohttp
            
            # Instagram Graph API requires the video to be publicly accessible
            # This typically means uploading to a public URL first
            
            if progress_callback:
                progress_callback(20, "Creating media container...")
            
            # Full caption with hashtags
            full_caption = caption
            if hashtags:
                full_caption += "\n\n" + " ".join(hashtags)
            
            # Create media container
            async with aiohttp.ClientSession() as session:
                # This is a simplified flow - actual implementation needs:
                # 1. Host video on public URL
                # 2. Create container with video URL
                # 3. Poll for processing
                # 4. Publish
                
                container_url = f"https://graph.facebook.com/v18.0/{self.settings.instagram_business_account_id}/media"
                
                # For Reels, we need video_url (must be publicly accessible)
                # In production, you'd upload to S3 first and use that URL
                
                logger.warning("Instagram posting requires publicly accessible video URL")
                
                return PostResult(
                    platform=Platform.INSTAGRAM,
                    success=False,
                    error_message="Video must be uploaded to public URL first (S3). Enable S3 upload for Instagram posting."
                )
                
        except Exception as e:
            logger.error(f"Instagram post failed: {e}")
            return PostResult(
                platform=Platform.INSTAGRAM,
                success=False,
                error_message=str(e)
            )
    
    async def post_to_youtube(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: List[str] = None,
        is_short: bool = True,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> PostResult:
        """
        Post video to YouTube (as Short if vertical)
        
        Uses YouTube Data API v3
        """
        if not self.beta_enabled:
            return self._beta_disabled_result(Platform.YOUTUBE)

        logger.info(f"Posting to YouTube: {title}")
        
        if not self.settings.youtube_client_id:
            return PostResult(
                platform=Platform.YOUTUBE,
                success=False,
                error_message="YouTube API not configured"
            )
        
        if progress_callback:
            progress_callback(0, "Preparing YouTube upload...")
        
        try:
            # Add #Shorts to title/description for YouTube Shorts
            if is_short and "#Shorts" not in description:
                description = f"{description}\n\n#Shorts"
            
            # YouTube API requires OAuth2 authentication
            # This needs google-auth and google-api-python-client
            
            try:
                from google.oauth2.credentials import Credentials
                from googleapiclient.discovery import build
                from googleapiclient.http import MediaFileUpload
            except ImportError:
                return PostResult(
                    platform=Platform.YOUTUBE,
                    success=False,
                    error_message="google-api-python-client not installed"
                )
            
            # In production, you'd load saved OAuth tokens
            # For now, we provide the structure
            
            if progress_callback:
                progress_callback(30, "YouTube OAuth required...")
            
            logger.warning("YouTube posting requires OAuth2 authentication flow")
            
            return PostResult(
                platform=Platform.YOUTUBE,
                success=False,
                error_message="YouTube OAuth2 authentication required. Run OAuth flow first."
            )
            
        except Exception as e:
            logger.error(f"YouTube post failed: {e}")
            return PostResult(
                platform=Platform.YOUTUBE,
                success=False,
                error_message=str(e)
            )
    
    async def post_to_all(
        self,
        video_path: str,
        title: str,
        description: str,
        hashtags: List[str] = None,
        platforms: List[Platform] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> List[PostResult]:
        """
        Post to all configured platforms
        
        Args:
            video_path: Path to video file
            title: Video title
            description: Video description
            hashtags: List of hashtags
            platforms: Specific platforms (default: all configured)
            progress_callback: Optional progress callback
            
        Returns:
            List of PostResult for each platform
        """
        if platforms is None:
            platforms = [Platform.INSTAGRAM, Platform.YOUTUBE]

        if not self.beta_enabled:
            return [self._beta_disabled_result(platform) for platform in platforms]
        
        results = []
        total = len(platforms)
        
        for i, platform in enumerate(platforms):
            platform_progress = lambda p, m: progress_callback(
                ((i + p / 100) / total) * 100, f"[{platform.value}] {m}"
            ) if progress_callback else None
            
            if platform == Platform.INSTAGRAM:
                caption = f"{title}\n\n{description}"
                result = await self.post_to_instagram(
                    video_path, caption, hashtags, platform_progress
                )
            elif platform == Platform.YOUTUBE:
                result = await self.post_to_youtube(
                    video_path, title, description, hashtags, True, platform_progress
                )
            else:
                continue
            
            results.append(result)
        
        return results
