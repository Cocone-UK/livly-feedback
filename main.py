"""CLI entrypoint for the Livly Island feedback system."""

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

from db.client import get_supabase_client
from db.dedup import deduplicate_and_insert
from db.retry import with_retry
from scrapers.appstore import scrape_appstore
from scrapers.google_play import scrape_google_play
from scrapers.discord_scraper import scrape_discord
from scrapers.reddit_scraper import scrape_reddit
from classifier.classify import classify_batch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

SCRAPER_MAP = {
    "appstore": scrape_appstore,
    "google_play": scrape_google_play,
    "discord": scrape_discord,
    "reddit": scrape_reddit,
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Livly Island Feedback System")
    parser.add_argument(
        "--scrapers",
        default=None,
        help="Which scrapers to run: 'all', 'discord', or comma-separated list (appstore,google_play,reddit,discord)",
    )
    parser.add_argument(
        "--classify",
        action="store_true",
        help="Run AI classification on new unclassified items",
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Export to Google Sheets and post Slack digest",
    )
    parser.add_argument(
        "--sheets-id",
        default=None,
        help="Google Sheets spreadsheet ID for export",
    )
    parser.add_argument(
        "--sheet-url",
        default=None,
        help="Google Sheets URL for Slack digest link",
    )
    return parser.parse_args(argv)


def _get_scraper_names(scrapers_arg: str) -> list[str]:
    if scrapers_arg == "all":
        return list(SCRAPER_MAP.keys())
    return [s.strip() for s in scrapers_arg.split(",")]


def run(args: argparse.Namespace) -> None:
    client = get_supabase_client()
    since = datetime.now(timezone.utc) - timedelta(days=7)

    scraper_names = _get_scraper_names(args.scrapers) if args.scrapers else []
    if scraper_names:
        logger.info("Running scrapers: %s", scraper_names)

    for name in scraper_names:
        scraper_fn = SCRAPER_MAP.get(name)
        if not scraper_fn:
            logger.warning("Unknown scraper: %s, skipping", name)
            continue

        try:
            if name == "discord":
                results = scraper_fn(since=since)
            elif name in ("appstore", "google_play"):
                results = scraper_fn()
            elif name == "reddit":
                results = scraper_fn(since=since)
            else:
                results = scraper_fn()

            for result in results:
                run_record = with_retry(
                    lambda r=result: client.table("scrape_runs")
                    .insert({"source": name, "region": r.region, "status": "running"})
                    .execute(),
                    "insert scrape_run",
                )
                run_id = run_record.data[0]["id"]

                fetched = len(result.items)
                new_count = 0

                if result.error:
                    logger.error("Scraper %s (%s) error: %s", name, result.region, result.error)

                if result.items:
                    dedup_result = deduplicate_and_insert(client, result.items, run_id)
                    new_count = dedup_result["inserted"]

                with_retry(
                    lambda rid=run_id, f=fetched, n=new_count, r=result: client.table("scrape_runs").update({
                        "status": "partial" if r.error else "success",
                        "items_fetched": f,
                        "items_new": n,
                        "finished_at": datetime.now(timezone.utc).isoformat(),
                        "error_message": r.error,
                    }).eq("id", rid).execute(),
                    "update scrape_run",
                )

                logger.info("Scraper %s (%s): fetched=%d, new=%d", name, result.region, fetched, new_count)

        except Exception as e:
            logger.error("Scraper %s failed: %s", name, e)
            with_retry(
                lambda: client.table("scrape_runs").insert({
                    "source": name,
                    "region": "unknown",
                    "status": "failed",
                    "error_message": str(e),
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                }).execute(),
                "insert failed scrape_run",
            )

    if args.classify:
        logger.info("Running classification...")
        result = classify_batch(client)
        logger.info("Classification: %d classified, %d failed", result["classified"], result["failed"])

    if args.export:
        logger.info("Exporting to Google Sheets...")
        from outputs.sheets import export_to_sheets

        if args.sheets_id:
            export_to_sheets(client, args.sheets_id)

        if os.environ.get("SLACK_WEBHOOK_URL"):
            from outputs.slack import build_digest_message, post_slack_digest

            classified = (
                client.table("feedback_classified")
                .select("*, feedback_raw(*)")
                .gte("classified_at", since.isoformat())
                .execute()
            )
            rows = classified.data or []
            sheet_url = args.sheet_url or "https://docs.google.com/spreadsheets"
            message = build_digest_message(rows, sheet_url=sheet_url)
            post_slack_digest(message)
            logger.info("Slack digest posted")
        else:
            logger.info("SLACK_WEBHOOK_URL not set, skipping Slack digest")

        logger.info("Weekly export complete")


def main():
    args = parse_args()
    run(args)


if __name__ == "__main__":
    main()
