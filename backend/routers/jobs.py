"""
Jobs Router
Handles video processing job creation and management
"""

import asyncio
import os
import shutil
from typing import List, Optional
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from datetime import datetime

from ..models.job import Job, JobCreate, JobStatus
from ..models.clip import Clip
from ..services.youtube_downloader import YouTubeDownloader
from ..services.transcription import TranscriptionService
from ..services.viral_detector import ViralDetector
from ..services.ai_cropping import AICroppingService
from ..services.video_renderer import VideoRenderer
from ..services.s3_uploader import S3Uploader
from ..services.voice_dubber import VoiceDubber
from ..utils.logger import get_logger
from ..config import get_settings
from .websocket import broadcast_progress, broadcast_log

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
logger = get_logger()

# In-memory job storage (use database in production)
jobs_db: dict[str, Job] = {}
clips_db: dict[str, List[Clip]] = {}


@router.post("/", response_model=Job)
async def create_job(
    background_tasks: BackgroundTasks,
    source_url: Optional[str] = Form(None),
    clip_count: int = Form(5),
    min_duration: int = Form(45),
    max_duration: int = Form(60),
    enable_dubbing: bool = Form(False),
    dubbing_language: Optional[str] = Form(None),
    upload_to_s3: bool = Form(True),
    file: Optional[UploadFile] = File(None)
):
    """Create a new video processing job"""
    
    if not source_url and not file:
        raise HTTPException(400, "Either source_url or file must be provided")
    
    # Create job
    job = Job(
        source_url=source_url,
        clip_count=clip_count,
        min_duration=min_duration,
        max_duration=max_duration,
        enable_dubbing=enable_dubbing,
        dubbing_language=dubbing_language,
        upload_to_s3=upload_to_s3
    )
    
    # Handle file upload
    if file:
        settings = get_settings()
        temp_dir = Path(settings.temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = temp_dir / f"{job.id}_{file.filename}"
        with open(file_path, 'wb') as f:
            content = await file.read()
            f.write(content)
        
        job.source_file = str(file_path)
    
    # Store job
    jobs_db[job.id] = job
    clips_db[job.id] = []
    
    # Start processing in background
    background_tasks.add_task(process_job, job.id)
    
    logger.info(f"Job created: {job.id}")
    return job


@router.get("/", response_model=List[Job])
async def list_jobs():
    """List all jobs"""
    return list(jobs_db.values())


@router.get("/{job_id}", response_model=Job)
async def get_job(job_id: str):
    """Get a specific job"""
    if job_id not in jobs_db:
        raise HTTPException(404, "Job not found")
    return jobs_db[job_id]


@router.get("/{job_id}/clips", response_model=List[Clip])
async def get_job_clips(job_id: str):
    """Get clips for a job"""
    if job_id not in clips_db:
        raise HTTPException(404, "Job not found")
    return clips_db[job_id]


@router.delete("/{job_id}")
async def delete_job(job_id: str):
    """Delete a job and its clips"""
    if job_id not in jobs_db:
        raise HTTPException(404, "Job not found")
    
    # Clean up files
    job = jobs_db[job_id]
    if job.source_file and os.path.exists(job.source_file):
        os.remove(job.source_file)
    
    del jobs_db[job_id]
    if job_id in clips_db:
        del clips_db[job_id]
    
    return {"status": "deleted"}


async def process_job(job_id: str):
    """Main job processing pipeline"""
    job = jobs_db.get(job_id)
    if not job:
        return
    
    settings = get_settings()
    
    try:
        # Initialize services
        downloader = YouTubeDownloader(settings.temp_dir)
        transcriber = TranscriptionService()
        detector = ViralDetector()
        cropper = AICroppingService()
        renderer = VideoRenderer(settings.output_dir)
        uploader = S3Uploader()
        dubber = VoiceDubber()
        
        video_path = None
        
        # =================================================================
        # Step 1: Download / Prepare Video
        # =================================================================
        def update_progress(pct, msg):
            job.progress = pct * 0.15  # 0-15% for download
            broadcast_progress(job_id, job.progress, msg)
            broadcast_log(f"[DOWNLOAD] {msg}")
        
        if job.source_url:
            job.status = JobStatus.DOWNLOADING
            broadcast_log(f"Starting download: {job.source_url}")
            
            video_path, video_info = await downloader.download(
                job.source_url, 
                progress_callback=update_progress
            )
            job.video_title = video_info.get('title', 'Untitled')
            job.video_duration = video_info.get('duration', 0)
        else:
            video_path = job.source_file
            job.video_title = Path(video_path).stem
        
        # =================================================================
        # Step 2: Transcribe
        # =================================================================
        def update_progress(pct, msg):
            job.progress = 15 + pct * 0.20  # 15-35%
            broadcast_progress(job_id, job.progress, msg)
            broadcast_log(f"[TRANSCRIBE] {msg}")
        
        job.status = JobStatus.TRANSCRIBING
        broadcast_log("Starting transcription...")
        
        transcript = await transcriber.transcribe(
            video_path,
            progress_callback=update_progress
        )
        broadcast_log(f"Transcribed {len(transcript.segments)} segments in {transcript.language}")
        
        # =================================================================
        # Step 3: Detect Viral Moments
        # =================================================================
        def update_progress(pct, msg):
            job.progress = 35 + pct * 0.15  # 35-50%
            broadcast_progress(job_id, job.progress, msg)
            broadcast_log(f"[ANALYZE] {msg}")
        
        job.status = JobStatus.ANALYZING
        broadcast_log("Analyzing for viral moments with Gemini AI...")
        
        viral_moments = await detector.detect_viral_moments(
            transcript,
            video_title=job.video_title,
            clip_count=job.clip_count,
            min_duration=job.min_duration,
            max_duration=job.max_duration,
            progress_callback=update_progress
        )
        broadcast_log(f"Found {len(viral_moments)} viral moments")
        
        # =================================================================
        # Step 4-5: Crop & Render Each Clip
        # =================================================================
        total_clips = len(viral_moments)
        
        for i, moment in enumerate(viral_moments):
            clip_progress_base = 50 + (i / total_clips) * 45  # 50-95%
            
            broadcast_log(f"Processing clip {i+1}/{total_clips}: {moment.title}")
            
            # Analyze scene for cropping strategy
            job.status = JobStatus.CROPPING
            scene = await cropper.analyze_scene(
                video_path,
                moment.start_time,
                moment.end_time
            )
            broadcast_log(f"Scene analysis: {scene.mode} mode - {scene.reason}")
            
            # Generate crop trajectory
            crop_frames = await cropper.generate_crop_trajectory(
                video_path,
                moment.start_time,
                moment.end_time,
                scene
            )
            
            # Render clip
            job.status = JobStatus.RENDERING
            output_filename = f"{job.id}_clip_{i+1:02d}.mp4"
            
            def render_progress(pct, msg):
                progress = clip_progress_base + (pct / 100) * (45 / total_clips)
                job.progress = progress
                broadcast_progress(job_id, progress, msg)
            
            clip_path = await renderer.render_clip(
                video_path,
                output_filename,
                moment.start_time,
                moment.end_time,
                crop_frames,
                progress_callback=render_progress
            )
            
            # Create clip record
            clip = Clip(
                job_id=job_id,
                title=moment.title,
                description=moment.description,
                start_time=moment.start_time,
                end_time=moment.end_time,
                viral_score=moment.viral_score,
                cropping_mode=scene.mode,
                file_path=clip_path
            )
            
            # Upload to S3 if enabled
            if job.upload_to_s3:
                job.status = JobStatus.UPLOADING
                s3_url = await uploader.upload_file(clip_path)
                if s3_url:
                    clip.s3_url = s3_url
                    broadcast_log(f"Uploaded to S3: {s3_url}")
            
            # Voice dubbing if enabled
            if job.enable_dubbing and job.dubbing_language:
                broadcast_log(f"Dubbing to {job.dubbing_language}...")
                audio_path = await renderer.extract_audio(clip_path)
                dubbed_path = await dubber.dub_audio(
                    audio_path,
                    job.dubbing_language
                )
                if dubbed_path:
                    clip.dubbed_audio_path = dubbed_path
                    broadcast_log(f"Dubbed audio saved: {dubbed_path}")
            
            clips_db[job_id].append(clip)
            job.clips.append(clip.id)
            
            broadcast_log(f"Clip {i+1} complete: {moment.title} (score: {moment.viral_score})")
            broadcast_progress(job_id, clip_progress_base + (45 / total_clips), f"Clip {i+1} complete")
        
        # =================================================================
        # Complete
        # =================================================================
        job.status = JobStatus.COMPLETED
        job.progress = 100
        job.completed_at = datetime.utcnow()
        
        broadcast_progress(job_id, 100, "Processing complete!")
        broadcast_log(f"Job {job_id} completed successfully with {len(clips_db[job_id])} clips")
        
    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        job.status = JobStatus.FAILED
        job.error_message = str(e)
        broadcast_log(f"[ERROR] Job failed: {e}")
        broadcast_progress(job_id, job.progress, f"Failed: {e}")
    
    finally:
        job.updated_at = datetime.utcnow()
