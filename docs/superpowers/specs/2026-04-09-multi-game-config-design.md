# Multi-Game Config Design

Make the feedback pipeline support multiple games via a `games.json` config file, starting with Livly Island (existing) and ポケコロ/Pokecolo (new).

## Constraints

- Livly must not be affected. Existing behavior, data, tables, and CI workflows must work unchanged.
- Each game gets its own Supabase tables (complete data isolation).
- Each game exports to its own Google Sheet.
- No new Python dependencies.

## Config: `games.json`

Root-level keys are game slugs used with `--game` CLI arg. The loader injects the slug from the key at load time — it is NOT stored inside the config object (avoids key/value drift).

`appstore_countries` is intentionally omitted — derived from `country_to_region` keys at runtime.

`categories` is per-game — a dress-up game and a pet game have different feedback taxonomies.

Each `sheet_region_groups` entry includes a `flag` emoji for Slack digests, keeping all region presentation config in one place.

```json
{
  "livly": {
    "display_name": "Livly Island",
    "game_description": "a mobile pet game by Cocone",
    "appstore_id": "1553045339",
    "google_play_id": "jp.cocone.livly",
    "google_play_regions": [["en", "us"], ["ja", "jp"], ["zh_TW", "tw"], ["zh_TW", "hk"]],
    "country_to_region": {"us": "en", "jp": "jp", "tw": "tw", "hk": "hk"},
    "categories": [
      "ux", "tutorial_onboarding", "gacha_monetization", "social",
      "bugs_performance", "content_request", "account_login",
      "art_aesthetics", "general_praise", "events", "localization"
    ],
    "tables": {
      "feedback_raw": "feedback_raw",
      "feedback_classified": "feedback_classified",
      "scrape_runs": "scrape_runs",
      "unclassified_rpc": "unclassified_feedback"
    },
    "sheets_id": "1BBwdagVzBhKPPS8oMTTeWp3JQorgfq_fm-ya0WnkACM",
    "sheet_region_groups": {
      "EN":   {"regions": ["en"], "summary_field": "summary", "include_region": false, "flag": ":gb:"},
      "ASIA": {"regions": ["jp", "tw", "hk"], "summary_field": "summary_jp", "include_region": true, "flag": ":jp:"}
    },
    "legacy_tabs_to_remove": ["JP Trends", "JP Weekly", "JP Stream", "Raw Data"],
    "slack_webhook_url": null
  },
  "pokecolo": {
    "display_name": "ポケコロ",
    "game_description": "a mobile avatar dress-up game by Cocone",
    "appstore_id": "451684733",
    "google_play_id": "jp.cocone.pocketcolony",
    "google_play_regions": [["ja", "jp"], ["en", "us"], ["zh_TW", "tw"], ["zh_TW", "hk"], ["en", "sg"], ["th", "th"]],
    "country_to_region": {"jp": "jp", "us": "en", "tw": "tw", "hk": "hk", "sg": "sg", "th": "th"},
    "categories": [
      "ux", "tutorial_onboarding", "gacha_monetization", "social",
      "bugs_performance", "content_request", "account_login",
      "art_aesthetics", "general_praise", "events", "localization"
    ],
    "tables": {
      "feedback_raw": "pokecolo_feedback_raw",
      "feedback_classified": "pokecolo_feedback_classified",
      "scrape_runs": "pokecolo_scrape_runs",
      "unclassified_rpc": "pokecolo_unclassified_feedback"
    },
    "sheets_id": null,
    "sheet_region_groups": {
      "JP": {"regions": ["jp"], "summary_field": "summary_jp", "include_region": false, "flag": ":jp:"},
      "EN": {"regions": ["en"], "summary_field": "summary", "include_region": false, "flag": ":gb:"},
      "TW": {"regions": ["tw"], "summary_field": "summary_jp", "include_region": false, "flag": ":tw:"},
      "HK": {"regions": ["hk"], "summary_field": "summary_jp", "include_region": false, "flag": ":hk:"},
      "SG": {"regions": ["sg"], "summary_field": "summary", "include_region": false, "flag": ":sg:"},
      "TH": {"regions": ["th"], "summary_field": "summary_jp", "include_region": false, "flag": ":th:"}
    },
    "legacy_tabs_to_remove": [],
    "slack_webhook_url": null
  }
}
```

