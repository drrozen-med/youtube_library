"""
Proxy-Enabled Transcript Fetcher
=================================

Simplified YouTube transcript fetching using proxy services with requests library.

Uses:
- ScrapingBee (primary)
- ScrapeNinja (fallback)
- Firecrawl (last resort)
"""

import html
import json
import logging
import os
import re
from typing import Any, Optional, Tuple
from dotenv import load_dotenv
import requests

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class ProxyTranscriptFetcherV3:
    """Fetch YouTube transcripts using proxy services."""

    def __init__(self):
        """Initialize with API keys from environment."""
        self.scrapingbee_key = os.getenv('SCRAPINGBEE_API_KEY', '')
        self.scrapeninja_key = os.getenv('SCRAPENINJA_API_KEY', '')
        self.firecrawl_key = os.getenv('FIRECRAWL_API_KEY', '')

        logger.info(f"ProxyTranscriptFetcherV3 initialized:")
        logger.info(f"  ScrapingBee: {'✓' if self.scrapingbee_key else '✗'}")
        logger.info(f"  ScrapeNinja: {'✓' if self.scrapeninja_key else '✗'}")
        logger.info(f"  Firecrawl: {'✓' if self.firecrawl_key else '✗'}")

    def fetch_transcript_sync(
        self,
        video_id: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Fetch transcript for a video (synchronous version).

        Args:
            video_id: YouTube video ID

        Returns:
            Tuple of (text, source, language)
        """
        url = f"https://www.youtube.com/watch?v={video_id}"

        # Try ScrapingBee first
        if self.scrapingbee_key:
            try:
                logger.info(f"Trying ScrapingBee for {video_id}")
                html = self._scrape_with_scrapingbee(url)
                if html:
                    transcript = self._extract_transcript(html, video_id)
                    if transcript:
                        logger.info(f"✅ Successfully fetched transcript for {video_id} using ScrapingBee")
                        return (transcript, "proxy-scraped", "en")
            except Exception as e:
                logger.warning(f"ScrapingBee failed for {video_id}: {e}")

        # Try ScrapeNinja
        if self.scrapeninja_key:
            try:
                logger.info(f"Trying ScrapeNinja for {video_id}")
                html = self._scrape_with_scrapeninja(url)
                if html:
                    transcript = self._extract_transcript(html, video_id)
                    if transcript:
                        logger.info(f"✅ Successfully fetched transcript for {video_id} using ScrapeNinja")
                        return (transcript, "proxy-scraped", "en")
            except Exception as e:
                logger.warning(f"ScrapeNinja failed for {video_id}: {e}")

        # Try Firecrawl
        if self.firecrawl_key:
            try:
                logger.info(f"Trying Firecrawl for {video_id}")
                html = self._scrape_with_firecrawl(url)
                if html:
                    transcript = self._extract_transcript(html, video_id)
                    if transcript:
                        logger.info(f"✅ Successfully fetched transcript for {video_id} using Firecrawl")
                        return (transcript, "proxy-scraped", "en")
            except Exception as e:
                logger.warning(f"Firecrawl failed for {video_id}: {e}")

        logger.error(f"❌ All proxy services failed for {video_id}")
        return (None, None, None)

    def _scrape_with_scrapingbee(self, url: str) -> Optional[str]:
        """Scrape URL using ScrapingBee API."""
        api_url = "https://app.scrapingbee.com/api/v1/"

        params = {
            'api_key': self.scrapingbee_key,
            'url': url,
            'render_js': 'true',
            'wait': 3000,
            'country_code': 'us'
        }

        try:
            response = requests.get(api_url, params=params, timeout=30)
            if response.status_code == 200:
                return response.text
            else:
                logger.error(f"ScrapingBee error: {response.status_code} - {response.text[:200]}")
                return None
        except Exception as e:
            logger.error(f"ScrapingBee exception: {e}")
            return None

    def _scrape_with_scrapeninja(self, url: str) -> Optional[str]:
        """Scrape URL using ScrapeNinja API."""
        # APIRoad endpoint is the stable path used in Scrapers-Hub.
        api_url = "https://scrapeninja.apiroad.net/scrape"

        headers = {
            'X-Apiroad-Key': self.scrapeninja_key,
            'Content-Type': 'application/json'
        }

        payload = {
            'url': url,
            'geo': 'us',
            'retryNum': 2,
            'blockImages': True,
            'blockMedia': True,
            'screenshot': 0
        }

        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=30)
            if response.status_code == 200:
                data = response.json()
                return data.get('body')
            else:
                logger.error(f"ScrapeNinja error: {response.status_code} - {response.text[:200]}")
                return None
        except Exception as e:
            logger.error(f"ScrapeNinja exception: {e}")
            return None

    def _scrape_with_firecrawl(self, url: str) -> Optional[str]:
        """Scrape URL using Firecrawl API."""
        api_url = "https://api.firecrawl.dev/v1/scrape"

        headers = {
            'Authorization': f'Bearer {self.firecrawl_key}',
            'Content-Type': 'application/json'
        }

        payload = {
            'url': url,
            'formats': ['html', 'markdown']
        }

        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if 'data' in data and 'html' in data['data']:
                    return data['data']['html']
                elif 'data' in data and 'markdown' in data['data']:
                    return data['data']['markdown']
            else:
                logger.error(f"Firecrawl error: {response.status_code} - {response.text[:200]}")
                return None
        except Exception as e:
            logger.error(f"Firecrawl exception: {e}")
            return None

    def _extract_transcript(self, html: str, video_id: str) -> Optional[str]:
        """Extract transcript from YouTube video page HTML."""
        # Method 1: Try to find ytInitialPlayerResponse
        player_response_match = re.search(r'var ytInitialPlayerResponse = ({.+?});', html)
        if player_response_match:
            try:
                player_data = json.loads(player_response_match.group(1))
                transcript_url = self._find_transcript_url(player_data)
                if transcript_url:
                    return self._fetch_transcript_from_url(transcript_url)
            except (json.JSONDecodeError, KeyError) as e:
                logger.debug(f"Failed to extract from player response: {e}")

        # Method 2: Try to find ytInitialData
        initial_data_match = re.search(r'var ytInitialData = ({.+?});', html)
        if initial_data_match:
            try:
                initial_data = json.loads(initial_data_match.group(1))
                transcript_url = self._find_transcript_url_recursive(initial_data)
                if transcript_url:
                    return self._fetch_transcript_from_url(transcript_url)
            except (json.JSONDecodeError, KeyError) as e:
                logger.debug(f"Failed to extract from initial data: {e}")

        logger.debug(f"No transcript data found in HTML for {video_id}")
        return None

    def _find_transcript_url(self, data: dict) -> Optional[str]:
        """Find transcript URL in player response data."""
        try:
            captions = data.get('captions', {})
            renderer = captions.get('playerCaptionsTracklistRenderer', {})
            tracks = renderer.get('captionTracks', [])

            if tracks:
                # Get first available track
                track = tracks[0]
                return track.get('baseUrl')
        except (KeyError, IndexError):
            pass

        return None

    def _find_transcript_url_recursive(self, obj: Any, depth: int = 0) -> Optional[str]:
        """Recursively search for transcript URL in data structure."""
        if depth > 10:
            return None

        if isinstance(obj, dict):
            if 'captionTracks' in obj and isinstance(obj['captionTracks'], list):
                tracks = obj['captionTracks']
                if tracks and 'baseUrl' in tracks[0]:
                    return tracks[0]['baseUrl']

            for key, value in obj.items():
                result = self._find_transcript_url_recursive(value, depth + 1)
                if result:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = self._find_transcript_url_recursive(item, depth + 1)
                if result:
                    return result

        return None

    def _fetch_transcript_from_url(self, transcript_url: str) -> Optional[str]:
        """Fetch transcript XML and parse it."""
        try:
            response = requests.get(transcript_url, timeout=10)
            if response.status_code == 200:
                content = response.text
                # Parse XML transcript format
                segment_pattern = re.compile(r'<text start="([0-9.]+)" dur="([0-9.]+)">(.+?)</text>', re.DOTALL)
                matches = segment_pattern.findall(content)

                if matches:
                    segments = [html.unescape(text) for _, _, text in matches]
                    transcript_text = "\n".join(segments)
                    # Clean up
                    transcript_text = re.sub(r'\n\s*\n', '\n', transcript_text)
                    return transcript_text.strip()
        except Exception as e:
            logger.error(f"Error fetching transcript from URL: {e}")

        return None


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
        languages: Tuple of language codes to try (in order) - not used in v3
        max_retries: Maximum number of retries

    Returns:
        Tuple of (text, source, language)
    """
    fetcher = ProxyTranscriptFetcherV3()
    return fetcher.fetch_transcript_sync(video_id)
