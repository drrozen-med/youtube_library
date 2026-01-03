"""
Proxy-Enabled Transcript Fetcher
=================================

YouTube transcript fetching using proxy services to bypass IP blocks.

Replaces youtube-transcript-api with proxy-enabled scraping using:
- ScrapingBee (primary)
- ScrapeNinja (fallback)
- Firecrawl (last resort)

Features:
- Proxy-enabled scraping to bypass YouTube IP blocks
- Automatic fallback chain
- HTML parsing for transcript data
- Rate limiting and cost tracking
- Compatible with existing transcript_fetcher.py interface
"""

import os
import asyncio
import logging
import json
import re
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass

import aiohttp
from bs4 import BeautifulSoup

# Import from shared library
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../shared/shared_universal_packages_library'))

from proxy_and_scraping.services.budget_scraper_mixin import (
    BudgetScraperMixin,
    BudgetServiceConfig,
    ServiceSelectionStrategy
)
from proxy_and_scraping.base.interfaces import ScrapingResult

logger = logging.getLogger(__name__)


@dataclass
class TranscriptMetadata:
    """Metadata for fetched transcript."""
    source: str  # "proxy-scraped" | "manual" | "auto-generated"
    language: str
    proxy_service: str  # "scrapingbee" | "scrapeninja" | "firecrawl"
    video_id: str


