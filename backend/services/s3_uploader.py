"""
S3 Uploader Service
Background upload to AWS S3 with progress tracking
"""

import asyncio
import os
from typing import Optional, Callable, List
from pathlib import Path
import mimetypes

from ..utils.logger import get_logger
from ..config import get_settings

logger = get_logger()


class S3Uploader:
    """Async S3 file uploader with multipart support"""
    
    def __init__(self):
        self.settings = get_settings()
        self._client = None
        self._initialized = False
    
    def _ensure_initialized(self):
        """Lazy initialize S3 client"""
        if self._initialized:
            return
        
        if not self.settings.aws_access_key_id or not self.settings.aws_secret_access_key:
            logger.warning("AWS credentials not configured, S3 upload disabled")
            return
        
        try:
            import boto3
            from botocore.config import Config
            
            config = Config(
                retries={'max_attempts': 3, 'mode': 'adaptive'},
                max_pool_connections=10
            )
            
            self._client = boto3.client(
                's3',
                aws_access_key_id=self.settings.aws_access_key_id,
                aws_secret_access_key=self.settings.aws_secret_access_key,
                region_name=self.settings.aws_region,
                config=config
            )
            
            self._initialized = True
            logger.info(f"S3 client initialized for bucket: {self.settings.s3_bucket_name}")
            
        except ImportError:
            logger.error("boto3 not installed")
            raise
    
    async def upload_file(
        self,
        local_path: str,
        s3_key: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Optional[str]:
        """
        Upload a file to S3
        
        Args:
            local_path: Local file path
            s3_key: S3 object key (default: filename)
            progress_callback: Optional progress callback
            
        Returns:
            S3 URL or None if upload disabled/failed
        """
        self._ensure_initialized()
        
        if not self._client:
            logger.info("S3 upload skipped (not configured)")
            return None
        
        if not os.path.exists(local_path):
            logger.error(f"File not found: {local_path}")
            return None
        
        # Generate S3 key if not provided
        if not s3_key:
            s3_key = f"clips/{Path(local_path).name}"
        
        file_size = os.path.getsize(local_path)
        logger.info(f"Uploading to S3: {s3_key} ({file_size / 1024 / 1024:.1f} MB)")
        
        if progress_callback:
            progress_callback(0, "Starting S3 upload...")
        
        # Get content type
        content_type, _ = mimetypes.guess_type(local_path)
        content_type = content_type or 'application/octet-stream'
        
        # Upload in thread pool
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None,
                self._do_upload,
                local_path,
                s3_key,
                content_type,
                file_size,
                progress_callback
            )
            
            # Generate URL
            url = f"https://{self.settings.s3_bucket_name}.s3.{self.settings.aws_region}.amazonaws.com/{s3_key}"
            
            if progress_callback:
                progress_callback(100, "Upload complete")
            
            logger.info(f"Upload complete: {url}")
            return url
            
        except Exception as e:
            logger.error(f"S3 upload failed: {e}")
            if progress_callback:
                progress_callback(0, f"Upload failed: {str(e)}")
            return None
    
    def _do_upload(
        self,
        local_path: str,
        s3_key: str,
        content_type: str,
        file_size: int,
        progress_callback: Optional[Callable[[float, str], None]]
    ):
        """Perform the actual upload (blocking)"""
        
        # Progress callback wrapper for boto3
        uploaded_bytes = 0
        
        def upload_progress(bytes_amount):
            nonlocal uploaded_bytes
            uploaded_bytes += bytes_amount
            if progress_callback:
                percent = (uploaded_bytes / file_size) * 100
                progress_callback(percent, f"Uploading: {percent:.0f}%")
        
        # Use multipart upload for files > 5MB
        if file_size > 5 * 1024 * 1024:
            from boto3.s3.transfer import TransferConfig
            
            config = TransferConfig(
                multipart_threshold=5 * 1024 * 1024,
                multipart_chunksize=5 * 1024 * 1024,
                max_concurrency=4,
                use_threads=True
            )
            
            self._client.upload_file(
                local_path,
                self.settings.s3_bucket_name,
                s3_key,
                ExtraArgs={'ContentType': content_type},
                Config=config,
                Callback=upload_progress
            )
        else:
            with open(local_path, 'rb') as f:
                self._client.put_object(
                    Bucket=self.settings.s3_bucket_name,
                    Key=s3_key,
                    Body=f,
                    ContentType=content_type
                )
            if progress_callback:
                progress_callback(100, "Upload complete")
    
    async def upload_batch(
        self,
        file_paths: List[str],
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> List[Optional[str]]:
        """
        Upload multiple files to S3
        
        Args:
            file_paths: List of local file paths
            progress_callback: Optional progress callback
            
        Returns:
            List of S3 URLs (None for failed uploads)
        """
        if not file_paths:
            return []
        
        urls = []
        total = len(file_paths)
        
        for i, path in enumerate(file_paths):
            def batch_progress(pct, msg):
                if progress_callback:
                    overall = ((i + pct / 100) / total) * 100
                    progress_callback(overall, f"[{i+1}/{total}] {msg}")
            
            url = await self.upload_file(path, progress_callback=batch_progress)
            urls.append(url)
        
        return urls
    
    async def delete_file(self, s3_key: str) -> bool:
        """Delete a file from S3"""
        self._ensure_initialized()
        
        if not self._client:
            return False
        
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._client.delete_object(
                    Bucket=self.settings.s3_bucket_name,
                    Key=s3_key
                )
            )
            logger.info(f"Deleted from S3: {s3_key}")
            return True
        except Exception as e:
            logger.error(f"S3 delete failed: {e}")
            return False
