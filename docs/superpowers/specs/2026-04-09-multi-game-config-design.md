# Multi-Game Config Design

Make the feedback pipeline support multiple games via a `games.json` config file, starting with Livly Island (existing) and ポケコロ/Pokecolo (new).

## Constraints

- Livly must not be affected. Existing behavior, data, tables, and CI workflows must work unchanged.
- Each game gets its own Supabase tables (complete data isolation).
- Each game exports to its own Google Sheet.
- No new Python dependencies.

## Config: `games.json`

Root-level keys are game slugs used with `--game` CLI arg. The slug is also stored inside the config as `"slug"` for logging and scoping.

`appstore_countries` is intentionally omitted — derived from `country_to_region` keys at runtime (avoids drift).

```json
{
  "livly": {
    "slug": "livly",
    "display_name": "Livly Island",
    "game_description": "a mobile pet game by Cocone",
    "appstore_id": "1553045339",
    "google_play_id": "jp.cocone.livly",
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
    "slug": "pokecolo",
    "display_name": "ポケコロ",
    "game_description": "a mobile avatar dress-up game by Cocone",
    "appstore_id": "451684733",
    "google_play_id": "jp.cocone.pocketcolony",
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
- Load `games.json` from the repo root. Validate that the slug exists and all required keys are present (`display_name`, `google_play_id`, `appstore_id`, `country_to_region`, `tables`, `sheets_id`, `sheet_region_groups`). Fail fast with a clear error if invalid.
- `--sheets-id` CLI arg is kept for backward compat. Precedence: CLI arg overrides `game_config["sheets_id"]`. This ensures the existing CI workflow (`--sheets-id "${{ vars.GOOGLE_SHEETS_ID }}"`) works unchanged.
- Pass game config to scrapers. Scraper dispatch (lines 83-90) changes from `scraper_fn()` to per-scraper calls:
  - `appstore`: `scrape_appstore(app_id=config["appstore_id"], countries=list(config["country_to_region"].keys()), country_to_region=config["country_to_region"])`
  - `google_play`: `scrape_google_play(package_id=config["google_play_id"], regions=config["google_play_regions"], country_to_region=config["country_to_region"])`
  - `discord`, `reddit`: unchanged (no game-specific config yet)
- Use `config["tables"]["scrape_runs"]` for scrape run tracking at lines 94-98 AND the error handler at line 127 (both currently hardcode `"scrape_runs"`).
- Pass `config["tables"]["feedback_raw"]` to `deduplicate_and_insert`.
- Pass full game config to `classify_batch` and `export_to_sheets`.
- Slack digest section (lines 149-163): use `config["tables"]["feedback_classified"]` for the query table. Pass `game_config` to `build_digest_message`.

### `scrapers/appstore.py`

- Remove hardcoded `APP_ID = "1553045339"` and `COUNTRY_REGION_MAP`.
- `scrape_appstore()` gains parameters: `app_id: str`, `countries: list[str]`, `country_to_region: dict[str, str]`.
- Uses these instead of the old constants. Logic is identical.

### `scrapers/google_play.py`

- Remove hardcoded `PACKAGE_ID = "jp.cocone.livly"` and `COUNTRY_REGION_MAP`.
- `scrape_google_play()` gains parameters: `package_id: str`, `regions: list[list[str]]`, `country_to_region: dict[str, str]`.
- `_parse_review()` (line 13) also needs `package_id` — currently uses the module-level `PACKAGE_ID` constant to build `source_url` (line 26: `PLAY_STORE_URL.format(pkg=PACKAGE_ID, ...)`). Add `package_id` as a parameter to `_parse_review` and pass it from `scrape_google_play`.

### `db/dedup.py`

- `deduplicate_and_insert()` gains parameter: `table_name: str = "feedback_raw"`.
- All `.table("feedback_raw")` calls become `.table(table_name)`.

### `classifier/classify.py`

- `classify_batch()` gains parameter: `game_config: dict`.
- `SYSTEM_PROMPT` (line 83) is templated: `"You are classifying user feedback for {display_name}, {game_description}."` instead of hardcoded "Livly Island, a mobile pet game by Cocone".
- `CLASSIFICATION_TOOL["description"]` (line 28, currently `"Classify a piece of user feedback for Livly Island."`) is also templated per-game. Build the tool dict at call time, not module level.
- `_fetch_unclassified` uses `game_config["tables"]["unclassified_rpc"]` instead of hardcoded `"unclassified_feedback"`.
- Upsert uses `game_config["tables"]["feedback_classified"]` instead of hardcoded `"feedback_classified"`.

### `outputs/sheets.py`

- `export_to_sheets()` signature changes from `(supabase_client, spreadsheet_id)` to `(supabase_client, game_config)`.
- Reads `spreadsheet_id` from `game_config["sheets_id"]`. If empty, log a warning and skip export (guard against running pokecolo before sheet is set up).
- Uses `game_config["sheet_region_groups"]` instead of hardcoded `REGION_GROUPS`. Remove the `REGION_GROUPS` constant.
- `_fetch_all_classified` uses `game_config["tables"]["feedback_classified"]` instead of hardcoded `"feedback_classified"`.
- Tab reordering (lines 464-472) becomes dynamic: builds `["{group} Trends", "{group} Weekly", "{group} Stream"]` from `sheet_region_groups` keys.
- Legacy tab cleanup (lines 399-404) scoped to `game_config["slug"] == "livly"` only.

### `outputs/slack.py`

- `build_digest_message()` and `_build_fallback_digest()` gain a `game_config` parameter.
- `_build_stats_context()` gains `game_config` parameter. Region iteration (line 17, currently hardcoded `[("en", "EN"), ("jp", "JP")]`) derives from `game_config["sheet_region_groups"]`: iterate over group keys and their regions.
- Sonnet prompt (line 68) uses `game_config["display_name"]` and `game_config["game_description"]` instead of hardcoded "Livly Island (a mobile pet game)".
- Fallback digest header (line 92) uses `game_config["display_name"]` instead of "Livly Island".
- Fallback region iteration (line 94, currently hardcoded `[("en", ":gb:", "EN"), ("jp", ":jp:", "JP")]`) derives from `sheet_region_groups` keys with a simple flag mapping.

## Files NOT Changing

- `scrapers/base.py` — FeedbackItem, ScraperResult, content hash
- `db/client.py` — Supabase client singleton
- `db/retry.py` — retry logic
- `scrapers/discord_scraper.py` — not used by pokecolo
- `scrapers/reddit_scraper.py` — not used by pokecolo
- `.github/workflows/` — existing workflows pass no `--game`, default to livly

## Supabase Prerequisites (manual, before running pokecolo)

Create in Supabase SQL editor. Full DDL provided to prevent FK cross-references.

### Tables

```sql
-- pokecolo_scrape_runs: same schema as scrape_runs
CREATE TABLE pokecolo_scrape_runs (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    source text NOT NULL,
    region text,
    status text NOT NULL DEFAULT 'running',
    items_fetched int,
    items_new int,
    error_message text,
    started_at timestamptz DEFAULT now(),
    finished_at timestamptz
);