class ProxyTranscriptFetcher(BudgetScraperMixin):
    """
    Fetch YouTube transcripts using proxy services.

    Usage:
        fetcher = ProxyTranscriptFetcher()
        text, metadata = await fetcher.fetch_transcript("video_id")
    """

    def __init__(self):
        """Initialize proxy transcript fetcher with API keys from environment."""
        config = BudgetServiceConfig(
            firecrawl_api_key=os.getenv('FIRECRAWL_API_KEY', ''),
            scrapeninja_api_key=os.getenv('SCRAPENINJA_API_KEY', ''),
            scrapebee_api_key=os.getenv('SCRAPINGBEE_API_KEY', ''),
            timeout=30,
            retry_attempts=3,
            preferred_service='scrapingbee',
            strategy=ServiceSelectionStrategy.PREFERRED_FIRST,
            enable_quality_gates=True,
            enable_deduplication=True,
        )

        # Initialize BudgetScraperMixin
        super().__init__(config)
        self.session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session

    async def close(self):
        """Close HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()

    async def fetch_transcript(
        self,
        video_id: str,
        languages: tuple = ('en', 'en-US', 'en-GB'),
        max_retries: int = 3
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Fetch transcript for a video using proxy services.

        Args:
            video_id: YouTube video ID
            languages: Tuple of language codes to try (in order)
            max_retries: Maximum number of retries across services

        Returns:
            Tuple of (text, source, language):
            - text: Full transcript as plaintext (or None)
            - source: "proxy-scraped" | None
            - language: Language code used (or None)
        """
        url = f"https://www.youtube.com/watch?v={video_id}"

        for attempt in range(max_retries):
            try:
                # Scrape YouTube video page with proxy
                html, metadata = await self.scrape_with_budget_service(
                    url,
                    options={
                        'render_js': True,
                        'wait_for': 3000,  # Wait for transcript to load
                        'country_code': 'us'
                    }
                )

                if not html:
                    logger.warning(f"Empty HTML response for {video_id} on attempt {attempt + 1}")
                    continue

                # Parse transcript from HTML
                transcript_data = self._extract_transcript_from_html(html, video_id)

                if transcript_data:
                    text = self._format_transcript(transcript_data)
                    metadata_obj = TranscriptMetadata(
                        source="proxy-scraped",
                        language=transcript_data.get('language_code', 'en'),
                        proxy_service=metadata.get('service', 'unknown'),
                        video_id=video_id
                    )

                    logger.info(f"✅ Successfully fetched transcript for {video_id} using {metadata_obj.proxy_service}")
                    return (text, "proxy-scraped", metadata_obj.language)

                else:
                    logger.warning(f"No transcript data found in HTML for {video_id} on attempt {attempt + 1}")

            except Exception as e:
                logger.error(f"Error fetching transcript for {video_id} on attempt {attempt + 1}: {type(e).__name__}: {e}")
                continue

        logger.error(f"❌ Failed to fetch transcript for {video_id} after {max_retries} attempts")
        return (None, None, None)

    def _extract_transcript_from_html(self, html: str, video_id: str) -> Optional[Dict[str, Any]]:
        """
        Extract transcript data from YouTube video page HTML.

        The transcript is typically embedded in:
        1. ytInitialPlayerResponse (JSON in script tag)
        2. ytInitialData (JSON in script tag)
        3. Dynamic loading via AJAX

        Args:
            html: Raw HTML from YouTube video page
            video_id: YouTube video ID

        Returns:
            Transcript data dict with 'segments' and 'language_code', or None
        """
        # Method 1: Try to find ytInitialPlayerResponse
        player_response_match = re.search(r'var ytInitialPlayerResponse = ({.+?});', html)
        if player_response_match:
            try:
                player_data = json.loads(player_response_match.group(1))
                transcript_data = self._extract_from_player_response(player_data)
                if transcript_data:
                    return transcript_data
            except json.JSONDecodeError:
                logger.debug("Failed to parse ytInitialPlayerResponse JSON")

        # Method 2: Try to find ytInitialData
        initial_data_match = re.search(r'var ytInitialData = ({.+?});', html)
        if initial_data_match:
            try:
                initial_data = json.loads(initial_data_match.group(1))
                transcript_data = self._extract_from_initial_data(initial_data)
                if transcript_data:
                    return transcript_data
            except json.JSONDecodeError:
                logger.debug("Failed to parse ytInitialData JSON")

        # Method 3: Search for transcript in script tags (more permissive regex)
        script_pattern = re.compile(r'"captions":\s*({.*?})', re.DOTALL)
        script_matches = script_pattern.findall(html)

        for match_str in script_matches:
            try:
                # Try to parse the extracted JSON
                transcript_json = json.loads(match_str)

                # Navigate through the structure to find transcript segments
                if 'playerCaptionsTracklistRenderer' in transcript_json:
                    caption_data = transcript_json['playerCaptionsTracklistRenderer']
                    if 'captionTracks' in caption_data and caption_data['captionTracks']:
                        # Get the first available caption track
                        track = caption_data['captionTracks'][0]
                        if 'baseUrl' in track:
                            # We found a transcript URL - fetch it
                            return self._fetch_transcript_from_url(track['baseUrl'])
            except (json.JSONDecodeError, KeyError):
                continue

        logger.debug(f"No transcript data found in HTML for {video_id}")
        return None

    def _extract_from_player_response(self, player_data: Dict) -> Optional[Dict[str, Any]]:
        """Extract transcript from ytInitialPlayerResponse."""
        try:
            captions = player_data.get('captions', {})
            renderer = captions.get('playerCaptionsTracklistRenderer', {})
            tracks = renderer.get('captionTracks', [])

            if not tracks:
                return None

            # Get first available track (prefer manual over auto-generated)
            track = tracks[0]
            kind = track.get('kind', '')

            # Try to get baseUrl for fetching
            base_url = track.get('baseUrl')
            if base_url:
                return self._fetch_transcript_from_url(base_url)

            return None

        except (KeyError, IndexError) as e:
            logger.debug(f"Failed to extract from player response: {e}")
            return None

    def _extract_from_initial_data(self, initial_data: Dict) -> Optional[Dict[str, Any]]:
        """Extract transcript from ytInitialData."""
        try:
            # Navigate through complex YouTube data structure
            # This is a simplified search - real structure may vary
            def find_captions(obj, depth=0):
                if depth > 10:  # Prevent infinite recursion
                    return None

                if isinstance(obj, dict):
                    if 'captionTracks' in obj:
                        return obj['captionTracks']
                    for key, value in obj.items():
                        result = find_captions(value, depth + 1)
                        if result:
                            return result
                elif isinstance(obj, list):
                    for item in obj:
                        result = find_captions(item, depth + 1)
                        if result:
                            return result
                return None

            tracks = find_captions(initial_data)
            if tracks and len(tracks) > 0:
                track = tracks[0]
                base_url = track.get('baseUrl')
                if base_url:
                    return self._fetch_transcript_from_url(base_url)

            return None

        except Exception as e:
            logger.debug(f"Failed to extract from initial data: {e}")
            return None

    async def _fetch_transcript_from_url(self, transcript_url: str) -> Optional[Dict[str, Any]]:
        """
        Fetch transcript data from YouTube's transcript URL.

        Args:
            transcript_url: URL to transcript data (usually XML)

        Returns:
            Transcript data dict with 'segments' and 'language_code'
        """
        try:
            session = await self._get_session()

            async with session.get(transcript_url) as response:
                if response.status != 200:
                    logger.warning(f"Transcript URL returned status {response.status}")
                    return None

                content = await response.text()

                # Parse XML transcript format
                # YouTube returns XML like: <transcript><text start="0.0" dur="1.5">Hello</text></transcript>

                # Use regex to extract segments (simpler than full XML parsing)
                segment_pattern = re.compile(r'<text start="([0-9.]+)" dur="([0-9.]+)">(.+?)</text>', re.DOTALL)
                matches = segment_pattern.findall(content)

                if not matches:
                    logger.warning("No transcript segments found in XML")
                    return None

                segments = []
                for start, duration, text in matches:
                    segments.append({
                        'text': text,
                        'start': float(start),
                        'duration': float(duration)
                    })

                return {
                    'segments': segments,
                    'language_code': 'en'  # Default - could be parsed from URL params
                }

        except Exception as e:
            logger.error(f"Error fetching transcript from URL: {type(e).__name__}: {e}")
            return None

    def _format_transcript(self, transcript_data: Dict[str, Any]) -> str:
        """
        Format transcript data into plain text.

        Args:
            transcript_data: Dict with 'segments' and 'language_code'

        Returns:
            Plain text transcript
        """
        segments = transcript_data.get('segments', [])

        # Join all segments with newlines
        text_segments = [seg.get('text', '') for seg in segments if seg.get('text')]
        transcript_text = "\n".join(text_segments)

        # Clean up common issues
        transcript_text = re.sub(r'\n\s*\n', '\n', transcript_text)  # Remove empty lines
        transcript_text = transcript_text.strip()

        return transcript_text


