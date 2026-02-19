"""
Proxy-Enabled Transcript Fetcher
=================================

Uses youtube-transcript-api through provider proxies to avoid local IP blocks.
"""

import logging
import os
import random
import time
from typing import Optional, Tuple

import requests
import urllib3
from dotenv import load_dotenv
from youtube_transcript_api import (
    CouldNotRetrieveTranscript,
    IpBlocked,
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
)
from youtube_transcript_api.proxies import GenericProxyConfig

# Load environment variables once.
load_dotenv()

logger = logging.getLogger(__name__)


class ProxyTranscriptFetcherV3:
    """Fetch YouTube transcripts via configured proxy providers."""

    def __init__(self) -> None:
        self.scrapingbee_key = os.getenv("SCRAPINGBEE_API_KEY", "").strip()
        self.max_retries = int(os.getenv("PROXY_TRANSCRIPT_MAX_RETRIES", "4"))

    def fetch_transcript_sync(
        self,
        video_id: str,
        languages: tuple = ("en", "en-US", "en-GB"),
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Fetch transcript via proxy providers.

        Returns:
            Tuple[text, source, language]
        """
        if self.scrapingbee_key:
            text, source, lang = self._fetch_with_scrapingbee(video_id, languages)
            if text:
                return text, source, lang

        logger.error("All configured proxy transcript providers failed for %s", video_id)
        return None, None, None

    def _fetch_with_scrapingbee(
        self,
        video_id: str,
        languages: tuple,
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Use ScrapingBee proxy mode with youtube-transcript-api.
        """
        delay = 1.5
        for attempt in range(1, self.max_retries + 1):
            try:
                api = self._build_scrapingbee_api()
                return self._fetch_with_api(api, video_id, languages)
            except (IpBlocked, RequestBlocked) as exc:
                if attempt == self.max_retries:
                    logger.error(
                        "ScrapingBee proxy exhausted retries for %s: %s",
                        video_id,
                        exc,
                    )
                    break
                sleep_for = delay + random.uniform(0.1, 0.9)
                logger.warning(
                    "ScrapingBee attempt %s/%s blocked for %s, retrying in %.1fs",
                    attempt,
                    self.max_retries,
                    video_id,
                    sleep_for,
                )
                time.sleep(sleep_for)
                delay = min(delay * 2.0, 20.0)
            except (
                CouldNotRetrieveTranscript,
                NoTranscriptFound,
                TranscriptsDisabled,
                VideoUnavailable,
            ) as exc:
                logger.warning("ScrapingBee transcript unavailable for %s: %s", video_id, exc)
                return None, None, None
            except Exception as exc:
                if attempt == self.max_retries:
                    logger.error(
                        "ScrapingBee proxy failed for %s after %s attempts: %s",
                        video_id,
                        self.max_retries,
                        exc,
                    )
                    break
                sleep_for = delay + random.uniform(0.1, 0.9)
                logger.warning(
                    "ScrapingBee attempt %s/%s errored for %s (%s), retrying in %.1fs",
                    attempt,
                    self.max_retries,
                    video_id,
                    type(exc).__name__,
                    sleep_for,
                )
                time.sleep(sleep_for)
                delay = min(delay * 2.0, 20.0)
        return None, None, None

    def _build_scrapingbee_api(self) -> YouTubeTranscriptApi:
        """
        Build youtube-transcript-api client over ScrapingBee proxy transport.
        """
        # ScrapingBee proxy mode requires query args in username and SSL verify disabled.
        proxy_user = (
            f"{self.scrapingbee_key}:render_js=False&premium_proxy=True&country_code=us"
        )
        proxy_cfg = GenericProxyConfig(
            http_url=f"http://{proxy_user}@proxy.scrapingbee.com:8886",
            https_url=f"https://{proxy_user}@proxy.scrapingbee.com:8887",
        )

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        session = requests.Session()
        session.verify = False
        return YouTubeTranscriptApi(proxy_config=proxy_cfg, http_client=session)

    def _fetch_with_api(
        self,
        api: YouTubeTranscriptApi,
        video_id: str,
        languages: tuple,
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Shared transcript selection strategy:
        1) manually created in preferred language
        2) auto-generated in preferred language
        3) any available transcript
        """
        transcript_list = api.list(video_id)

        for code in languages:
            try:
                transcript = transcript_list.find_manually_created_transcript([code])
                fetched = transcript.fetch()
                text = "\n".join([part.text for part in fetched if hasattr(part, "text")])
                if text:
                    return text, "manual", transcript.language_code
            except (NoTranscriptFound, CouldNotRetrieveTranscript):
                continue

        for code in languages:
            try:
                transcript = transcript_list.find_generated_transcript([code])
                fetched = transcript.fetch()
                text = "\n".join([part.text for part in fetched if hasattr(part, "text")])
                if text:
                    return text, "auto-generated", transcript.language_code
            except (NoTranscriptFound, CouldNotRetrieveTranscript):
                continue

        for transcript in transcript_list:
            try:
                fetched = transcript.fetch()
                text = "\n".join([part.text for part in fetched if hasattr(part, "text")])
                if text:
                    source = "manual" if not transcript.is_generated else "auto-generated"
                    return text, source, transcript.language_code
            except Exception:
                continue

        return None, None, None


async def fetch_transcript_text_with_proxy(
    video_id: str,
    languages: tuple = ("en", "en-US", "en-GB"),
    max_retries: int = 3,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Backward-compatible async wrapper.
    """
    fetcher = ProxyTranscriptFetcherV3()
    fetcher.max_retries = max_retries
    return fetcher.fetch_transcript_sync(video_id, languages=languages)