-- pokecolo_feedback_raw: same schema, FK references itself (not feedback_raw)
CREATE TABLE pokecolo_feedback_raw (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    content_hash text NOT NULL,
    source text NOT NULL,
    region text,
    external_id text NOT NULL,
    author text,
    content text NOT NULL,
    rating smallint,
    channel text,
    source_url text,
    posted_at timestamptz NOT NULL,
    scraped_at timestamptz DEFAULT now(),
    scrape_run_id uuid REFERENCES pokecolo_scrape_runs(id),
    superseded_by uuid REFERENCES pokecolo_feedback_raw(id),
    UNIQUE(content_hash)
);

-- pokecolo_feedback_classified: FK references pokecolo_feedback_raw (not feedback_raw)
CREATE TABLE pokecolo_feedback_classified (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    feedback_id uuid NOT NULL REFERENCES pokecolo_feedback_raw(id) UNIQUE,
    sentiment text,
    categories text[],
    severity text,
    language text,
    summary text,
    summary_jp text,
    key_quotes text[],
    model_used text,
    classified_at timestamptz DEFAULT now()
);
```

### RPC

```sql
CREATE OR REPLACE FUNCTION pokecolo_unclassified_feedback(batch_limit int DEFAULT 50)
RETURNS SETOF pokecolo_feedback_raw AS $$
    SELECT r.*
    FROM pokecolo_feedback_raw r
    LEFT JOIN pokecolo_feedback_classified c ON c.feedback_id = r.id
    WHERE c.feedback_id IS NULL
      AND r.superseded_by IS NULL
    LIMIT batch_limit;
$$ LANGUAGE sql STABLE;
```

## Usage

```bash
# Livly (unchanged default — existing CI keeps working)
python main.py --scrapers appstore,google_play --classify --export

# Pokecolo (explicit)
python main.py --game pokecolo --scrapers appstore,google_play --classify --export
```

## Testing Strategy

1. After code changes, run Livly pipeline (no `--game` flag) and verify identical behavior.
2. Create pokecolo Supabase tables with the DDL above, then run pokecolo scrape on a single region to verify data flows correctly.
3. Verify Livly tables have zero new rows from pokecolo run.
4. Verify pokecolo tables have correct FK references (no cross-table links).
