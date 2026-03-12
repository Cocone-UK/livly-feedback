from scrapers.base import FeedbackItem, compute_content_hash
from datetime import datetime, timezone


def test_feedback_item_creation():
    item = FeedbackItem(
        source="appstore_ios",
        region="en",
        external_id="12345",
        author="testuser",
        content="Great game!",
        rating=5,
        channel=None,
        source_url="https://example.com",
        posted_at=datetime(2026, 3, 10, tzinfo=timezone.utc),
    )
    assert item.source == "appstore_ios"
    assert item.rating == 5


def test_compute_content_hash_deterministic():
    hash1 = compute_content_hash("appstore_ios", "12345", "Great game!", 5)
    hash2 = compute_content_hash("appstore_ios", "12345", "Great game!", 5)
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 hex


def test_compute_content_hash_changes_with_content():
    hash1 = compute_content_hash("appstore_ios", "12345", "Great game!", 5)
    hash2 = compute_content_hash("appstore_ios", "12345", "Bad game!", 5)
    assert hash1 != hash2


def test_compute_content_hash_changes_with_rating():
    hash1 = compute_content_hash("appstore_ios", "12345", "Great game!", 5)
    hash2 = compute_content_hash("appstore_ios", "12345", "Great game!", 1)
    assert hash1 != hash2


def test_compute_content_hash_none_rating():
    hash1 = compute_content_hash("discord", "msg-001", "Love this game", None)
    hash2 = compute_content_hash("discord", "msg-001", "Love this game", None)
    assert hash1 == hash2
