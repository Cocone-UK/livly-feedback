from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from scrapers.reddit_scraper import _submission_to_feedback, _comment_to_feedback


def _make_mock_submission():
    sub = MagicMock()
    sub.id = "abc123"
    sub.author.name = "redditor1"
    sub.title = "Account recovery help"
    sub.selftext = "I forgot my password and can't get back in"
    sub.created_utc = datetime(2026, 3, 10, tzinfo=timezone.utc).timestamp()
    sub.permalink = "/r/LivlyIsland/comments/abc123/account_recovery_help/"
    sub.url = "https://reddit.com/r/LivlyIsland/comments/abc123/account_recovery_help/"
    return sub


def _make_mock_comment():
    comment = MagicMock()
    comment.id = "cmt456"
    comment.author.name = "redditor2"
    comment.body = "Same here, gacha rates are awful"
    comment.created_utc = datetime(2026, 3, 11, tzinfo=timezone.utc).timestamp()
    comment.permalink = "/r/LivlyIsland/comments/abc123/comment/cmt456/"
    return comment


def test_submission_to_feedback():
    sub = _make_mock_submission()
    item = _submission_to_feedback(sub)
    assert item.source == "reddit"
    assert item.region == "en"
    assert item.external_id == "post_abc123"
    assert "password" in item.content
    assert item.channel == "r/LivlyIsland"


def test_submission_includes_title_in_content():
    sub = _make_mock_submission()
    item = _submission_to_feedback(sub)
    assert "Account recovery help" in item.content


def test_comment_to_feedback():
    comment = _make_mock_comment()
    item = _comment_to_feedback(comment)
    assert item.source == "reddit"
    assert item.external_id == "comment_cmt456"
    assert "gacha" in item.content
