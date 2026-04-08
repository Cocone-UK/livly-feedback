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


@pytest.fixture
def livly_config():
    """Livly game config for testing."""
    return {
        "slug": "livly",
        "display_name": "Livly Island",
        "game_description": "a mobile pet game by Cocone",
        "appstore_id": "1553045339",
        "google_play_id": "jp.cocone.livly",
        "google_play_regions": [["en", "us"], ["ja", "jp"], ["zh_TW", "tw"], ["zh_TW", "hk"]],
        "country_to_region": {"us": "en", "jp": "jp", "tw": "tw", "hk": "hk"},
        "categories": [
            "ux", "tutorial_onboarding", "gacha_monetization", "social",
            "bugs_performance", "content_request", "account_login",
            "art_aesthetics", "general_praise", "events", "localization",
        ],
        "tables": {
            "feedback_raw": "feedback_raw",
            "feedback_classified": "feedback_classified",
            "scrape_runs": "scrape_runs",
            "unclassified_rpc": "unclassified_feedback",
        },
        "sheets_id": "test-sheet-id",
        "sheet_region_groups": {
            "EN": {"regions": ["en"], "summary_field": "summary", "include_region": False, "flag": ":gb:"},
            "ASIA": {"regions": ["jp", "tw", "hk"], "summary_field": "summary_jp", "include_region": True, "flag": ":jp:"},
        },
        "legacy_tabs_to_remove": ["JP Trends", "JP Weekly", "JP Stream", "Raw Data"],
        "slack_webhook_url": None,
    }
