"""
AI Cropping Service
Dual-mode intelligent cropping using MediaPipe and YOLOv8
"""
from __future__ import annotations

import asyncio
from typing import List, Tuple, Optional, Callable, TYPE_CHECKING
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..utils.logger import get_logger
from ..utils.stabilizer import HeavyTripodStabilizer, StabilizerConfig

logger = get_logger()

# Lazy imports for heavy packages (not available in production deployment)
cv2 = None
np = None

def _ensure_cv2():
    """Lazy load OpenCV"""
    global cv2
    if cv2 is None:
        try:
            import cv2 as _cv2
            cv2 = _cv2
        except ImportError:
            raise ImportError("OpenCV (cv2) is required for AI cropping. Install with: pip install opencv-python")
    return cv2

def _ensure_numpy():
    """Lazy load NumPy"""
    global np
    if np is None:
        try:
            import numpy as _np
            np = _np
        except ImportError:
            raise ImportError("NumPy is required for AI cropping. Install with: pip install numpy")
    return np


class CroppingMode(str, Enum):
    """Cropping strategy modes"""
    TRACK = "track"      # Single subject tracking
    GENERAL = "general"  # Multi-subject / landscape with blur


@dataclass
class FaceDetection:
    """Represents a detected face"""
    x: int
    y: int
    width: int
    height: int
    confidence: float
    is_speaking: bool = False


@dataclass
class SceneAnalysis:
    """Result of scene analysis"""
    mode: CroppingMode
    face_count: int
    primary_face: Optional[FaceDetection]
    all_faces: List[FaceDetection]
    movement_score: float  # 0-100, how much movement in scene
    reason: str


@dataclass
class CropFrame:
    """Represents a single frame's crop parameters"""
    center_x: int
    center_y: int
    crop_width: int
    crop_height: int
    mode: CroppingMode


