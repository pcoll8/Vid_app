"""
YouTube Downloader Service
Downloads videos from YouTube using yt-dlp
"""

import os
import asyncio
from typing import Optional, Tuple, Callable
from pathlib import Path
import yt_dlp

from ..utils.logger import get_logger

logger = get_logger()


class YouTubeDownloader:
    """Service for downloading videos from YouTube"""
    
    def __init__(self, temp_dir: str = "temp"):
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
    
    async def download(
        self, 
        url: str, 
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Tuple[str, dict]:
        """
        Download a video from YouTube
        
        Args:
            url: YouTube URL
            progress_callback: Optional callback (progress_percent, status_message)
            
        Returns:
            Tuple of (file_path, video_info)
        """
        logger.info(f"Starting download: {url}")
        
        video_info = {}
        output_path = None
        
        def progress_hook(d):
            nonlocal output_path
            if d['status'] == 'downloading':
                if progress_callback and 'downloaded_bytes' in d and 'total_bytes' in d:
                    percent = (d['downloaded_bytes'] / d['total_bytes']) * 100
                    progress_callback(percent, f"Downloading: {percent:.1f}%")
            elif d['status'] == 'finished':
                output_path = d['filename']
                logger.info(f"Download finished: {output_path}")
                if progress_callback:
                    progress_callback(100, "Download complete")
        
        ydl_opts = {
            'format': 'best[height<=1080][ext=mp4]/best[height<=1080]/best',
            'outtmpl': str(self.temp_dir / '%(id)s.%(ext)s'),
            'progress_hooks': [progress_hook],
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        # Run yt-dlp in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        
        def do_download():
            nonlocal video_info, output_path
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                video_info = {
                    'id': info.get('id'),
                    'title': info.get('title'),
                    'duration': info.get('duration'),
                    'description': info.get('description', ''),
                    'uploader': info.get('uploader'),
                    'view_count': info.get('view_count', 0),
                    'like_count': info.get('like_count', 0),
                }
                if not output_path:
                    output_path = str(self.temp_dir / f"{info['id']}.{info.get('ext', 'mp4')}")
        
        await loop.run_in_executor(None, do_download)
        
        if not output_path or not os.path.exists(output_path):
            raise Exception("Failed to download video")
        
        logger.info(f"Video downloaded: {video_info.get('title', 'Unknown')}")
        return output_path, video_info
    
    async def get_info(self, url: str) -> dict:
        """Get video info without downloading"""
        logger.info(f"Fetching video info: {url}")
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        loop = asyncio.get_event_loop()
        
        def do_extract():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)
        
        info = await loop.run_in_executor(None, do_extract)
        
        return {
            'id': info.get('id'),
            'title': info.get('title'),
            'duration': info.get('duration'),
            'description': info.get('description', ''),
            'uploader': info.get('uploader'),
            'thumbnail': info.get('thumbnail'),
        }
