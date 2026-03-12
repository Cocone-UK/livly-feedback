import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from scrapers.discord_scraper import _message_to_feedback, TARGET_CHANNELS


def _make_mock_message(content="Bug: my island disappeared", channel_name="app-bug-report",
                       author_name="user123", message_id=789, created_at=None):
    msg = MagicMock()
    msg.content = content
    msg.channel.name = channel_name
    msg.author.name = author_name
    msg.author.bot = False
    msg.id = message_id
    msg.created_at = created_at or datetime(2026, 3, 11, 10, 0, 0, tzinfo=timezone.utc)
    msg.jump_url = f"https://discord.com/channels/123/456/{message_id}"
    return msg


def test_message_to_feedback():
    msg = _make_mock_message()
    item = _message_to_feedback(msg)
    assert item.source == "discord"
    assert item.region == "en"
    assert item.external_id == "789"
    assert item.channel == "app-bug-report"
    assert "disappeared" in item.content


def test_message_to_feedback_preserves_channel():
    msg = _make_mock_message(channel_name="gacha-chat")
    item = _message_to_feedback(msg)
    assert item.channel == "gacha-chat"


def test_target_channels_defined():
    expected = [
        "app-bug-report", "app-feedback", "app-poll-feedback",
        "discord-feedback", "discord-poll-feedback",
        "livly-general", "gacha-chat", "q-and-a",
    ]
    for ch in expected:
        assert ch in TARGET_CHANNELS
