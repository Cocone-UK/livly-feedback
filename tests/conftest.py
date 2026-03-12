"""Shared test fixtures."""

import pytest
from datetime import datetime, timezone
from scrapers.base import FeedbackItem


@pytest.fixture
def sample_feedback_item():
    return FeedbackItem(
        source="appstore_ios",
        region="en",
        external_id="review-123",
        author="testuser",
        content="This game is amazing but gacha rates are terrible",
        rating=3,
        channel=None,
        source_url="https://apps.apple.com/review/123",
        posted_at=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def sample_discord_item():
    return FeedbackItem(
        source="discord",
        region="en",
        external_id="msg-456",
        author="discorduser#1234",
        content="The new update broke my island layout",
        rating=None,
        channel="app-bug-report",
        source_url=None,
        posted_at=datetime(2026, 3, 11, 15, 30, 0, tzinfo=timezone.utc),
    )
