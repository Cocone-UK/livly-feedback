import json
from unittest.mock import patch, MagicMock
from scrapers.appstore import scrape_appstore, _parse_rss_entry

# Sample RSS entry from Apple's feed
LIVLY_CONFIG = {
    "appstore_id": "1553045339",
    "country_to_region": {"us": "en"},
}

SAMPLE_RSS_ENTRY = {
    "author": {"name": {"label": "ReviewerName"}},
    "im:rating": {"label": "4"},
    "title": {"label": "Fun game"},
    "content": {"label": "Really enjoying this pet game. Wish there were more items though."},
    "id": {"label": "12345678"},
    "link": {"attributes": {"href": "https://apps.apple.com/review/12345678"}},
    "im:version": {"label": "3.2.1"},
    "updated": {"label": "2026-03-10T12:00:00-07:00"},
}


def test_parse_rss_entry():
    item = _parse_rss_entry(SAMPLE_RSS_ENTRY, region="en")
    assert item.source == "appstore_ios"
    assert item.region == "en"
    assert item.external_id == "12345678"
    assert item.author == "ReviewerName"
    assert item.rating == 4
    assert "enjoying" in item.content


def test_parse_rss_entry_jp():
    entry = {**SAMPLE_RSS_ENTRY}
    item = _parse_rss_entry(entry, region="jp")
    assert item.region == "jp"


@patch("scrapers.appstore.httpx.get")
def test_scrape_appstore_fetches_pages(mock_get):
    """Scraper should fetch up to 10 pages per country."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"feed": {"entry": [SAMPLE_RSS_ENTRY]}}
    mock_get.return_value = mock_response

    results = scrape_appstore(game_config=LIVLY_CONFIG, max_pages=2)

    assert len(results) == 1
    assert results[0].source == "appstore_ios"
    assert results[0].region == "en"
    assert len(results[0].items) == 2
    assert mock_get.call_count == 2


@patch("scrapers.appstore.httpx.get")
def test_scrape_appstore_handles_empty_page(mock_get):
    """Scraper should stop when a page has no entries."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"feed": {}}
    mock_get.return_value = mock_response

    results = scrape_appstore(game_config=LIVLY_CONFIG, max_pages=10)
    assert len(results[0].items) == 0
