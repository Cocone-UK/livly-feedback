# Multi-Game Config Design

Make the feedback pipeline support multiple games via a `games.json` config file, starting with Livly Island (existing) and ポケコロ/Pokecolo (new).

## Constraints

- Livly must not be affected. Existing behavior, data, tables, and CI workflows must work unchanged.
- Each game gets its own Supabase tables (complete data isolation).
- Each game exports to its own Google Sheet.
- No new Python dependencies.

## Config: `games.json`

Root-level keys are game slugs used with `--game` CLI arg.

```json
{
  "livly": {
    "display_name": "Livly Island",
    "game_description": "a mobile pet game by Cocone",
    "appstore_id": "1553045339",
    "google_play_id": "jp.cocone.livly",
    "appstore_countries": ["us", "jp", "tw", "hk"],
    "google_play_regions": [["en", "us"], ["ja", "jp"], ["zh_TW", "tw"], ["zh_TW", "hk"]],
    "country_to_region": {"us": "en", "jp": "jp", "tw": "tw", "hk": "hk"},
    "tables": {
      "feedback_raw": "feedback_raw",
      "feedback_classified": "feedback_classified",
      "scrape_runs": "scrape_runs",
      "unclassified_rpc": "unclassified_feedback"
    },
    "sheets_id": "1BBwdagVzBhKPPS8oMTTeWp3JQorgfq_fm-ya0WnkACM",
    "sheet_region_groups": {
      "EN":   {"regions": ["en"], "summary_field": "summary", "include_region": false},
      "ASIA": {"regions": ["jp", "tw", "hk"], "summary_field": "summary_jp", "include_region": true}
    }
  },
  "pokecolo": {
    "display_name": "ポケコロ",
    "game_description": "a mobile avatar dress-up game by Cocone",
    "appstore_id": "451684733",
    "google_play_id": "jp.cocone.pocketcolony",
    "appstore_countries": ["jp", "us", "tw", "hk", "sg", "th"],
    "google_play_regions": [["ja", "jp"], ["en", "us"], ["zh_TW", "tw"], ["zh_TW", "hk"], ["en", "sg"], ["th", "th"]],
    "country_to_region": {"jp": "jp", "us": "en", "tw": "tw", "hk": "hk", "sg": "sg", "th": "th"},
    "tables": {
      "feedback_raw": "pokecolo_feedback_raw",
      "feedback_classified": "pokecolo_feedback_classified",
      "scrape_runs": "pokecolo_scrape_runs",
      "unclassified_rpc": "pokecolo_unclassified_feedback"
    },
    "sheets_id": "",
    "sheet_region_groups": {
      "JP": {"regions": ["jp"], "summary_field": "summary_jp", "include_region": false},
      "EN": {"regions": ["en"], "summary_field": "summary", "include_region": false},
      "TW": {"regions": ["tw"], "summary_field": "summary_jp", "include_region": false},
      "HK": {"regions": ["hk"], "summary_field": "summary_jp", "include_region": false},
      "SG": {"regions": ["sg"], "summary_field": "summary", "include_region": false},
      "TH": {"regions": ["th"], "summary_field": "summary_jp", "include_region": false}
    }
  }
}
```

## File Changes

### `main.py`

- Add `--game` argument, default `"livly"`.
- Load `games.json` from the repo root, look up the game config by slug.
- Pass game config to scrapers, dedup, classifier, and export.
- Use `config["tables"]["scrape_runs"]` for scrape run tracking (currently hardcoded `"scrape_runs"`).
- Pass `config["tables"]["feedback_raw"]` to `deduplicate_and_insert`.
- Pass full game config to `classify_batch` and `export_to_sheets`.
- Slack digest section (lines 149-163) uses `config["tables"]["feedback_classified"]` instead of hardcoded `"feedback_classified"` for the query.

### `scrapers/appstore.py`

- Remove hardcoded `APP_ID = "1553045339"` and `COUNTRY_REGION_MAP`.
- `scrape_appstore()` gains parameters: `app_id: str`, `countries: list[str]`, `country_to_region: dict[str, str]`.
- Uses these instead of the old constants. Logic is identical.

### `scrapers/google_play.py`

- Remove hardcoded `PACKAGE_ID = "jp.cocone.livly"` and `COUNTRY_REGION_MAP`.
- `scrape_google_play()` gains parameters: `package_id: str`, `regions: list[list[str]]`, `country_to_region: dict[str, str]`.
- Uses these instead of the old constants. Logic is identical.

### `db/dedup.py`

- `deduplicate_and_insert()` gains parameter: `table_name: str = "feedback_raw"`.
- All `.table("feedback_raw")` calls become `.table(table_name)`.

### `classifier/classify.py`

- `classify_batch()` gains parameter: `game_config: dict`.
- `SYSTEM_PROMPT` is templated with `game_config["display_name"]` and `game_config["game_description"]` instead of hardcoded "Livly Island".
- `_fetch_unclassified` uses `game_config["tables"]["unclassified_rpc"]` instead of hardcoded `"unclassified_feedback"`.
- Upsert uses `game_config["tables"]["feedback_classified"]` instead of hardcoded `"feedback_classified"`.

### `outputs/sheets.py`

- `export_to_sheets()` signature changes from `(supabase_client, spreadsheet_id)` to `(supabase_client, game_config)`.
- Reads `spreadsheet_id` from `game_config["sheets_id"]`.
- Uses `game_config["sheet_region_groups"]` instead of hardcoded `REGION_GROUPS`.
- `_fetch_all_classified` uses `game_config["tables"]["feedback_classified"]` instead of hardcoded `"feedback_classified"`.
- Remove the hardcoded `REGION_GROUPS` constant.
- Tab reordering at end of export (currently hardcoded to `["EN Trends", "ASIA Trends", ...]`) becomes dynamic: builds order from `sheet_region_groups` keys.
- Legacy tab cleanup (lines 400-404, removes old "JP Trends" etc.) is harmless for pokecolo (try/except catches missing tabs), but should be scoped to livly only or removed.

## Files NOT Changing

- `scrapers/base.py` — FeedbackItem, ScraperResult, content hash
- `db/client.py` — Supabase client singleton
- `db/retry.py` — retry logic
- `scrapers/discord_scraper.py` — not used by pokecolo
- `scrapers/reddit_scraper.py` — not used by pokecolo
- `outputs/slack.py` — unchanged
- `.github/workflows/` — existing workflows pass no `--game`, default to livly

## Supabase Prerequisites (manual, before running pokecolo)

Create in Supabase SQL editor:

1. `pokecolo_feedback_raw` — same schema as `feedback_raw`
2. `pokecolo_feedback_classified` — same schema as `feedback_classified`
3. `pokecolo_scrape_runs` — same schema as `scrape_runs`
4. `pokecolo_unclassified_feedback` RPC — same logic as `unclassified_feedback`, pointing at pokecolo tables

## Usage

```bash
# Livly (unchanged default)
python main.py --scrapers appstore,google_play --classify --export

# Pokecolo (explicit)
python main.py --game pokecolo --scrapers appstore,google_play --classify --export
```

## Testing Strategy

1. After code changes, run Livly pipeline (no `--game` flag) and verify identical behavior.
2. Create pokecolo Supabase tables, then run pokecolo scrape on a single region to verify data flows correctly.
3. Verify Livly tables have zero new rows from pokecolo run.