# Convenience function for backward compatibility
async def fetch_transcript_text_with_proxy(
    video_id: str,
    languages: tuple = ('en', 'en-US', 'en-GB'),
    max_retries: int = 3
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Fetch transcript using proxy services (convenience function).

    Compatible interface with transcript_fetcher.fetch_transcript_text()

    Args:
        video_id: YouTube video ID
        languages: Tuple of language codes to try (in order)
        max_retries: Maximum number of retries

    Returns:
        Tuple of (text, source, language)
    """
    fetcher = ProxyTranscriptFetcher()
    try:
        return await fetcher.fetch_transcript(video_id, languages, max_retries)
    finally:
        await fetcher.close()


# For testing
if __name__ == "__main__":
    import asyncio

    async def test():
        """Test proxy transcript fetching."""
        video_id = "jNQXAC9IVRw"  # "Me at the zoo" - classic test video

        print(f"Testing proxy transcript fetch for video: {video_id}")
        print("=" * 60)

        text, source, language = await fetch_transcript_text_with_proxy(video_id)

        if text:
            print(f"✅ SUCCESS!")
            print(f"Source: {source}")
            print(f"Language: {language}")
            print(f"Transcript length: {len(text)} characters")
            print(f"\nFirst 500 characters:\n{text[:500]}")
        else:
            print(f"❌ FAILED - No transcript retrieved")

    asyncio.run(test())
