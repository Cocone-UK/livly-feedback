"""Google Play review scraper using google-play-scraper."""

from datetime import datetime, timezone
from typing import Optional
from google_play_scraper import reviews as gplay_reviews, Sort
from scrapers.base import FeedbackItem, ScraperResult

PLAY_STORE_URL = "https://play.google.com/store/apps/details?id={pkg}&reviewId={review_id}"


def _parse_review(review: dict, region: str, package_id: str) -> FeedbackItem:
    posted_at = review["at"]
    if isinstance(posted_at, datetime) and posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=timezone.utc)

    return FeedbackItem(
        source="google_play",
        region=region,
        external_id=review["reviewId"],
        author=review.get("userName"),
        content=review["content"] or "",
        rating=review.get("score"),
        channel=None,
        source_url=PLAY_STORE_URL.format(pkg=package_id, review_id=review["reviewId"]),
        posted_at=posted_at,
    )


def scrape_google_play(
    game_config: dict,
    max_pages: int = 10,
    since: Optional[datetime] = None,
) -> list[ScraperResult]:
    package_id = game_config["google_play_id"]
    regions = game_config["google_play_regions"]
    country_to_region = game_config["country_to_region"]

    results = []

    for lang, country in regions:
        region = country_to_region.get(country, "en")
        items = []
        error = None
        token = None

        try:
            for _ in range(max_pages):
                batch, token = gplay_reviews(
                    package_id,
                    lang=lang,
                    country=country,
                    sort=Sort.NEWEST,
                    count=200,
                    continuation_token=token,
                )

                if not batch:
                    break

                for review in batch:
                    if not review.get("content"):
                        continue
                    item = _parse_review(review, region, package_id)
                    if since and item.posted_at < since:
                        token = None
                        break
                    items.append(item)

                if token is None:
                    break
        except Exception as e:
            error = str(e)

        results.append(ScraperResult(
            source="google_play", region=region, items=items, error=error
        ))

    return results
