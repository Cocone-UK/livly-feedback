"""CLI entrypoint for the feedback pipeline."""

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

from config import load_game_config
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
    parser = argparse.ArgumentParser(description="Feedback Pipeline")
    parser.add_argument(
        "--game",
        default="livly",
        help="Game slug from games.json (default: livly)",
    )
    parser.add_argument(
        "--scrapers",
        default=None,
        help="Which scrapers to run: 'all', 'discord', or comma-separated list",
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
        help="Google Sheets spreadsheet ID (overrides games.json)",
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


def _check_tables_exist(client, game_config: dict) -> None:
    """Verify game tables exist in Supabase. Fail fast if not."""
    table_name = game_config["tables"]["scrape_runs"]
    try:
        client.table(table_name).select("id").limit(1).execute()
    except Exception as e:
        if "relation" in str(e).lower() or "404" in str(e) or "does not exist" in str(e).lower():
            logger.error("Table '%s' does not exist. Run the DDL from docs/superpowers/specs/", table_name)
            sys.exit(1)
        raise


def run(args: argparse.Namespace) -> None:
    game_config = load_game_config(args.game)
    logger.info("Running pipeline for game: %s (%s)", game_config["slug"], game_config["display_name"])

    # CLI --sheets-id overrides config
    if args.sheets_id:
        game_config["sheets_id"] = args.sheets_id

    client = get_supabase_client()
    since = datetime.now(timezone.utc) - timedelta(days=7)

    tables = game_config["tables"]
    scrape_runs_table = tables["scrape_runs"]
    raw_table = tables["feedback_raw"]

    # Verify tables exist before doing any work
    _check_tables_exist(client, game_config)

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
                results = scraper_fn(since=since, game_config=game_config)
            elif name in ("appstore", "google_play"):
                results = scraper_fn(game_config=game_config)
            elif name == "reddit":
                results = scraper_fn(since=since, game_config=game_config)
            else:
                results = scraper_fn(game_config=game_config)

            for result in results:
                run_record = with_retry(
                    lambda r=result: client.table(scrape_runs_table)
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
                    dedup_result = deduplicate_and_insert(client, result.items, run_id, table_name=raw_table)
                    new_count = dedup_result["inserted"]

                with_retry(
                    lambda rid=run_id, f=fetched, n=new_count, r=result: client.table(scrape_runs_table).update({
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
                lambda: client.table(scrape_runs_table).insert({
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
        result = classify_batch(client, game_config)
        logger.info("Classification: %d classified, %d failed", result["classified"], result["failed"])

    if args.export:
        logger.info("Exporting to Google Sheets...")
        from outputs.sheets import export_to_sheets
        export_to_sheets(client, game_config)

        slack_url = game_config.get("slack_webhook_url") or os.environ.get("SLACK_WEBHOOK_URL")
        if slack_url:
            from outputs.slack import build_digest_message, post_slack_digest

            classified_table = tables["feedback_classified"]
            classified = (
                client.table(classified_table)
                .select("*, feedback_raw(*)")
                .gte("classified_at", since.isoformat())
                .execute()
            )
            rows = classified.data or []
            sheet_url = args.sheet_url or "https://docs.google.com/spreadsheets"
            message = build_digest_message(rows, sheet_url=sheet_url, game_config=game_config)
            post_slack_digest(message, webhook_url=slack_url)
            logger.info("Slack digest posted")
        else:
            logger.info("No Slack webhook configured, skipping digest")

        logger.info("Export complete")


def main():
    args = parse_args()
    run(args)


if __name__ == "__main__":
    main()