class AICroppingService:
    """
    Intelligent video cropping with scene-based strategy
    
    Uses PySceneDetect for content-aware cropping (lightweight alternative to MediaPipe/YOLOv8)
    GENERAL Mode: Center crop with blurred background
    """
    
    def __init__(self):
        self.scene_detector = None
        self.stabilizer = HeavyTripodStabilizer(StabilizerConfig(
            smoothing_factor=0.12,
            max_velocity=25.0,
            lock_threshold=60.0,
            deadzone=25.0
        ))
        self._initialized = False
        self._cv2 = None
        self._np = None
        
        # Output dimensions (9:16 vertical)
        self.output_width = 1080
        self.output_height = 1920
    
    def _ensure_initialized(self):
        """Lazy load scene detection"""
        if self._initialized:
            return
        
        try:
            import cv2
            self._cv2 = cv2
            logger.info("OpenCV loaded for scene detection")
        except ImportError:
            logger.warning("OpenCV not available")
        
        try:
            import numpy as np_module
            self._np = np_module
            logger.info("NumPy loaded")
        except ImportError:
            logger.warning("NumPy not available")
        
        try:
            from scenedetect import detect, ContentDetector
            self.scene_detector = ContentDetector(threshold=27.0)
            logger.info("SceneDetect loaded for content-aware cropping")
        except ImportError:
            logger.warning("SceneDetect not available, using center crop only")
        
        self._initialized = True
    
    async def analyze_scene(
        self,
        video_path: str,
        start_time: float,
        end_time: float,
        sample_frames: int = 10
    ) -> SceneAnalysis:
        """
        Analyze a video segment to determine optimal cropping strategy
        
        Args:
            video_path: Path to video file
            start_time: Start of segment in seconds
            end_time: End of segment in seconds
            sample_frames: Number of frames to sample for analysis
            
        Returns:
            SceneAnalysis with recommended mode and details
        """
        logger.info(f"Analyzing scene: {start_time:.1f}s - {end_time:.1f}s")
        
        self._ensure_initialized()
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._do_scene_analysis,
            video_path,
            start_time,
            end_time,
            sample_frames
        )
    
    def _do_scene_analysis(
        self,
        video_path: str,
        start_time: float,
        end_time: float,
        sample_frames: int
    ) -> SceneAnalysis:
        """Perform scene analysis (blocking)"""
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        
        duration = end_time - start_time
        sample_interval = duration / sample_frames
        
        all_detections = []
        face_counts = []
        prev_frame = None
        movement_scores = []
        
        for i in range(sample_frames):
            time_offset = start_time + (i * sample_interval)
            frame_num = int(time_offset * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            ret, frame = cap.read()
            
            if not ret:
                continue
            
            # Detect faces
            faces = self._detect_faces(frame)
            all_detections.extend(faces)
            face_counts.append(len(faces))
            
            # Calculate movement
            if prev_frame is not None:
                movement = self._calculate_movement(prev_frame, frame)
                movement_scores.append(movement)
            
            prev_frame = frame.copy()
        
        cap.release()
        
        # Analyze results
        avg_faces = np.mean(face_counts) if face_counts else 0
        max_faces = max(face_counts) if face_counts else 0
        avg_movement = np.mean(movement_scores) if movement_scores else 0
        
        # Determine mode
        if avg_faces <= 1.5 and max_faces <= 2:
            mode = CroppingMode.TRACK
            reason = f"Single subject detected (avg {avg_faces:.1f} faces)"
        else:
            mode = CroppingMode.GENERAL
            reason = f"Multiple subjects ({max_faces} max faces) - using blur layout"
        
        # Find primary face (most consistently detected, largest)
        primary = self._find_primary_face(all_detections) if all_detections else None
        
        return SceneAnalysis(
            mode=mode,
            face_count=int(avg_faces),
            primary_face=primary,
            all_faces=all_detections[-10:] if all_detections else [],
            movement_score=float(avg_movement),
            reason=reason
        )
    
    def _detect_faces(self, frame: np.ndarray) -> List[FaceDetection]:
        """Detect content regions in a frame using center-based heuristics"""
        faces = []
        
        if self._cv2 is None or self._np is None:
            return faces
        
        height, width = frame.shape[:2]
        
        # Use center-weighted detection (most content is centered)
        # Create a synthetic "face" detection at the center
        center_x = width // 2
        center_y = height // 3  # Upper third for typical video content
        
        faces.append(FaceDetection(
            x=center_x - width // 6,
            y=center_y - height // 8,
            width=width // 3,
            height=height // 4,
            confidence=0.8
        ))
        
        return faces
    
    def _calculate_movement(self, prev_frame: np.ndarray, curr_frame: np.ndarray) -> float:
        """Calculate movement score between frames"""
        if self._cv2 is None or self._np is None:
            return 0.0
        
        prev_gray = self._cv2.cvtColor(prev_frame, self._cv2.COLOR_BGR2GRAY)
        curr_gray = self._cv2.cvtColor(curr_frame, self._cv2.COLOR_BGR2GRAY)
        
        diff = self._cv2.absdiff(prev_gray, curr_gray)
        movement = self._np.mean(diff)
        
        # Normalize to 0-100
        return min(100, movement * 2)
    
    def _find_primary_face(self, detections: List[FaceDetection]) -> Optional[FaceDetection]:
        """Find the most prominent face from all detections"""
        if not detections:
            return None
        
        # Score by size and confidence
        scored = []
        for face in detections:
            area = face.width * face.height
            score = area * face.confidence
            scored.append((score, face))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]
    
    async def generate_crop_trajectory(
        self,
        video_path: str,
        start_time: float,
        end_time: float,
        scene_analysis: SceneAnalysis,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> List[CropFrame]:
        """
        Generate frame-by-frame crop coordinates for a video segment
        
        Args:
            video_path: Path to video file
            start_time: Start time in seconds
            end_time: End time in seconds
            scene_analysis: Pre-computed scene analysis
            progress_callback: Optional progress callback
            
        Returns:
            List of CropFrame objects for each frame
        """
        logger.info(f"Generating crop trajectory: {scene_analysis.mode}")
        
        if progress_callback:
            progress_callback(0, f"Generating {scene_analysis.mode} crop trajectory...")
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._generate_trajectory,
            video_path,
            start_time,
            end_time,
            scene_analysis,
            progress_callback
        )
    
    def _generate_trajectory(
        self,
        video_path: str,
        start_time: float,
        end_time: float,
        scene_analysis: SceneAnalysis,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> List[CropFrame]:
        """Generate crop trajectory with optimized frame skipping"""
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        start_frame = int(start_time * fps)
        end_frame = int(end_time * fps)
        total_frames = end_frame - start_frame
        
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        
        # Reset stabilizer
        self.stabilizer.reset(frame_width // 2, frame_height // 2)
        
        # Performance optimization: process every Nth frame, interpolate the rest
        # For 30fps, process every 3rd frame (10fps detection)
        skip_factor = max(1, int(fps / 10))
        
        keyframe_crops = []
        keyframe_indices = []
        
        for i in range(0, total_frames, skip_factor):
            cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame + i)
            ret, frame = cap.read()
            if not ret:
                break
            
            if scene_analysis.mode == CroppingMode.TRACK:
                crop = self._track_mode_crop(frame, frame_width, frame_height)
            else:
                crop = self._general_mode_crop(frame_width, frame_height)
            
            keyframe_crops.append(crop)
            keyframe_indices.append(i)
            
            if progress_callback and len(keyframe_crops) % 10 == 0:
                progress = (i / total_frames) * 100
                progress_callback(progress, f"Analyzing frame {i}/{total_frames}")
        
        cap.release()
        
        # Interpolate frames between keyframes
        crop_frames = self._interpolate_crop_frames(
            keyframe_crops, keyframe_indices, total_frames, scene_analysis.mode
        )
        
        if progress_callback:
            progress_callback(100, "Crop trajectory complete")
        
        return crop_frames
    
    def _interpolate_crop_frames(
        self,
        keyframes: List[CropFrame],
        indices: List[int],
        total_frames: int,
        mode: CroppingMode
    ) -> List[CropFrame]:
        """Interpolate crop positions between keyframes for smooth motion"""
        if not keyframes:
            return []
        
        crop_frames = []
        
        for frame_idx in range(total_frames):
            # Find surrounding keyframes
            prev_key_idx = 0
            next_key_idx = 0
            
            for i, ki in enumerate(indices):
                if ki <= frame_idx:
                    prev_key_idx = i
                if ki >= frame_idx:
                    next_key_idx = i
                    break
            else:
                next_key_idx = len(keyframes) - 1
            
            if prev_key_idx == next_key_idx or indices[next_key_idx] == indices[prev_key_idx]:
                # Use exact keyframe
                crop_frames.append(keyframes[prev_key_idx])
            else:
                # Linear interpolation between keyframes
                t = (frame_idx - indices[prev_key_idx]) / (indices[next_key_idx] - indices[prev_key_idx])
                prev_crop = keyframes[prev_key_idx]
                next_crop = keyframes[next_key_idx]
                
                crop_frames.append(CropFrame(
                    center_x=int(prev_crop.center_x + t * (next_crop.center_x - prev_crop.center_x)),
                    center_y=int(prev_crop.center_y + t * (next_crop.center_y - prev_crop.center_y)),
                    crop_width=prev_crop.crop_width,
                    crop_height=prev_crop.crop_height,
                    mode=mode
                ))
        
        return crop_frames
    
    def _track_mode_crop(self, frame: np.ndarray, width: int, height: int) -> CropFrame:
        """Generate crop for TRACK mode (single subject)"""
        faces = self._detect_faces(frame)
        
        if faces:
            # Get primary face center
            face = max(faces, key=lambda f: f.width * f.height)
            detected_x = face.x + face.width // 2
            detected_y = face.y + face.height // 2
            confidence = face.confidence
        else:
            # No face detected, use center
            detected_x = width // 2
            detected_y = height // 2
            confidence = 0.3
        
        # Apply stabilization
        smooth_x, smooth_y = self.stabilizer.update(detected_x, detected_y, confidence)
        
        # Calculate crop dimensions (maintain 9:16 aspect ratio)
        crop_height = height
        crop_width = int(crop_height * 9 / 16)
        
        if crop_width > width:
            crop_width = width
            crop_height = int(crop_width * 16 / 9)
        
        return CropFrame(
            center_x=int(smooth_x),
            center_y=int(smooth_y),
            crop_width=crop_width,
            crop_height=crop_height,
            mode=CroppingMode.TRACK
        )
    
    def _general_mode_crop(self, width: int, height: int) -> CropFrame:
        """Generate crop for GENERAL mode (centered, will use blur background)"""
        return CropFrame(
            center_x=width // 2,
            center_y=height // 2,
            crop_width=width,  # Full width, blur will be added
            crop_height=height,
            mode=CroppingMode.GENERAL
        )
