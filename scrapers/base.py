"""Base types and utilities shared across all scrapers."""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class FeedbackItem:
    """A single piece of user feedback from any source."""

    source: str  # appstore_ios, google_play, discord, reddit
    region: str  # en, jp
    external_id: str  # platform's native ID
    author: Optional[str]
    content: str
    rating: Optional[int]  # 1-5 for stores, None for discord/reddit
    channel: Optional[str]  # discord channel name, subreddit, etc.
    source_url: Optional[str]
    posted_at: datetime


@dataclass
class ScraperResult:
    """Result from a scraper run."""

    source: str
    region: str
    items: list[FeedbackItem]
    error: Optional[str] = None


def compute_content_hash(
    source: str,
    external_id: str,
    content: str,
    rating: Optional[int],
) -> str:
    """SHA-256 hash for deduplication. Includes rating so rating-only changes are caught."""
    raw = f"{source}|{external_id}|{content}|{rating}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
