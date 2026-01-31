"""
ViralClip Configuration
Centralized settings management using Pydantic Settings
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # ==========================================================================
    # Application
    # ==========================================================================
    app_name: str = "ViralClip"
    debug: bool = False
    
    # ==========================================================================
    # Google Gemini
    # ==========================================================================
    gemini_api_key: str = Field(default="", description="Google Gemini API Key")
    
    # ==========================================================================
    # AWS S3
    # ==========================================================================
    aws_access_key_id: str = Field(default="", description="AWS Access Key ID")
    aws_secret_access_key: str = Field(default="", description="AWS Secret Key")
    aws_region: str = Field(default="us-east-1", description="AWS Region")
    s3_bucket_name: str = Field(default="", description="S3 Bucket Name")
    
    # ==========================================================================
    # ElevenLabs
    # ==========================================================================
    elevenlabs_api_key: str = Field(default="", description="ElevenLabs API Key")
    
    # ==========================================================================
    # Social Media APIs
    # ==========================================================================
    tiktok_client_key: str = Field(default="", description="TikTok Client Key")
    tiktok_client_secret: str = Field(default="", description="TikTok Client Secret")
    instagram_access_token: str = Field(default="", description="Instagram Access Token")
    instagram_business_account_id: str = Field(default="", description="Instagram Business ID")
    youtube_client_id: str = Field(default="", description="YouTube Client ID")
    youtube_client_secret: str = Field(default="", description="YouTube Client Secret")
    
    # ==========================================================================
    # Processing Settings
    # ==========================================================================
    whisper_model: str = Field(default="base", description="Whisper model size")
    min_clip_duration: int = Field(default=15, ge=5, le=30)
    max_clip_duration: int = Field(default=60, ge=30, le=180)
    viral_moments_count: int = Field(default=5, ge=3, le=15)
    
    # ==========================================================================
    # Paths
    # ==========================================================================
    output_dir: str = Field(default="output", description="Output directory for clips")
    temp_dir: str = Field(default="temp", description="Temporary processing directory")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