## New file: `config.py`

A small config loader module (~40 lines). Responsibilities:

1. Load `games.json` from repo root.
2. Inject `slug` from the JSON key into each config dict (not stored in the file).
3. Validate required keys: `display_name`, `game_description`, `appstore_id`, `google_play_id`, `google_play_regions`, `country_to_region`, `categories`, `tables`, `sheets_id`, `sheet_region_groups`.
4. Validate `tables` sub-keys: `feedback_raw`, `feedback_classified`, `scrape_runs`, `unclassified_rpc`.
5. Cross-validate: every country in `google_play_regions` (second element of each pair) must exist in `country_to_region`. Fail fast if not.
6. Return the config dict for the requested slug, or fail with a clear error listing available slugs.

Called once from `main.py` at startup. All other modules receive the loaded config — they do not load it themselves.

## File Changes

### `main.py`

- Add `--game` argument, default `"livly"`.
- Call `config.py` loader to get validated game config. Slug is injected by the loader.
- **Startup table check**: after loading config and Supabase client, query one of the game's tables (e.g., `client.table(config["tables"]["scrape_runs"]).select("id").limit(1).execute()`). If it returns an error (404/relation does not exist), fail fast with: `"Table {name} does not exist. Run the DDL from docs/superpowers/specs/..."`. This avoids retry storms against missing tables.
- `--sheets-id` CLI arg is kept for backward compat. Precedence: CLI arg overrides `config["sheets_id"]`. This ensures the existing CI workflow (`--sheets-id "${{ vars.GOOGLE_SHEETS_ID }}"`) works unchanged.
- **Uniform scraper dispatch**: all scrapers receive `game_config` as a keyword argument. The `SCRAPER_MAP` dispatch stays generic:
  ```python
  for name in scraper_names:
      scraper_fn = SCRAPER_MAP.get(name)
      results = scraper_fn(game_config=config)
  ```
  Each scraper extracts what it needs from the config internally. Discord/Reddit accept the parameter but ignore it for now.
- Use `config["tables"]["scrape_runs"]` for scrape run tracking at lines 94-98 AND the error handler at line 127 (both currently hardcode `"scrape_runs"`).
- Pass `config["tables"]["feedback_raw"]` to `deduplicate_and_insert`.
- Pass full game config to `classify_batch` and `export_to_sheets`.
- Slack digest section (lines 149-163): use `config["tables"]["feedback_classified"]` for the query table. Use `config["slack_webhook_url"]` if set, else fall back to `SLACK_WEBHOOK_URL` env var. Pass `game_config` to `build_digest_message`.

### `scrapers/appstore.py`

- Remove hardcoded `APP_ID` and `COUNTRY_REGION_MAP`.
- `scrape_appstore(game_config)` extracts `app_id`, countries (from `country_to_region` keys), and `country_to_region` from the config dict.
- Logic is identical. Default behavior when called without config: not supported — config is always required.

### `scrapers/google_play.py`

- Remove hardcoded `PACKAGE_ID` and `COUNTRY_REGION_MAP`.
- `scrape_google_play(game_config)` extracts `package_id`, `regions`, and `country_to_region` from the config dict.
- `_parse_review()` (line 13) gains `package_id` parameter — currently uses the module-level `PACKAGE_ID` constant to build `source_url` (line 26). Pass it from `scrape_google_play`.
- Remove the `PLAY_STORE_URL` format string's dependency on the module constant.

### `scrapers/discord_scraper.py` and `scrapers/reddit_scraper.py`

- Add `game_config=None` parameter to their entry functions. Ignore it for now.
- Document as future work: Discord `TARGET_CHANNELS` and Reddit `SUBREDDIT_NAME` are still hardcoded for Livly. When a second game needs Discord/Reddit, these should move to config.

### `db/dedup.py`

