"""
ViralClip Configuration
Centralized settings management using Pydantic Settings
"""

from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import List
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # ==========================================================================
    # Application
    # ==========================================================================
    app_name: str = "ViralClip"
    debug: bool = False
    app_version: str = "1.1.0"

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
    instagram_access_token: str = Field(default="", description="Instagram Access Token")
    instagram_business_account_id: str = Field(default="", description="Instagram Business ID")
    youtube_client_id: str = Field(default="", description="YouTube Client ID")
    youtube_client_secret: str = Field(default="", description="YouTube Client Secret")
    
    # ==========================================================================
    # Processing Settings
    # ==========================================================================
    whisper_model: str = Field(default="base", description="Whisper model size")
    min_clip_duration: int = Field(default=45, ge=30, le=60)
    max_clip_duration: int = Field(default=60, ge=45, le=180)
    viral_moments_count: int = Field(default=5, ge=3, le=15)
    max_upload_size_mb: int = Field(default=1024, ge=50, le=10240, description="Max upload file size in MB")
    job_worker_concurrency: int = Field(default=1, ge=1, le=4, description="Concurrent processing workers")
    max_pending_jobs: int = Field(default=10, ge=1, le=200, description="Max queued pending jobs")
    enable_beta_social_posting: bool = Field(default=False, description="Enable beta social posting APIs")

    # ==========================================================================
    # Security
    # ==========================================================================
    api_key: str = Field(default="", description="Optional API key for /api and /ws routes")
    cors_allowed_origins: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:8000",
            "http://127.0.0.1:8000"
        ],
        description="Allowed CORS origins"
    )

    # ==========================================================================
    # Paths
    # ==========================================================================
    output_dir: str = Field(default="output", description="Output directory for clips")
    temp_dir: str = Field(default="temp", description="Temporary processing directory")
    data_dir: str = Field(default="data", description="Persistent application data directory")

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value):
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
