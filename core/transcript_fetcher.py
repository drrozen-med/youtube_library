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
import logging
import time
import random

from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
    CouldNotRetrieveTranscript,
    VideoUnavailable,
    IpBlocked,
    RequestBlocked
)

logger = logging.getLogger(__name__)

# Rate limiting: delay between requests (seconds)
BASE_DELAY = 2.0  # Base delay between requests
MAX_DELAY = 60.0  # Maximum delay for exponential backoff
BACKOFF_MULTIPLIER = 2.0  # Multiply delay by this on each retry


def _delay_with_jitter(base_delay: float) -> None:
    """Add delay with random jitter to avoid thundering herd."""
    jitter = random.uniform(0.8, 1.2)  # ±20% jitter
    time.sleep(base_delay * jitter)


def check_ip_block_status(test_video_id: str = "jNQXAC9IVRw") -> Tuple[bool, Optional[str]]:
    """
    Check if the current IP is blocked by YouTube.
    
    Uses a well-known public video (me at the zoo) to test connectivity.
    
    Args:
        test_video_id: Video ID to use for testing (default: "me at the zoo" - a very old, stable video)
    
    Returns:
        Tuple of (is_blocked, error_message):
        - is_blocked: True if IP is blocked, False if accessible
        - error_message: Error message if blocked, None if accessible
    """
    try:
        api = YouTubeTranscriptApi()
        # Try to list transcripts for a well-known video
        transcript_list = api.list(test_video_id)
        
        # If we can list transcripts, try to fetch one (even if it doesn't exist)
        # This tests if we can make requests without being blocked
        try:
            # Try to get any available transcript
            for transcript in transcript_list:
                try:
                    parts = api.fetch(test_video_id, languages=[transcript.language_code])
                    # If we got here, IP is not blocked
                    return (False, None)
                except (IpBlocked, RequestBlocked) as e:
                    return (True, str(e))
                except (NoTranscriptFound, CouldNotRetrieveTranscript):
                    # Transcript not found is OK - we just want to test if IP is blocked
                    continue
            
            # If we can list but no transcripts available, that's fine - IP is not blocked
            return (False, None)
            
        except (IpBlocked, RequestBlocked) as e:
            return (True, str(e))
            
    except (IpBlocked, RequestBlocked) as e:
        return (True, str(e))
    except Exception as e:
        # Other errors (network, etc.) - assume not blocked but log
        logger.debug(f"Health check error (not necessarily a block): {type(e).__name__}: {e}")
        return (False, None)
    
    return (False, None)


def fetch_transcript_text(
    video_id: str,
    languages: tuple = ('en', 'en-US', 'en-GB'),
    max_retries: int = 3,
    initial_delay: float = 5.0
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Fetch transcript for a video with language fallbacks and rate limiting.
    
    Strategy:
    1. Try manual transcripts in preferred languages
    2. Fall back to auto-generated in preferred languages
    3. Fall back to any available transcript
    4. Retry with exponential backoff on IP blocks
    5. Return None if completely unavailable
    
    Args:
        video_id: YouTube video ID
        languages: Tuple of language codes to try (in order)
        max_retries: Maximum number of retries on IP block (default: 3)
        initial_delay: Initial delay in seconds before retry (default: 5.0)
    
    Returns:
        Tuple of (text, source, language):
        - text: Full transcript as plaintext (or None)
        - source: "manual" | "auto-generated" | None
        - language: Language code used (or None)
    """
    delay = initial_delay
    
    for attempt in range(max_retries + 1):
        if attempt > 0:
            # Exponential backoff with jitter
            logger.warning(f"Retry attempt {attempt}/{max_retries} for {video_id} after {delay:.1f}s delay...")
            _delay_with_jitter(delay)
            delay = min(delay * BACKOFF_MULTIPLIER, MAX_DELAY)
        
        try:
            # Add base delay between requests to avoid rate limiting
            if attempt == 0:
                _delay_with_jitter(BASE_DELAY)
            
            return _fetch_transcript_internal(video_id, languages)
            
        except (IpBlocked, RequestBlocked) as e:
            if attempt < max_retries:
                logger.warning(f"IP blocked on attempt {attempt + 1}/{max_retries + 1} for {video_id}. Retrying in {delay:.1f}s...")
                continue
            else:
                # Final attempt failed - log and return None
                logger.error(f"⚠️  IP BLOCKED by YouTube for video {video_id} after {max_retries + 1} attempts: {e}")
                return (None, None, None)
    
    return (None, None, None)


def _fetch_transcript_internal(
    video_id: str,
    languages: tuple = ('en', 'en-US', 'en-GB')
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Internal function to fetch transcript (without retry logic).
    Called by fetch_transcript_text which handles retries.
    """
    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
        
        # 1) Try manual transcripts first
        for code in languages:
            try:
                transcript = transcript_list.find_manually_created_transcript([code])
                parts = api.fetch(video_id, languages=[code])
                text = "\n".join([p.text for p in parts if hasattr(p, 'text')])
                return (text, "manual", transcript.language_code)
            except (NoTranscriptFound, CouldNotRetrieveTranscript) as e:
                logger.debug(f"Manual transcript not found for {video_id} in {code}: {type(e).__name__}: {e}")
                continue
            except (IpBlocked, RequestBlocked) as e:
                # Re-raise to be handled by retry logic
                raise
        
        # 2) Fall back to auto-generated
        for code in languages:
            try:
                transcript = transcript_list.find_generated_transcript([code])
                parts = api.fetch(video_id, languages=[code])
                text = "\n".join([p.text for p in parts if hasattr(p, 'text')])
                return (text, "auto-generated", transcript.language_code)
            except (NoTranscriptFound, CouldNotRetrieveTranscript) as e:
                logger.debug(f"Auto-generated transcript not found for {video_id} in {code}: {type(e).__name__}: {e}")
                continue
            except (IpBlocked, RequestBlocked) as e:
                # Re-raise to be handled by retry logic
                raise
        
        # 3) Last resort: grab any available transcript
        for transcript in transcript_list:
            try:
                parts = api.fetch(video_id, languages=[transcript.language_code])
                text = "\n".join([p.text for p in parts if hasattr(p, 'text')])
                source = "manual" if not transcript.is_generated else "auto-generated"
                return (text, source, transcript.language_code)
            except (IpBlocked, RequestBlocked) as e:
                # Re-raise to be handled by retry logic
                raise
            except Exception as e:
                logger.debug(f"Failed to fetch transcript {transcript.language_code} for {video_id}: {type(e).__name__}: {e}")
                continue
        
    except TranscriptsDisabled as e:
        logger.warning(f"Transcripts disabled for video {video_id}: {e}")
        return (None, None, None)
    except NoTranscriptFound as e:
        logger.warning(f"No transcript found for video {video_id}: {e}")
        return (None, None, None)
    except CouldNotRetrieveTranscript as e:
        logger.warning(f"Could not retrieve transcript for video {video_id}: {e}")
        return (None, None, None)
    except VideoUnavailable as e:
        logger.warning(f"Video unavailable: {video_id}: {e}")
        return (None, None, None)
    except (IpBlocked, RequestBlocked) as e:
        # Re-raise to be handled by retry logic in fetch_transcript_text
        raise
    except Exception as e:
        # Network or other rare errors - log the full error
        logger.error(f"Unexpected error fetching transcript for {video_id}: {type(e).__name__}: {e}", exc_info=True)
        return (None, None, None)
    
    return (None, None, None)
