"""
Transcription Service
High-speed transcription using Faster-Whisper with word-level timestamps
"""

import asyncio
from typing import List, Optional, Callable
from pathlib import Path
from dataclasses import dataclass

from ..utils.logger import get_logger
from ..config import get_settings

logger = get_logger()


@dataclass
class WordTimestamp:
    """Represents a word with its timing information"""
    word: str
    start: float
    end: float
    probability: float


@dataclass 
class TranscriptSegment:
    """Represents a transcript segment"""
    id: int
    start: float
    end: float
    text: str
    words: List[WordTimestamp]


@dataclass
class TranscriptionResult:
    """Complete transcription result"""
    language: str
    language_probability: float
    duration: float
    segments: List[TranscriptSegment]
    full_text: str


class TranscriptionService:
    """CPU-optimized transcription using Faster-Whisper"""
    
    def __init__(self, model_size: Optional[str] = None):
        settings = get_settings()
        self.model_size = model_size or settings.whisper_model
        self.model = None
        self._model_loaded = False
    
    def _ensure_model_loaded(self):
        """Lazy load the Whisper model with optimal settings"""
        if self._model_loaded:
            return
            
        logger.info(f"Loading Faster-Whisper model: {self.model_size}")
        
        try:
            import os
            from faster_whisper import WhisperModel
            
            # Auto-detect optimal CPU threads (use 75% of available cores)
            cpu_count = os.cpu_count() or 4
            optimal_threads = max(2, int(cpu_count * 0.75))
            
            # CPU-optimized configuration with int8 quantization
            self.model = WhisperModel(
                self.model_size,
                device="cpu",
                compute_type="int8",
                cpu_threads=optimal_threads,
                num_workers=2,  # Parallel data loading
            )
            self._model_loaded = True
            logger.info(f"Whisper model loaded (threads={optimal_threads})")
            
        except ImportError:
            logger.error("faster-whisper not installed. Run: pip install faster-whisper")
            raise
    
    async def transcribe(
        self,
        audio_path: str,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> TranscriptionResult:
        """
        Transcribe audio/video file
        
        Args:
            audio_path: Path to audio or video file
            progress_callback: Optional progress callback
            
        Returns:
            TranscriptionResult with segments and word timestamps
        """
        logger.info(f"Starting transcription: {audio_path}")
        
        if progress_callback:
            progress_callback(0, "Loading transcription model...")
        
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, 
            self._do_transcription, 
            audio_path,
            progress_callback
        )
        
        logger.info(f"Transcription complete: {len(result.segments)} segments")
        return result
    
    def _do_transcription(
        self, 
        audio_path: str,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> TranscriptionResult:
        """Perform the actual transcription (blocking)"""
        self._ensure_model_loaded()
        
        if progress_callback:
            progress_callback(10, "Transcribing audio...")
        
        # Transcribe with word timestamps
        segments_gen, info = self.model.transcribe(
            audio_path,
            word_timestamps=True,
            vad_filter=True,  # Filter out non-speech
            vad_parameters=dict(
                min_silence_duration_ms=500,
                speech_pad_ms=200
            )
        )
        
        segments = []
        full_text_parts = []
        
        # Process segments
        segment_list = list(segments_gen)
        total_segments = len(segment_list)
        
        for i, segment in enumerate(segment_list):
            # Extract word timestamps
            words = []
            if segment.words:
                for word in segment.words:
                    words.append(WordTimestamp(
                        word=word.word.strip(),
                        start=word.start,
                        end=word.end,
                        probability=word.probability
                    ))
            
            segments.append(TranscriptSegment(
                id=segment.id,
                start=segment.start,
                end=segment.end,
                text=segment.text.strip(),
                words=words
            ))
            
            full_text_parts.append(segment.text.strip())
            
            # Update progress
            if progress_callback and total_segments > 0:
                progress = 10 + (80 * (i + 1) / total_segments)
                progress_callback(progress, f"Transcribing: {i + 1}/{total_segments} segments")
        
        if progress_callback:
            progress_callback(100, "Transcription complete")
        
        return TranscriptionResult(
            language=info.language,
            language_probability=info.language_probability,
            duration=info.duration,
            segments=segments,
            full_text=" ".join(full_text_parts)
        )
    
    def get_text_at_time(self, result: TranscriptionResult, time: float) -> Optional[str]:
        """Get the text being spoken at a specific time"""
        for segment in result.segments:
            if segment.start <= time <= segment.end:
                return segment.text
        return None
    
    def get_segment_at_time(self, result: TranscriptionResult, time: float) -> Optional[TranscriptSegment]:
        """Get the segment at a specific time"""
        for segment in result.segments:
            if segment.start <= time <= segment.end:
                return segment
        return None
