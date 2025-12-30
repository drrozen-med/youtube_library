"""
Transcript Fetcher
==================

Download YouTube video transcripts with language fallbacks.

Features:
- Prefers manually created transcripts over auto-generated
- Multi-language fallback (en, en-US, en-GB, etc.)
- Graceful handling when transcripts are unavailable
- Returns clean plaintext + metadata (source, language)
"""

from typing import Optional, Tuple

from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
    CouldNotRetrieveTranscript
)


def fetch_transcript_text(
    video_id: str,
    languages: tuple = ('en', 'en-US', 'en-GB')
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Fetch transcript for a video with language fallbacks.
    
    Strategy:
    1. Try manual transcripts in preferred languages
    2. Fall back to auto-generated in preferred languages
    3. Fall back to any available transcript
    4. Return None if completely unavailable
    
    Args:
        video_id: YouTube video ID
        languages: Tuple of language codes to try (in order)
    
    Returns:
        Tuple of (text, source, language):
        - text: Full transcript as plaintext (or None)
        - source: "manual" | "auto-generated" | None
        - language: Language code used (or None)
    """
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # 1) Try manual transcripts first
        for code in languages:
            try:
                transcript = transcript_list.find_manually_created_transcript([code])
                parts = transcript.fetch()
                text = "\n".join([p['text'] for p in parts if p.get('text')])
                return (text, "manual", transcript.language_code)
            except (NoTranscriptFound, CouldNotRetrieveTranscript):
                continue
        
        # 2) Fall back to auto-generated
        for code in languages:
            try:
                transcript = transcript_list.find_generated_transcript([code])
                parts = transcript.fetch()
                text = "\n".join([p['text'] for p in parts if p.get('text')])
                return (text, "auto-generated", transcript.language_code)
            except (NoTranscriptFound, CouldNotRetrieveTranscript):
                continue
        
        # 3) Last resort: grab any available transcript
        for transcript in transcript_list:
            try:
                parts = transcript.fetch()
                text = "\n".join([p['text'] for p in parts if p.get('text')])
                source = "manual" if not transcript.is_generated else "auto-generated"
                return (text, source, transcript.language_code)
            except Exception:
                continue
        
    except (TranscriptsDisabled, NoTranscriptFound, CouldNotRetrieveTranscript):
        # Transcripts completely unavailable
        return (None, None, None)
    except Exception:
        # Network or other rare errors - don't crash the run
        return (None, None, None)
    
    return (None, None, None)
