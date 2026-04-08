"""iOS App Store review scraper via Apple RSS feed."""

import httpx
from datetime import datetime, timezone
from dateutil import parser as dateutil_parser
from scrapers.base import FeedbackItem, ScraperResult

RSS_URL = "https://itunes.apple.com/{country}/rss/customerreviews/page={page}/id={app_id}/sortBy=mostRecent/json"


def _parse_rss_entry(entry: dict, region: str) -> FeedbackItem:
    """Parse a single RSS feed entry into a FeedbackItem."""
    posted_at = dateutil_parser.isoparse(entry["updated"]["label"])
    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=timezone.utc)

    return FeedbackItem(
        source="appstore_ios",
        region=region,
        external_id=entry["id"]["label"],
        author=entry.get("author", {}).get("name", {}).get("label"),
        content=entry["content"]["label"],
        rating=int(entry["im:rating"]["label"]),
        channel=None,
        source_url=entry.get("link", {}).get("attributes", {}).get("href"),
        posted_at=posted_at,
    )


def scrape_appstore(
    game_config: dict,
    max_pages: int = 10,
) -> list[ScraperResult]:
    app_id = game_config["appstore_id"]
    country_to_region = game_config["country_to_region"]
    countries = list(country_to_region.keys())

    max_pages = min(max_pages, 10)
    results = []

    for country in countries:
        region = country_to_region.get(country, "en")
        items = []
        error = None

        try:
            for page in range(1, max_pages + 1):
                url = RSS_URL.format(country=country, page=page, app_id=app_id)
                resp = httpx.get(url, timeout=30)
                resp.raise_for_status()
                data = resp.json()

                entries = data.get("feed", {}).get("entry", [])
                if not entries:
                    break

                for entry in entries:
                    if page == 1 and "im:rating" not in entry:
                        continue
                    items.append(_parse_rss_entry(entry, region))
        except Exception as e:
            error = str(e)

        results.append(ScraperResult(
            source="appstore_ios", region=region, items=items, error=error
        ))

    return results