- `deduplicate_and_insert()` gains parameter: `table_name: str = "feedback_raw"`.
- All `.table("feedback_raw")` calls become `.table(table_name)`.

### `classifier/classify.py`

- `classify_batch()` gains parameter: `game_config: dict`.
- `SYSTEM_PROMPT` (line 83) is templated with `game_config["display_name"]` and `game_config["game_description"]`.
- `CLASSIFICATION_TOOL` is rebuilt per-call (not module-level) with templated `description` using `game_config["display_name"]`. The old module-level `CLASSIFICATION_TOOL` constant is removed.
- `CATEGORIES` list (line 12) is removed. Read from `game_config["categories"]` instead. The tool schema's `categories` enum uses this list.
- `_fetch_unclassified` uses `game_config["tables"]["unclassified_rpc"]` instead of hardcoded `"unclassified_feedback"`.
- Upsert uses `game_config["tables"]["feedback_classified"]` instead of hardcoded `"feedback_classified"`.

### `outputs/sheets.py`

- `export_to_sheets()` signature changes from `(supabase_client, spreadsheet_id)` to `(supabase_client, game_config)`.
- Reads `spreadsheet_id` from `game_config["sheets_id"]`. If `None`, log a warning and return early (guard against running pokecolo before sheet is created).
- Uses `game_config["sheet_region_groups"]` instead of hardcoded `REGION_GROUPS`. Remove the `REGION_GROUPS` constant.
- `_fetch_all_classified` uses `game_config["tables"]["feedback_classified"]` instead of hardcoded `"feedback_classified"`.
- Category heatmap columns in `_build_trends_sections` (line 172) read from `game_config["categories"]` instead of the hardcoded `category_columns` list.
- Tab reordering (lines 464-472) becomes dynamic: builds `["{group} Trends", "{group} Weekly", "{group} Stream"]` from `sheet_region_groups` keys.
- Legacy tab cleanup uses `game_config["legacy_tabs_to_remove"]` list instead of hardcoded tab names with a `slug == "livly"` check.

### `outputs/slack.py`

- `build_digest_message()` and `_build_fallback_digest()` gain a `game_config` parameter.
- `_build_stats_context()` gains `game_config` parameter. Region iteration (line 17, currently hardcoded `[("en", "EN"), ("jp", "JP")]`) iterates over `game_config["sheet_region_groups"]` — for each group, uses the group's `regions` list.
- Sonnet prompt (line 68) uses `game_config["display_name"]` and `game_config["game_description"]`.
- Fallback digest header (line 92) uses `game_config["display_name"]`.
- Fallback region iteration (line 94) iterates over `sheet_region_groups`, using each group's `flag` emoji from config.

## Files NOT Changing

- `scrapers/base.py` — FeedbackItem, ScraperResult, content hash
- `db/client.py` — Supabase client singleton
- `db/retry.py` — retry logic
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

-- pokecolo_feedback_raw: FK references pokecolo tables only (not Livly tables)
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

## Adding a New Game (migration checklist)

1. Add a block to `games.json` with all required keys.
2. Run DDL to create 3 tables + 1 RPC in Supabase (copy from pokecolo DDL, rename prefixes, verify FK references point to the new tables).
3. Create a Google Sheet and set the ID in config.
4. Set a Slack webhook URL in config if desired.
5. Add a CI workflow step with `--game <slug>`.
6. If the game has Discord/Reddit channels, parameterize those scrapers (currently hardcoded for Livly — documented as future work).

No code changes required for steps 1-5.

## Testing Strategy

1. After code changes, run Livly pipeline (no `--game` flag) and verify identical behavior.
2. Create pokecolo Supabase tables with the DDL above, then run pokecolo scrape on a single region to verify data flows correctly.
3. Verify Livly tables have zero new rows from pokecolo run.
4. Verify pokecolo tables have correct FK references (no cross-table links).
5. Post-refactor: `grep -r '"feedback_raw"\|"feedback_classified"\|"scrape_runs"\|"unclassified_feedback"' *.py **/*.py` — should only appear in `config.py` validation and `games.json`. Any match elsewhere is a missed hardcoded reference.
