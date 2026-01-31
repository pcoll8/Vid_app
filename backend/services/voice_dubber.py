"""
Voice Dubbing Service
ElevenLabs integration for AI voice dubbing and translation
"""

import asyncio
import os
from typing import Optional, Callable, List
from pathlib import Path

from ..utils.logger import get_logger
from ..config import get_settings

logger = get_logger()

# Supported languages for dubbing
SUPPORTED_LANGUAGES = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "pl": "Polish",
    "tr": "Turkish",
    "ru": "Russian",
    "nl": "Dutch",
    "cs": "Czech",
    "ar": "Arabic",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "hi": "Hindi",
    "id": "Indonesian",
    "fil": "Filipino",
    "vi": "Vietnamese",
    "th": "Thai",
    "sv": "Swedish",
    "da": "Danish",
    "fi": "Finnish",
    "no": "Norwegian",
    "hu": "Hungarian",
    "el": "Greek",
    "he": "Hebrew",
    "ro": "Romanian",
    "uk": "Ukrainian",
    "bg": "Bulgarian"
}


class VoiceDubber:
    """AI Voice dubbing using ElevenLabs"""
    
    def __init__(self):
        self.settings = get_settings()
        self._client = None
        self._initialized = False
    
    def _ensure_initialized(self):
        """Lazy initialize ElevenLabs client"""
        if self._initialized:
            return
        
        if not self.settings.elevenlabs_api_key:
            logger.warning("ElevenLabs API key not configured, dubbing disabled")
            return
        
        try:
            from elevenlabs import ElevenLabs
            
            self._client = ElevenLabs(api_key=self.settings.elevenlabs_api_key)
            self._initialized = True
            logger.info("ElevenLabs client initialized")
            
        except ImportError:
            logger.error("elevenlabs package not installed")
            raise
    
    @staticmethod
    def get_supported_languages() -> dict:
        """Get list of supported languages"""
        return SUPPORTED_LANGUAGES.copy()
    
    async def dub_audio(
        self,
        audio_path: str,
        target_language: str,
        source_language: Optional[str] = None,
        voice_id: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Optional[str]:
        """
        Dub audio to a target language
        
        Args:
            audio_path: Path to source audio file
            target_language: Target language code (e.g., 'es' for Spanish)
            source_language: Optional source language code (auto-detected if not provided)
            voice_id: Optional ElevenLabs voice ID (uses default if not provided)
            progress_callback: Optional progress callback
            
        Returns:
            Path to dubbed audio file or None if failed
        """
        self._ensure_initialized()
        
        if not self._client:
            logger.info("Dubbing skipped (ElevenLabs not configured)")
            return None
        
        if target_language not in SUPPORTED_LANGUAGES:
            logger.error(f"Unsupported language: {target_language}")
            return None
        
        if not os.path.exists(audio_path):
            logger.error(f"Audio file not found: {audio_path}")
            return None
        
        logger.info(f"Dubbing audio to {SUPPORTED_LANGUAGES[target_language]}")
        
        if progress_callback:
            progress_callback(0, f"Starting dubbing to {SUPPORTED_LANGUAGES[target_language]}...")
        
        # Output path
        output_path = audio_path.rsplit('.', 1)[0] + f'_dubbed_{target_language}.mp3'
        
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None,
                self._do_dubbing,
                audio_path,
                output_path,
                target_language,
                source_language,
                voice_id,
                progress_callback
            )
            
            if result and progress_callback:
                progress_callback(100, "Dubbing complete")
            
            return result
            
        except Exception as e:
            logger.error(f"Dubbing failed: {e}")
            if progress_callback:
                progress_callback(0, f"Dubbing failed: {str(e)}")
            return None
    
    def _do_dubbing(
        self,
        audio_path: str,
        output_path: str,
        target_language: str,
        source_language: Optional[str],
        voice_id: Optional[str],
        progress_callback: Optional[Callable[[float, str], None]]
    ) -> Optional[str]:
        """Perform dubbing (blocking)"""
        
        if progress_callback:
            progress_callback(10, "Uploading audio to ElevenLabs...")
        
        # Create dubbing project
        with open(audio_path, 'rb') as audio_file:
            dubbing = self._client.dubbing.dub_a_video_or_an_audio_file(
                file=(os.path.basename(audio_path), audio_file),
                target_lang=target_language,
                source_lang=source_language,
                watermark=False
            )
        
        dubbing_id = dubbing.dubbing_id
        
        if progress_callback:
            progress_callback(30, "Processing dubbing...")
        
        # Poll for completion
        import time
        max_attempts = 60  # 5 minutes max
        attempt = 0
        
        while attempt < max_attempts:
            status = self._client.dubbing.get_dubbing_project_metadata(dubbing_id)
            
            if status.status == "dubbed":
                break
            elif status.status == "failed":
                logger.error(f"Dubbing failed: {status.error}")
                return None
            
            if progress_callback:
                progress = 30 + (attempt / max_attempts) * 50
                progress_callback(progress, f"Processing: {status.status}")
            
            time.sleep(5)
            attempt += 1
        
        if attempt >= max_attempts:
            logger.error("Dubbing timed out")
            return None
        
        if progress_callback:
            progress_callback(85, "Downloading dubbed audio...")
        
        # Download dubbed audio
        dubbed_audio = self._client.dubbing.get_dubbed_file(dubbing_id, target_language)
        
        with open(output_path, 'wb') as f:
            for chunk in dubbed_audio:
                f.write(chunk)
        
        logger.info(f"Dubbed audio saved: {output_path}")
        return output_path
    
    async def clone_voice(
        self,
        audio_samples: List[str],
        voice_name: str,
        description: Optional[str] = None
    ) -> Optional[str]:
        """
        Create a cloned voice from audio samples
        
        Args:
            audio_samples: List of paths to audio samples (10-60s each recommended)
            voice_name: Name for the cloned voice
            description: Optional voice description
            
        Returns:
            Voice ID or None if failed
        """
        self._ensure_initialized()
        
        if not self._client:
            return None
        
        logger.info(f"Creating voice clone: {voice_name}")
        
        loop = asyncio.get_event_loop()
        try:
            # Prepare files
            files = []
            for path in audio_samples:
                if os.path.exists(path):
                    files.append(open(path, 'rb'))
            
            if not files:
                logger.error("No valid audio samples provided")
                return None
            
            voice = await loop.run_in_executor(
                None,
                lambda: self._client.clone(
                    name=voice_name,
                    description=description or f"Cloned voice: {voice_name}",
                    files=files
                )
            )
            
            # Close files
            for f in files:
                f.close()
            
            logger.info(f"Voice cloned successfully: {voice.voice_id}")
            return voice.voice_id
            
        except Exception as e:
            logger.error(f"Voice cloning failed: {e}")
            return None
    
    async def generate_subtitles(
        self,
        audio_path: str,
        language: str
    ) -> Optional[str]:
        """
        Generate subtitles for dubbed audio
        
        Args:
            audio_path: Path to audio file
            language: Language code
            
        Returns:
            Path to SRT subtitle file or None
        """
        # This would typically use a separate transcription service
        # For now, we'll rely on the main transcription service
        from .transcription import TranscriptionService
        
        logger.info(f"Generating subtitles for dubbed audio: {language}")
        
        transcription = TranscriptionService()
        result = await transcription.transcribe(audio_path)
        
        # Generate SRT
        srt_path = audio_path.rsplit('.', 1)[0] + '.srt'
        
        with open(srt_path, 'w', encoding='utf-8') as f:
            for i, segment in enumerate(result.segments, 1):
                start = self._format_srt_time(segment.start)
                end = self._format_srt_time(segment.end)
                f.write(f"{i}\n")
                f.write(f"{start} --> {end}\n")
                f.write(f"{segment.text}\n\n")
        
        logger.info(f"Subtitles generated: {srt_path}")
        return srt_path
    
    @staticmethod
    def _format_srt_time(seconds: float) -> str:
        """Format seconds to SRT timestamp"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
