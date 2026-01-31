"""
Video Renderer Service
FFmpeg-based video processing for clip extraction and 9:16 rendering
"""

import asyncio
import subprocess
import os
import json
from typing import List, Optional, Callable
from pathlib import Path
from dataclasses import dataclass

from ..utils.logger import get_logger
from .ai_cropping import CropFrame, CroppingMode

logger = get_logger()


@dataclass
class RenderConfig:
    """Configuration for video rendering"""
    output_width: int = 1080
    output_height: int = 1920
    fps: int = 30
    video_bitrate: str = "4M"
    audio_bitrate: str = "128k"
    codec: str = "libx264"
    preset: str = "fast"  # Faster encoding with minimal quality loss
    crf: int = 22  # Slightly lower CRF for better quality
    threads: int = 0  # Auto-detect optimal threads


class VideoRenderer:
    """FFmpeg-based video rendering for 9:16 vertical clips"""
    
    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.config = RenderConfig()
        self._has_nvenc = False
        self._check_ffmpeg()
        self._detect_hardware_acceleration()
    
    def _detect_hardware_acceleration(self):
        """Detect available hardware encoders"""
        try:
            result = subprocess.run(
                ["ffmpeg", "-encoders"],
                capture_output=True,
                text=True
            )
            if "h264_nvenc" in result.stdout:
                self._has_nvenc = True
                logger.info("NVIDIA NVENC encoder detected")
        except Exception:
            pass
    
    def _check_ffmpeg(self):
        """Verify FFmpeg is available"""
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                raise RuntimeError("FFmpeg not found")
            logger.info("FFmpeg available")
        except FileNotFoundError:
            logger.error("FFmpeg not installed. Please install FFmpeg.")
            raise RuntimeError("FFmpeg is required but not installed")
    
    async def render_clip(
        self,
        input_path: str,
        output_filename: str,
        start_time: float,
        end_time: float,
        crop_frames: Optional[List[CropFrame]] = None,
        subtitles_path: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> str:
        """
        Render a clip from source video
        
        Args:
            input_path: Source video path
            output_filename: Output filename (without path)
            start_time: Start time in seconds
            end_time: End time in seconds
            crop_frames: Optional list of crop coordinates per frame
            subtitles_path: Optional ASS/SRT subtitles file
            progress_callback: Optional progress callback
            
        Returns:
            Path to rendered clip
        """
        output_path = str(self.output_dir / output_filename)
        duration = end_time - start_time
        
        logger.info(f"Rendering clip: {output_filename} ({duration:.1f}s)")
        
        if progress_callback:
            progress_callback(0, "Starting render...")
        
        # Determine rendering approach
        if crop_frames and crop_frames[0].mode == CroppingMode.TRACK:
            cmd = await self._build_track_mode_command(
                input_path, output_path, start_time, end_time, 
                crop_frames, subtitles_path
            )
        else:
            cmd = self._build_general_mode_command(
                input_path, output_path, start_time, end_time,
                subtitles_path
            )
        
        # Execute FFmpeg
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            self._run_ffmpeg,
            cmd,
            duration,
            progress_callback
        )
        
        if progress_callback:
            progress_callback(100, "Render complete")
        
        # Generate thumbnail
        await self._generate_thumbnail(output_path)
        
        logger.info(f"Clip rendered: {output_path}")
        return output_path
    
    async def _build_track_mode_command(
        self,
        input_path: str,
        output_path: str,
        start_time: float,
        end_time: float,
        crop_frames: List[CropFrame],
        subtitles_path: Optional[str]
    ) -> List[str]:
        """Build FFmpeg command for TRACK mode with dynamic cropping"""
        
        # For simplicity, use average crop position (stabilizer already smoothed)
        if crop_frames:
            avg_x = sum(cf.center_x for cf in crop_frames) // len(crop_frames)
            avg_y = sum(cf.center_y for cf in crop_frames) // len(crop_frames)
            crop_w = crop_frames[0].crop_width
            crop_h = crop_frames[0].crop_height
        else:
            avg_x, avg_y = 960, 540  # Default 1080p center
            crop_w, crop_h = 607, 1080  # 9:16 from 1080p
        
        # Calculate crop offset
        crop_x = max(0, avg_x - crop_w // 2)
        crop_y = max(0, avg_y - crop_h // 2)
        
        filter_chain = [
            f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y}",
            f"scale={self.config.output_width}:{self.config.output_height}:flags=lanczos"
        ]
        
        if subtitles_path and os.path.exists(subtitles_path):
            # Escape path for FFmpeg filter
            sub_path = subtitles_path.replace('\\', '/').replace(':', '\\:')
            filter_chain.append(f"subtitles='{sub_path}'")
        
        filter_str = ",".join(filter_chain)
        
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_time),
            "-i", input_path,
            "-t", str(end_time - start_time),
            "-vf", filter_str,
            "-c:v", self.config.codec,
            "-preset", self.config.preset,
            "-crf", str(self.config.crf),
            "-c:a", "aac",
            "-b:a", self.config.audio_bitrate,
            "-movflags", "+faststart",
            output_path
        ]
        
        return cmd
    
    def _build_general_mode_command(
        self,
        input_path: str,
        output_path: str,
        start_time: float,
        end_time: float,
        subtitles_path: Optional[str]
    ) -> List[str]:
        """Build FFmpeg command for GENERAL mode with blurred background"""
        
        # Complex filter for blur background layout
        # 1. Create blurred, scaled background
        # 2. Overlay scaled original video in center
        filter_complex = f"""
        [0:v]split=2[bg][fg];
        [bg]scale={self.config.output_width}:{self.config.output_height}:force_original_aspect_ratio=increase,
            crop={self.config.output_width}:{self.config.output_height},
            boxblur=20:5[blurred];
        [fg]scale={self.config.output_width}:-2:force_original_aspect_ratio=decrease[scaled];
        [blurred][scaled]overlay=(W-w)/2:(H-h)/2[out]
        """.replace('\n', '').replace(' ', '')
        
        # Add subtitles if provided
        if subtitles_path and os.path.exists(subtitles_path):
            sub_path = subtitles_path.replace('\\', '/').replace(':', '\\:')
            filter_complex = filter_complex.replace('[out]', f"[presub];[presub]subtitles='{sub_path}'[out]")
        
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_time),
            "-i", input_path,
            "-t", str(end_time - start_time),
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-map", "0:a",
            "-c:v", self.config.codec,
            "-preset", self.config.preset,
            "-crf", str(self.config.crf),
            "-c:a", "aac",
            "-b:a", self.config.audio_bitrate,
            "-movflags", "+faststart",
            output_path
        ]
        
        return cmd
    
    def _run_ffmpeg(
        self,
        cmd: List[str],
        duration: float,
        progress_callback: Optional[Callable[[float, str], None]]
    ):
        """Execute FFmpeg command with progress tracking"""
        logger.debug(f"FFmpeg command: {' '.join(cmd)}")
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        # Read stderr for progress (FFmpeg outputs progress there)
        stderr_output = []
        for line in process.stderr:
            stderr_output.append(line)
            
            # Parse progress from FFmpeg output
            if "time=" in line and progress_callback:
                try:
                    time_str = line.split("time=")[1].split()[0]
                    parts = time_str.split(":")
                    current_time = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                    progress = min(95, (current_time / duration) * 100)
                    progress_callback(progress, f"Encoding: {progress:.0f}%")
                except:
                    pass
        
        process.wait()
        
        if process.returncode != 0:
            error_msg = "".join(stderr_output[-10:])
            logger.error(f"FFmpeg failed: {error_msg}")
            raise RuntimeError(f"FFmpeg encoding failed: {error_msg}")
    
    async def _generate_thumbnail(self, video_path: str) -> str:
        """Generate a thumbnail from the video"""
        thumb_path = video_path.rsplit('.', 1)[0] + '_thumb.jpg'
        
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-ss", "1",  # 1 second in
            "-vframes", "1",
            "-vf", "scale=540:960",
            "-q:v", "2",
            thumb_path
        ]
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: subprocess.run(cmd, capture_output=True)
        )
        
        return thumb_path
    
    async def extract_audio(self, video_path: str) -> str:
        """Extract audio from video for processing"""
        audio_path = video_path.rsplit('.', 1)[0] + '.wav'
        
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            audio_path
        ]
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: subprocess.run(cmd, capture_output=True, check=True)
        )
        
        return audio_path
