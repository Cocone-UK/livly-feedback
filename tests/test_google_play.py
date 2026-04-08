from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from scrapers.google_play import scrape_google_play, _parse_review

LIVLY_CONFIG = {
    "google_play_id": "jp.cocone.livly",
    "google_play_regions": [["en", "us"]],
    "country_to_region": {"us": "en"},
}

SAMPLE_REVIEW = {
    "reviewId": "gp-review-001",
    "userName": "PlayUser",
    "content": "Beautiful art but too many bugs after the last update",
    "score": 2,
    "at": datetime(2026, 3, 9, 10, 30, 0),
    "thumbsUpCount": 5,
}


def test_parse_review():
    item = _parse_review(SAMPLE_REVIEW, region="en", package_id="jp.cocone.livly")
    assert item.source == "google_play"
    assert item.region == "en"
    assert item.external_id == "gp-review-001"
    assert item.rating == 2
    assert "bugs" in item.content
    assert "jp.cocone.livly" in item.source_url


def test_parse_review_jp():
    item = _parse_review(SAMPLE_REVIEW, region="jp", package_id="jp.cocone.livly")
    assert item.region == "jp"


@patch("scrapers.google_play.gplay_reviews")
def test_scrape_google_play_paginates(mock_reviews):
    mock_reviews.side_effect = [
        ([SAMPLE_REVIEW], "token-1"),
        ([SAMPLE_REVIEW], None),
    ]

    results = scrape_google_play(game_config=LIVLY_CONFIG, max_pages=5)

    assert len(results) == 1
    assert len(results[0].items) == 2
    assert mock_reviews.call_count == 2


@patch("scrapers.google_play.gplay_reviews")
def test_scrape_google_play_respects_since(mock_reviews):
    old_review = {**SAMPLE_REVIEW, "at": datetime(2025, 1, 1)}
    mock_reviews.return_value = ([old_review], None)

    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    results = scrape_google_play(game_config=LIVLY_CONFIG, since=since)

    assert len(results[0].items) == 0
