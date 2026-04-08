"""Game config loader with validation."""

import json
import os

REQUIRED_KEYS = [
    "display_name", "game_description", "appstore_id", "google_play_id",
    "google_play_regions", "country_to_region", "categories", "tables",
    "sheets_id", "sheet_region_groups", "legacy_tabs_to_remove", "slack_webhook_url",
]
REQUIRED_TABLE_KEYS = ["feedback_raw", "feedback_classified", "scrape_runs", "unclassified_rpc"]

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "games.json")


def load_game_config(slug: str) -> dict:
    """Load and validate game config by slug. Injects slug from key."""
    with open(CONFIG_PATH) as f:
        all_games = json.load(f)

    if slug not in all_games:
        available = ", ".join(sorted(all_games.keys()))
        raise ValueError(f"Unknown game '{slug}'. Available: {available}")

    config = all_games[slug]
    config["slug"] = slug

    for key in REQUIRED_KEYS:
        if key not in config:
            raise ValueError(f"Game '{slug}' missing required key: {key}")

    for key in REQUIRED_TABLE_KEYS:
        if key not in config.get("tables", {}):
            raise ValueError(f"Game '{slug}' missing tables key: {key}")

    country_to_region = config["country_to_region"]
    for pair in config["google_play_regions"]:
        country = pair[1]
        if country not in country_to_region:
            raise ValueError(
                f"Game '{slug}': country '{country}' in google_play_regions "
                f"but missing from country_to_region"
            )

    return config
