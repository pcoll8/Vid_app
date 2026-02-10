"""
Jobs Router
Handles video processing job creation, persistence, and background queue execution.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from ..config import get_settings
from ..models.clip import Clip
from ..models.job import Job, JobStatus
from ..services.ai_cropping import AICroppingService
from ..services.job_queue import get_job_queue
from ..services.job_store import get_job_store
from ..services.s3_uploader import S3Uploader
from ..services.transcription import TranscriptionService
from ..services.video_renderer import VideoRenderer
from ..services.viral_detector import ViralDetector
from ..services.voice_dubber import VoiceDubber
from ..services.youtube_downloader import YouTubeDownloader
from ..utils.logger import get_logger
from .websocket import broadcast_log, broadcast_progress, broadcast_to_all

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
logger = get_logger()

# In-memory runtime cache backed by SQLite persistence
jobs_db: Dict[str, Job] = {}
clips_db: Dict[str, List[Clip]] = {}

job_store = get_job_store()
job_queue = get_job_queue()

_IN_PROGRESS_STATUSES = {
    JobStatus.DOWNLOADING,
    JobStatus.DOWNLOADING.value,
    JobStatus.TRANSCRIBING,
    JobStatus.TRANSCRIBING.value,
    JobStatus.ANALYZING,
    JobStatus.ANALYZING.value,
    JobStatus.CROPPING,
    JobStatus.CROPPING.value,
    JobStatus.RENDERING,
    JobStatus.RENDERING.value,
    JobStatus.UPLOADING,
    JobStatus.UPLOADING.value,
}


def _model_to_dict(model):
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()


def _safe_filename(filename: Optional[str]) -> str:
    if not filename:
        return "uploaded_video.mp4"
    return Path(filename).name.replace("..", "_").replace("\\", "_").replace("/", "_")


def _remove_file(path: Optional[str]):
    if not path:
        return
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception as exc:
        logger.warning(f"Failed to remove file {path}: {exc}")


def _cleanup_clip_files(clip: Clip):
    _remove_file(clip.file_path)
    _remove_file(clip.dubbed_audio_path)
    _remove_file(clip.subtitles_path)

    if clip.file_path:
        thumb_path = clip.file_path.rsplit(".", 1)[0] + "_thumb.jpg"
        _remove_file(thumb_path)


async def _persist_job(job: Job):
    job.updated_at = datetime.utcnow()
    await job_store.upsert_job(job)


async def _persist_clip(clip: Clip):
    await job_store.upsert_clip(clip)


async def initialize_job_state():
    """Load persisted jobs/clips into memory and recover interrupted jobs."""
    await job_store.initialize()

    persisted_jobs = await job_store.list_jobs()
    jobs_db.clear()
    jobs_db.update({job.id: job for job in persisted_jobs})

    persisted_clips = await job_store.list_clips()
    clips_db.clear()
    for clip in persisted_clips:
        clips_db.setdefault(clip.job_id, []).append(clip)

    recovered = 0
    for job in jobs_db.values():
        if job.status in _IN_PROGRESS_STATUSES:
            job.status = JobStatus.FAILED
            job.error_message = "Job interrupted by server restart"
            job.updated_at = datetime.utcnow()
            await job_store.upsert_job(job)
            recovered += 1

    logger.info(
        f"Recovered {len(jobs_db)} jobs and {len(persisted_clips)} clips from persistent storage"
    )
    if recovered:
        logger.warning(f"Marked {recovered} interrupted jobs as failed")


def configure_job_queue():
    """Configure queue processor from current settings."""
    settings = get_settings()
    job_queue.configure(
        processor=process_job,
        worker_count=settings.job_worker_concurrency,
        max_pending=settings.max_pending_jobs,
    )


@router.post("/", response_model=Job)
async def create_job(
    source_url: Optional[str] = Form(None),
    clip_count: int = Form(5),
    min_duration: int = Form(45),
    max_duration: int = Form(60),
    enable_dubbing: bool = Form(False),
    dubbing_language: Optional[str] = Form(None),
    upload_to_s3: bool = Form(True),
    file: Optional[UploadFile] = File(None),
):
    """Create a new video processing job."""
    if not source_url and not file:
        raise HTTPException(400, "Either source_url or file must be provided")
    if min_duration > max_duration:
        raise HTTPException(400, "min_duration cannot be greater than max_duration")

    if not job_queue.can_accept():
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Job queue is full. Try again in a few minutes.",
        )

    job = Job(
        source_url=source_url,
        clip_count=clip_count,
        min_duration=min_duration,
        max_duration=max_duration,
        enable_dubbing=enable_dubbing,
        dubbing_language=dubbing_language,
        upload_to_s3=upload_to_s3,
    )

    if file:
        if file.content_type and not file.content_type.startswith("video/"):
            raise HTTPException(400, "Uploaded file must be a video")

        settings = get_settings()
        temp_dir = Path(settings.temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)

        max_upload_bytes = settings.max_upload_size_mb * 1024 * 1024
        file_path = temp_dir / f"{job.id}_{_safe_filename(file.filename)}"
        bytes_written = 0
        chunk_size = 1024 * 1024

        try:
            with open(file_path, "wb") as output_file:
                while True:
                    chunk = await file.read(chunk_size)
                    if not chunk:
                        break
                    bytes_written += len(chunk)
                    if bytes_written > max_upload_bytes:
                        output_file.close()
                        _remove_file(str(file_path))
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"File exceeds max upload size ({settings.max_upload_size_mb}MB)",
                        )
                    output_file.write(chunk)
        finally:
            await file.close()

        job.source_file = str(file_path)

    jobs_db[job.id] = job
    clips_db[job.id] = []
    await _persist_job(job)

    try:
        enqueued = await job_queue.enqueue(job.id)
    except RuntimeError as exc:
        _remove_file(job.source_file)
        jobs_db.pop(job.id, None)
        clips_db.pop(job.id, None)
        await job_store.delete_job(job.id)
        raise HTTPException(503, f"Job queue unavailable: {exc}") from exc

    if not enqueued:
        _remove_file(job.source_file)
        jobs_db.pop(job.id, None)
        clips_db.pop(job.id, None)
        await job_store.delete_job(job.id)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Job queue is full. Try again later.",
        )

    broadcast_log(f"Job queued: {job.id}")
    logger.info(f"Job created and queued: {job.id}")
    return job


@router.get("/", response_model=List[Job])
async def list_jobs():
    """List all jobs."""
    return sorted(jobs_db.values(), key=lambda item: item.created_at, reverse=True)


@router.get("/{job_id}", response_model=Job)
async def get_job(job_id: str):
    """Get a specific job."""
    job = jobs_db.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.get("/{job_id}/clips", response_model=List[Clip])
async def get_job_clips(job_id: str):
    """Get clips for a job."""
    if job_id not in jobs_db:
        raise HTTPException(404, "Job not found")
    return clips_db.get(job_id, [])


async def delete_clip_record(clip_id: str) -> bool:
    """Delete clip from memory + persistent storage."""
    for job_id, clips in clips_db.items():
        for index, clip in enumerate(clips):
            if clip.id != clip_id:
                continue

            _cleanup_clip_files(clip)
            clips.pop(index)
            await job_store.delete_clip(clip_id)

            job = jobs_db.get(job_id)
            if job and clip_id in job.clips:
                job.clips.remove(clip_id)
                await _persist_job(job)
            return True
    return False


@router.delete("/{job_id}")
async def delete_job(job_id: str):
    """Delete a job and all generated artifacts."""
    job = jobs_db.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    for clip in list(clips_db.get(job_id, [])):
        _cleanup_clip_files(clip)

    _remove_file(job.source_file)

    jobs_db.pop(job_id, None)
    clips_db.pop(job_id, None)
    await job_store.delete_job(job_id)

    broadcast_log(f"Job deleted: {job_id}")
    return {"status": "deleted"}


async def process_job(job_id: str):
    """Main job processing pipeline."""
    job = jobs_db.get(job_id)
    if not job:
        return

    settings = get_settings()
    temporary_downloaded_file: Optional[str] = None
    video_path: Optional[str] = None

    try:
        downloader = YouTubeDownloader(settings.temp_dir)
        transcriber = TranscriptionService()
        detector = ViralDetector()
        cropper = AICroppingService()
        renderer = VideoRenderer(settings.output_dir)
        uploader = S3Uploader()
        dubber = VoiceDubber()

        # =================================================================
        # Step 1: Download / Prepare Video
        # =================================================================
        def download_progress(pct, msg):
            job.progress = pct * 0.15
            broadcast_progress(job_id, job.progress, msg)
            broadcast_log(f"[DOWNLOAD] {msg}")

        if job.source_url:
            job.status = JobStatus.DOWNLOADING
            await _persist_job(job)
            broadcast_log(f"Starting download: {job.source_url}")

            video_path, video_info = await downloader.download(
                job.source_url,
                progress_callback=download_progress,
            )
            temporary_downloaded_file = video_path
            job.video_title = video_info.get("title", "Untitled")
            job.video_duration = video_info.get("duration", 0)
            await _persist_job(job)
        else:
            video_path = job.source_file
            job.video_title = Path(video_path).stem if video_path else "Uploaded Video"
            await _persist_job(job)

        if not video_path:
            raise RuntimeError("Video source could not be prepared")

        # =================================================================
        # Step 2: Transcribe
        # =================================================================
        def transcribe_progress(pct, msg):
            job.progress = 15 + pct * 0.20
            broadcast_progress(job_id, job.progress, msg)
            broadcast_log(f"[TRANSCRIBE] {msg}")

        job.status = JobStatus.TRANSCRIBING
        await _persist_job(job)
        broadcast_log("Starting transcription...")

        transcript = await transcriber.transcribe(
            video_path,
            progress_callback=transcribe_progress,
        )
        broadcast_log(
            f"Transcribed {len(transcript.segments)} segments in {transcript.language}"
        )

        # =================================================================
        # Step 3: Detect Viral Moments
        # =================================================================
        def analysis_progress(pct, msg):
            job.progress = 35 + pct * 0.15
            broadcast_progress(job_id, job.progress, msg)
            broadcast_log(f"[ANALYZE] {msg}")

        job.status = JobStatus.ANALYZING
        await _persist_job(job)
        broadcast_log("Analyzing for viral moments with Gemini AI...")

        viral_moments = await detector.detect_viral_moments(
            transcript,
            video_title=job.video_title or "",
            clip_count=job.clip_count,
            min_duration=job.min_duration,
            max_duration=job.max_duration,
            progress_callback=analysis_progress,
        )

        if not viral_moments:
            raise RuntimeError("No viral moments found for this video")

        broadcast_log(f"Found {len(viral_moments)} viral moments")

        # =================================================================
        # Step 4-5: Crop & Render Each Clip
        # =================================================================
        total_clips = len(viral_moments)
        clips_db.setdefault(job_id, [])

        for index, moment in enumerate(viral_moments):
            clip_progress_base = 50 + (index / total_clips) * 45
            broadcast_log(
                f"Processing clip {index + 1}/{total_clips}: {moment.title}"
            )

            job.status = JobStatus.CROPPING
            await _persist_job(job)
            scene = await cropper.analyze_scene(
                video_path,
                moment.start_time,
                moment.end_time,
            )
            broadcast_log(f"Scene analysis: {scene.mode} mode - {scene.reason}")

            crop_frames = await cropper.generate_crop_trajectory(
                video_path,
                moment.start_time,
                moment.end_time,
                scene,
            )

            job.status = JobStatus.RENDERING
            await _persist_job(job)
            output_filename = f"{job.id}_clip_{index + 1:02d}.mp4"

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
                progress_callback=render_progress,
            )

            clip = Clip(
                job_id=job_id,
                title=moment.title,
                description=moment.description,
                start_time=moment.start_time,
                end_time=moment.end_time,
                viral_score=moment.viral_score,
                cropping_mode=scene.mode,
                file_path=clip_path,
            )

            if job.upload_to_s3:
                job.status = JobStatus.UPLOADING
                await _persist_job(job)
                s3_url = await uploader.upload_file(clip_path)
                if s3_url:
                    clip.s3_url = s3_url
                    broadcast_log(f"Uploaded to S3: {s3_url}")

            if job.enable_dubbing and job.dubbing_language:
                broadcast_log(f"Dubbing to {job.dubbing_language}...")
                audio_path = await renderer.extract_audio(clip_path)
                try:
                    dubbed_path = await dubber.dub_audio(
                        audio_path,
                        job.dubbing_language,
                    )
                    if dubbed_path:
                        clip.dubbed_audio_path = dubbed_path
                        broadcast_log(f"Dubbed audio saved: {dubbed_path}")
                finally:
                    _remove_file(audio_path)

            clips_db[job_id].append(clip)
            job.clips.append(clip.id)
            await _persist_clip(clip)
            await _persist_job(job)

            await broadcast_to_all({"type": "clip_ready", "data": _model_to_dict(clip)})
            broadcast_log(
                f"Clip {index + 1} complete: {moment.title} (score: {moment.viral_score})"
            )
            broadcast_progress(
                job_id,
                clip_progress_base + (45 / total_clips),
                f"Clip {index + 1} complete",
            )

        # =================================================================
        # Complete
        # =================================================================
        job.status = JobStatus.COMPLETED
        job.progress = 100
        job.completed_at = datetime.utcnow()
        await _persist_job(job)

        broadcast_progress(job_id, 100, "Processing complete!")
        broadcast_log(
            f"Job {job_id} completed successfully with {len(clips_db[job_id])} clips"
        )

    except Exception as exc:
        logger.exception(f"Job {job_id} failed: {exc}")
        job.status = JobStatus.FAILED
        job.error_message = str(exc)
        await _persist_job(job)
        broadcast_log(f"[ERROR] Job failed: {exc}")
        broadcast_progress(job_id, job.progress, f"Failed: {exc}")

    finally:
        job.updated_at = datetime.utcnow()
        await job_store.upsert_job(job)
        if temporary_downloaded_file:
            _remove_file(temporary_downloaded_file)
