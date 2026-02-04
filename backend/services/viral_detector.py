"""
Viral Moment Detector
Uses Google Gemini 2.0 Flash to identify the most engaging moments in a video
"""

import asyncio
import json
import re
from typing import List, Optional, Callable
from dataclasses import dataclass

from ..utils.logger import get_logger
from ..config import get_settings
from .transcription import TranscriptionResult

logger = get_logger()


@dataclass
class ViralMoment:
    """Represents a detected viral moment"""
    start_time: float
    end_time: float
    viral_score: float  # 0-100
    hook_text: str
    title: str
    description: str
    hashtags: List[str]
    reason: str  # Why this moment is viral


class ViralDetector:
    """Detects viral moments in video content using Gemini AI"""
    
    def __init__(self):
        self.settings = get_settings()
        self._client = None
    
    def _ensure_client(self):
        """Lazy load the Gemini client"""
        if self._client is not None:
            return
            
        if not self.settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY not configured")
        
        try:
            from google import genai
            self._client = genai.Client(api_key=self.settings.gemini_api_key)
            logger.info("Gemini client initialized")
        except ImportError:
            logger.error("google-genai not installed")
            raise
    
    async def detect_viral_moments(
        self,
        transcript: TranscriptionResult,
        video_title: str = "",
        clip_count: int = 5,
        min_duration: int = 45,
        max_duration: int = 60,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> List[ViralMoment]:
        """
        Analyze transcript to find viral moments
        
        Args:
            transcript: The transcription result
            video_title: Original video title for context
            clip_count: Number of clips to find (3-15)
            min_duration: Minimum clip duration in seconds
            max_duration: Maximum clip duration in seconds
            progress_callback: Optional progress callback
            
        Returns:
            List of ViralMoment objects sorted by viral_score
        """
        logger.info(f"Detecting {clip_count} viral moments...")
        
        if progress_callback:
            progress_callback(0, "Analyzing transcript for viral moments...")
        
        self._ensure_client()
        
        # Prepare transcript with timestamps
        formatted_transcript = self._format_transcript(transcript)
        
        # Build the prompt
        prompt = self._build_analysis_prompt(
            formatted_transcript,
            video_title,
            clip_count,
            min_duration,
            max_duration,
            transcript.duration
        )
        
        if progress_callback:
            progress_callback(20, "Sending to Gemini AI for analysis...")
        
        # Call Gemini API
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt,
                config={
                    'response_mime_type': 'application/json',
                    'safety_settings': [
                        {'category': 'HARM_CATEGORY_HARASSMENT', 'threshold': 'BLOCK_NONE'},
                        {'category': 'HARM_CATEGORY_HATE_SPEECH', 'threshold': 'BLOCK_NONE'},
                        {'category': 'HARM_CATEGORY_SEXUALLY_EXPLICIT', 'threshold': 'BLOCK_NONE'},
                        {'category': 'HARM_CATEGORY_DANGEROUS_CONTENT', 'threshold': 'BLOCK_NONE'}
                    ]
                }
            )
        )
        
        if progress_callback:
            progress_callback(80, "Parsing AI response...")
        
        # Parse the response
        if not response or not hasattr(response, 'text') or not response.text:
            logger.error("Gemini returned empty response (possibly blocked)")
            return []
            
        moments = self._parse_response(response.text)
        
        # Sort by viral score
        moments.sort(key=lambda m: m.viral_score, reverse=True)
        
        if progress_callback:
            progress_callback(100, f"Found {len(moments)} viral moments")
        
        logger.info(f"Detected {len(moments)} viral moments")
        return moments
    
    def _format_transcript(self, transcript: TranscriptionResult) -> str:
        """Format transcript with timestamps for AI analysis"""
        lines = []
        for segment in transcript.segments:
            time_str = f"[{self._format_time(segment.start)} - {self._format_time(segment.end)}]"
            lines.append(f"{time_str} {segment.text}")
        return "\n".join(lines)
    
    def _format_time(self, seconds: float) -> str:
        """Format seconds to MM:SS"""
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"
    
    def _build_analysis_prompt(
        self,
        transcript: str,
        video_title: str,
        clip_count: int,
        min_duration: int,
        max_duration: int,
        total_duration: float
    ) -> str:
        """Build the prompt for Gemini analysis"""
        return f"""You are an expert viral content analyst specializing in short-form video content for Instagram Reels and YouTube Shorts.

Analyze this video transcript and identify the {clip_count} most viral-worthy moments that would perform best as standalone short clips.

VIDEO TITLE: {video_title}
TOTAL DURATION: {self._format_time(total_duration)}

TRANSCRIPT:
{transcript}

REQUIREMENTS:
- Each clip must be between {min_duration} and {max_duration} seconds
- Clips should start with a strong hook (question, surprising statement, controversy, emotion)
- Clips should be self-contained and make sense without context
- Avoid clips that end mid-sentence or mid-thought
- Prioritize moments with high emotional engagement, controversy, humor, or actionable insights

For each viral moment, provide:
1. Exact start and end timestamps (in seconds)
2. Viral score (0-100) based on hook strength, emotional impact, and shareability
3. The hook text (first sentence that grabs attention)
4. SEO-optimized title (max 60 chars, include power words)
5. SEO-optimized description (max 150 chars, include CTA)
6. 5 relevant hashtags
7. Brief explanation of why this moment is viral-worthy

RESPOND IN VALID JSON FORMAT ONLY:
{{
    "moments": [
        {{
            "start_time": 45.5,
            "end_time": 78.2,
            "viral_score": 92,
            "hook_text": "The first attention-grabbing sentence",
            "title": "Why Most People Get This Wrong",
            "description": "This changes everything about... Watch till the end! #viral",
            "hashtags": ["#viral", "#mindblown", "#tips", "#howto", "#trending"],
            "reason": "Strong controversial hook with actionable insight"
        }}
    ]
}}

Return exactly {clip_count} moments, ranked by viral potential."""
    
    def _parse_response(self, response_text: str) -> List[ViralMoment]:
        """Parse the Gemini response into ViralMoment objects"""
        try:
            # Extract JSON from response (handle markdown code blocks)
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if not json_match:
                logger.error("No JSON found in response")
                return []
            
            data = json.loads(json_match.group())
            moments = []
            
            for m in data.get('moments', []):
                moments.append(ViralMoment(
                    start_time=float(m.get('start_time', 0)),
                    end_time=float(m.get('end_time', 0)),
                    viral_score=float(m.get('viral_score', 50)),
                    hook_text=m.get('hook_text', ''),
                    title=m.get('title', 'Untitled Clip'),
                    description=m.get('description', ''),
                    hashtags=m.get('hashtags', []),
                    reason=m.get('reason', '')
                ))
            
            return moments
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response: {e}")
            return []
        except Exception as e:
            logger.error(f"Error parsing viral moments: {e}")
            return []
