# Multi-Game Config Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the feedback pipeline support multiple games via `games.json`, starting with Livly Island (existing) and Pokecolo (new), with complete data isolation.

**Architecture:** A `games.json` config file defines per-game settings (app IDs, regions, table names, categories, sheet config). A `config.py` loader validates and injects the slug. All modules receive `game_config` dict instead of using hardcoded constants. `--game` CLI arg defaults to `"livly"` for backward compat.

**Tech Stack:** Python 3.12, Supabase, Anthropic API, gspread, httpx, google-play-scraper, pytest

**Spec:** `docs/superpowers/specs/2026-04-09-multi-game-config-design.md`

**Note:** `test_classify.py` and `test_sheets.py` import functions (`classify_feedback`, `_build_weekly_rows`, `_build_trends_data`) that do not exist in the current source — these tests are pre-broken from a prior refactor. They will be rewritten as part of this plan.

---

### Task 1: Create `games.json` and `config.py` with tests

**Files:**
- Create: `games.json`
- Create: `config.py`
- Create: `tests/test_config.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Create `games.json`**

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
    "display_name": "\u30dd\u30b1\u30b3\u30ed",
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

- [ ] **Step 2: Write failing tests for `config.py`**

Create `tests/test_config.py`:

```python
import pytest
from config import load_game_config


def test_load_livly_config():
    config = load_game_config("livly")
    assert config["slug"] == "livly"
    assert config["display_name"] == "Livly Island"
    assert config["appstore_id"] == "1553045339"
    assert config["tables"]["feedback_raw"] == "feedback_raw"


def test_load_pokecolo_config():
    config = load_game_config("pokecolo")
    assert config["slug"] == "pokecolo"
    assert config["appstore_id"] == "451684733"
    assert config["tables"]["feedback_raw"] == "pokecolo_feedback_raw"


def test_slug_injected_from_key():
    config = load_game_config("livly")
    assert "slug" in config
    assert config["slug"] == "livly"


def test_unknown_slug_raises():
    with pytest.raises(ValueError, match="Unknown game 'nonexistent'"):
        load_game_config("nonexistent")


def test_country_cross_validation(tmp_path, monkeypatch):
    """A country in google_play_regions but not in country_to_region should fail."""
    import json
    bad_config = {
        "bad_game": {
            "display_name": "Bad",
            "game_description": "test",
            "appstore_id": "1",
            "google_play_id": "com.test",
            "google_play_regions": [["en", "xx"]],
            "country_to_region": {"us": "en"},
            "categories": ["ux"],
            "tables": {
                "feedback_raw": "t1",
                "feedback_classified": "t2",
                "scrape_runs": "t3",
                "unclassified_rpc": "t4",
            },
            "sheets_id": null,
            "sheet_region_groups": {},
            "legacy_tabs_to_remove": [],
            "slack_webhook_url": null,
        }
    }
    config_file = tmp_path / "games.json"
    config_file.write_text(json.dumps(bad_config))
    monkeypatch.setattr("config.CONFIG_PATH", str(config_file))

    with pytest.raises(ValueError, match="country 'xx'.*missing from country_to_region"):
        load_game_config("bad_game")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'config'`

- [ ] **Step 4: Implement `config.py`**

Create `config.py`:

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/test_config.py -v`
Expected: All 5 tests PASS

- [ ] **Step 6: Add `livly_config` fixture to `tests/conftest.py`**

Add to bottom of `tests/conftest.py`:

```python
@pytest.fixture
def livly_config():
    """Livly game config for testing."""
    return {
        "slug": "livly",
        "display_name": "Livly Island",
        "game_description": "a mobile pet game by Cocone",
        "appstore_id": "1553045339",
        "google_play_id": "jp.cocone.livly",
        "google_play_regions": [["en", "us"], ["ja", "jp"], ["zh_TW", "tw"], ["zh_TW", "hk"]],
        "country_to_region": {"us": "en", "jp": "jp", "tw": "tw", "hk": "hk"},
        "categories": [
            "ux", "tutorial_onboarding", "gacha_monetization", "social",
            "bugs_performance", "content_request", "account_login",
            "art_aesthetics", "general_praise", "events", "localization",
        ],
        "tables": {
            "feedback_raw": "feedback_raw",
            "feedback_classified": "feedback_classified",
            "scrape_runs": "scrape_runs",
            "unclassified_rpc": "unclassified_feedback",
        },
        "sheets_id": "test-sheet-id",
        "sheet_region_groups": {
            "EN": {"regions": ["en"], "summary_field": "summary", "include_region": False, "flag": ":gb:"},
            "ASIA": {"regions": ["jp", "tw", "hk"], "summary_field": "summary_jp", "include_region": True, "flag": ":jp:"},
        },
        "legacy_tabs_to_remove": ["JP Trends", "JP Weekly", "JP Stream", "Raw Data"],
        "slack_webhook_url": None,
    }
```

- [ ] **Step 7: Commit**

```bash
git add games.json config.py tests/test_config.py tests/conftest.py
git commit -m "feat: add games.json config and config.py loader with validation"
```

---

### Task 2: Update App Store scraper

**Files:**
- Modify: `scrapers/appstore.py:8-9` (remove constants), `:32-38` (new signature)
- Modify: `tests/test_appstore.py`

- [ ] **Step 1: Update `scrapers/appstore.py`**

Remove lines 8-9 (`APP_ID` and `COUNTRY_REGION_MAP` constants).

Replace `scrape_appstore` function (lines 32-69) with:

```python
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
```

- [ ] **Step 2: Update `tests/test_appstore.py`**

Replace the two tests that call `scrape_appstore`:

```python
LIVLY_CONFIG = {
    "appstore_id": "1553045339",
    "country_to_region": {"us": "en"},
}


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
```

- [ ] **Step 3: Run tests**

Run: `.venv/bin/python3 -m pytest tests/test_appstore.py -v`
Expected: All 4 tests PASS

- [ ] **Step 4: Commit**

```bash
git add scrapers/appstore.py tests/test_appstore.py
git commit -m "refactor: appstore scraper reads config from game_config dict"
```

---

### Task 3: Update Google Play scraper

**Files:**
- Modify: `scrapers/google_play.py:8-9` (remove constants), `:13-28` (parse_review), `:31-79` (scrape fn)
- Modify: `tests/test_google_play.py`

- [ ] **Step 1: Update `scrapers/google_play.py`**

Remove lines 8-9 (`PACKAGE_ID` and `COUNTRY_REGION_MAP` constants).

Update `_parse_review` (line 13) to accept `package_id`:

```python
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
```

Replace `scrape_google_play` (lines 31-79) with:

```python
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
```

- [ ] **Step 2: Update `tests/test_google_play.py`**

```python
LIVLY_CONFIG = {
    "google_play_id": "jp.cocone.livly",
    "google_play_regions": [["en", "us"]],
    "country_to_region": {"us": "en"},
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
```

- [ ] **Step 3: Run tests**

Run: `.venv/bin/python3 -m pytest tests/test_google_play.py -v`
Expected: All 4 tests PASS

- [ ] **Step 4: Commit**

```bash
git add scrapers/google_play.py tests/test_google_play.py
git commit -m "refactor: google play scraper reads config from game_config dict"
```

---

### Task 4: Update Discord and Reddit scrapers

**Files:**
- Modify: `scrapers/discord_scraper.py:92`
- Modify: `scrapers/reddit_scraper.py:61`

- [ ] **Step 1: Add `game_config` param to Discord scraper**

In `scrapers/discord_scraper.py`, change line 92:

```python
def scrape_discord(since: Optional[datetime] = None, game_config: dict | None = None) -> list[ScraperResult]:
    return asyncio.run(_run_discord_scrape(since))
```

- [ ] **Step 2: Add `game_config` param to Reddit scraper**

In `scrapers/reddit_scraper.py`, change line 61:

```python
def scrape_reddit(
    since: Optional[datetime] = None,
    post_limit: int = 100,
    comments_per_post: int = 20,
    game_config: dict | None = None,
) -> list[ScraperResult]:
```

- [ ] **Step 3: Run existing tests to verify no breakage**

Run: `.venv/bin/python3 -m pytest tests/test_discord_scraper.py tests/test_reddit_scraper.py -v`
Expected: All existing tests PASS (param is optional, ignored)

- [ ] **Step 4: Commit**

```bash
git add scrapers/discord_scraper.py scrapers/reddit_scraper.py
git commit -m "refactor: add game_config param to discord/reddit scrapers (unused for now)"
```

---

### Task 5: Update `db/dedup.py`

**Files:**
- Modify: `db/dedup.py:10` (signature), `:41,46,67,72,100,119` (table references)
- Test: `tests/test_dedup.py` (no changes needed — default param preserves existing calls)

- [ ] **Step 1: Update `deduplicate_and_insert` signature and table references**

In `db/dedup.py`, change the function signature (line 10):

```python
def deduplicate_and_insert(
    client: Client,
    items: list[FeedbackItem],
    run_id: str,
    table_name: str = "feedback_raw",
) -> dict:
```

Then replace every `.table("feedback_raw")` with `.table(table_name)`. There are 4 occurrences:
- Line 41: `.table("feedback_raw")` in hash check
- Line 67: `.table("feedback_raw")` in external_id check
- Line 100: `.table("feedback_raw").insert(c)` in batch insert
- Line 119: `.table("feedback_raw")` in supersede update

- [ ] **Step 2: Run existing tests (unchanged — default param)**

Run: `.venv/bin/python3 -m pytest tests/test_dedup.py -v`
Expected: All 3 tests PASS (they don't pass `table_name`, so default `"feedback_raw"` is used)

- [ ] **Step 3: Commit**

```bash
git add db/dedup.py
git commit -m "refactor: dedup accepts configurable table_name param"
```

---

### Task 6: Update classifier

**Files:**
- Modify: `classifier/classify.py` (remove constants, parameterize with game_config)
- Rewrite: `tests/test_classify.py` (currently broken — imports nonexistent `classify_feedback`)

- [ ] **Step 1: Update `classifier/classify.py`**

Remove the module-level `CATEGORIES` list (lines 12-24), `CLASSIFICATION_TOOL` dict (lines 26-71), and `SYSTEM_PROMPT` string (lines 83-89).

Add helper functions that build these from config:

```python
def _build_system_prompt(game_config: dict) -> str:
    return (
        f"You are classifying user feedback for {game_config['display_name']}, "
        f"{game_config['game_description']}.\n"
        "Analyze the feedback and classify it using the classify_feedback tool.\n\n"
        "Severity guidelines:\n"
        "- critical: User churned, threatening to quit, data loss, account locked out\n"
        "- moderate: Frustrated but still playing, repeated complaint, functional issue\n"
        "- minor: Suggestion, mild annoyance, cosmetic issue"
    )


def _build_classification_tool(game_config: dict) -> dict:
    categories = game_config["categories"]
    return {
        "name": "classify_feedback",
        "description": f"Classify a piece of user feedback for {game_config['display_name']}.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sentiment": {
                    "type": "string",
                    "enum": ["positive", "negative", "neutral", "mixed"],
                    "description": "Overall sentiment of the feedback.",
                },
                "categories": {
                    "type": "array",
                    "items": {"type": "string", "enum": categories},
                    "description": "One or more category tags.",
                },
                "severity": {
                    "type": "string",
                    "enum": ["critical", "moderate", "minor"],
                    "description": "Critical = user churned/threatening to quit/data loss. Moderate = frustrated but playing. Minor = suggestion/cosmetic.",
                },
                "language": {
                    "type": "string",
                    "enum": ["en", "ja", "zh", "other"],
                    "description": "Detected language of the feedback.",
                },
                "summary_en": {
                    "type": "string",
                    "description": "One-line summary in English.",
                },
                "summary_jp": {
                    "type": "string",
                    "description": "One-line summary in Japanese (for HQ).",
                },
                "key_quotes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Notable phrases extracted from the feedback.",
                },
            },
            "required": [
                "sentiment", "categories", "severity", "language",
                "summary_en", "summary_jp", "key_quotes",
            ],
        },
    }
```

Update `_fetch_unclassified` to accept the RPC name:

```python
def _fetch_unclassified(supabase_client, batch_size: int, rpc_name: str) -> list[dict]:
    """Fetch unclassified, non-superseded feedback via Postgres RPC."""
    from db.retry import with_retry

    resp = with_retry(
        lambda: supabase_client.rpc(
            rpc_name, {"batch_limit": batch_size}
        ).execute(),
        "fetch unclassified feedback",
    )
    return resp.data or []
```

Update `classify_batch` to accept `game_config`:

```python
def classify_batch(supabase_client, game_config: dict) -> dict:
    """Classify all unclassified feedback via the Anthropic Message Batches API."""
    from db.retry import with_retry

    tables = game_config["tables"]
    rpc_name = tables["unclassified_rpc"]
    classified_table = tables["feedback_classified"]

    all_unclassified = _fetch_unclassified(supabase_client, 10000, rpc_name)
    if not all_unclassified:
        logger.info("No unclassified items found")
        return {"classified": 0, "failed": 0}

    logger.info("Submitting %d items to Anthropic Batches API", len(all_unclassified))

    system_prompt = _build_system_prompt(game_config)
    classification_tool = _build_classification_tool(game_config)

    requests = []
    for row in all_unclassified:
        rating_str = f"{row.get('rating')}/5" if row.get("rating") is not None else "N/A"
        user_message = f"Feedback from {row['source']} (rating: {rating_str}):\n\n{row['content']}"

        requests.append(Request(
            custom_id=str(row["id"]),
            params=MessageCreateParamsNonStreaming(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                system=system_prompt,
                tools=[classification_tool],
                tool_choice={"type": "tool", "name": "classify_feedback"},
                messages=[{"role": "user", "content": user_message}],
            ),
        ))

    ai_client = anthropic.Anthropic()
    message_batch = ai_client.messages.batches.create(requests=requests)
    logger.info("Batch %s created (%d requests), polling...", message_batch.id, len(requests))

    while message_batch.processing_status != "ended":
        time.sleep(POLL_INTERVAL)
        message_batch = ai_client.messages.batches.retrieve(message_batch.id)
        counts = message_batch.request_counts
        logger.info("Batch %s: %d processing, %d succeeded, %d errored",
                     message_batch.id, counts.processing, counts.succeeded, counts.errored)

    logger.info("Batch %s complete: %d succeeded, %d errored, %d expired",
                 message_batch.id, message_batch.request_counts.succeeded,
                 message_batch.request_counts.errored, message_batch.request_counts.expired)

    classified_count = 0
    failed_count = 0

    for result in ai_client.messages.batches.results(message_batch.id):
        if result.result.type != "succeeded":
            logger.error("Batch item %s: %s", result.custom_id, result.result.type)
            failed_count += 1
            continue

        message = result.result.message
        classification = None
        for block in message.content:
            if block.type == "tool_use":
                classification = block.input
                break

        if classification is None:
            logger.error("No tool_use in batch result for %s", result.custom_id)
            failed_count += 1
            continue

        insert_data = {
            "feedback_id": result.custom_id,
            "sentiment": classification["sentiment"],
            "categories": _to_pg_array(classification.get("categories", [])),
            "severity": classification["severity"],
            "language": classification["language"],
            "summary": classification["summary_en"],
            "summary_jp": classification["summary_jp"],
            "key_quotes": _to_pg_array(classification.get("key_quotes", [])),
            "model_used": message.model,
        }
        with_retry(
            lambda d=insert_data: supabase_client.table(classified_table).upsert(d).execute(),
            "upsert classification",
        )
        classified_count += 1

    return {"classified": classified_count, "failed": failed_count}
```

- [ ] **Step 2: Rewrite `tests/test_classify.py`**

```python
from unittest.mock import MagicMock, patch
from classifier.classify import _build_system_prompt, _build_classification_tool

LIVLY_CONFIG = {
    "slug": "livly",
    "display_name": "Livly Island",
    "game_description": "a mobile pet game by Cocone",
    "categories": [
        "ux", "tutorial_onboarding", "gacha_monetization", "social",
        "bugs_performance", "content_request", "account_login",
        "art_aesthetics", "general_praise", "events", "localization",
    ],
    "tables": {
        "feedback_raw": "feedback_raw",
        "feedback_classified": "feedback_classified",
        "scrape_runs": "scrape_runs",
        "unclassified_rpc": "unclassified_feedback",
    },
}


def test_system_prompt_includes_game_name():
    prompt = _build_system_prompt(LIVLY_CONFIG)
    assert "Livly Island" in prompt
    assert "a mobile pet game by Cocone" in prompt


def test_system_prompt_uses_config_name():
    config = {**LIVLY_CONFIG, "display_name": "TestGame", "game_description": "a test game"}
    prompt = _build_system_prompt(config)
    assert "TestGame" in prompt
    assert "Livly Island" not in prompt


def test_classification_tool_has_required_fields():
    tool = _build_classification_tool(LIVLY_CONFIG)
    props = tool["input_schema"]["properties"]
    assert "sentiment" in props
    assert "categories" in props
    assert "severity" in props
    assert "language" in props
    assert "summary_en" in props
    assert "summary_jp" in props
    assert "key_quotes" in props


def test_classification_tool_uses_config_categories():
    tool = _build_classification_tool(LIVLY_CONFIG)
    cat_enum = tool["input_schema"]["properties"]["categories"]["items"]["enum"]
    assert cat_enum == LIVLY_CONFIG["categories"]


def test_classification_tool_description_uses_game_name():
    tool = _build_classification_tool(LIVLY_CONFIG)
    assert "Livly Island" in tool["description"]
```

- [ ] **Step 3: Run tests**

Run: `.venv/bin/python3 -m pytest tests/test_classify.py -v`
Expected: All 5 tests PASS

- [ ] **Step 4: Commit**

```bash
git add classifier/classify.py tests/test_classify.py
git commit -m "refactor: classifier builds prompt and tool schema from game_config"
```

---

### Task 7: Update Sheets export

**Files:**
- Modify: `outputs/sheets.py` (remove `REGION_GROUPS`, parameterize with game_config)
- Rewrite: `tests/test_sheets.py` (currently broken — imports nonexistent functions)

- [ ] **Step 1: Update `outputs/sheets.py`**

Remove the `REGION_GROUPS` constant (lines 14-17).

Update `_fetch_all_classified` to accept table name (line 31):

```python
def _fetch_all_classified(supabase_client, since: str, table_name: str = "feedback_classified") -> list[dict]:
    """Fetch all classified feedback since a date, paginating past the 1000-row limit."""
    all_rows = []
    offset = 0
    page_size = 1000
    while True:
        resp = (
            supabase_client.table(table_name)
            .select("*, feedback_raw(*)")
            .gte("classified_at", since)
            .order("id")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        rows = resp.data or []
        all_rows.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size
    return all_rows
```

Update `_build_trends_sections` to accept `categories` param (line 120). Replace the hardcoded `category_columns` list (line 172) with the param:

```python
def _build_trends_sections(classified_rows: list[dict], regions: list[str],
                           categories: list[str], since_year: int = 2025) -> tuple[list[list], int]:
```

And inside the function, replace line 172-176:

```python
    category_columns = categories
```

Update `export_to_sheets` to accept `game_config` (line 392):

```python
def export_to_sheets(supabase_client, game_config: dict) -> None:
    sheets_id = game_config.get("sheets_id")
    if not sheets_id:
        logger.warning("No sheets_id configured for %s, skipping export", game_config["slug"])
        return

    gc = _get_sheets_client()
    spreadsheet = gc.open_by_key(sheets_id)

    tables = game_config["tables"]
    region_groups = game_config["sheet_region_groups"]
    categories = game_config["categories"]

    all_rows = _fetch_all_classified(supabase_client, "2025-01-01T00:00:00+00:00", tables["feedback_classified"])
    logger.info("Fetched %d classified items for 2025+2026", len(all_rows))

    # Remove legacy tabs
    for legacy in game_config.get("legacy_tabs_to_remove", []):
        try:
            spreadsheet.del_worksheet(spreadsheet.worksheet(legacy))
        except gspread.WorksheetNotFound:
            pass

    # --- Trends tabs ---
    for group_name, config in region_groups.items():
        tab_name = f"{group_name} Trends"
        try:
            spreadsheet.del_worksheet(spreadsheet.worksheet(tab_name))
        except gspread.WorksheetNotFound:
            pass
        ws = spreadsheet.add_worksheet(title=tab_name, rows=200, cols=20)
        trends_data, hm_offset, num_cats = _build_trends_sections(
            all_rows, config["regions"], categories, since_year=2025,
        )
        if trends_data:
            ws.append_rows(trends_data)
            _apply_trends_colors(ws, trends_data, hm_offset, num_cats)

    # --- Weekly tabs ---
    for group_name, config in region_groups.items():
        tab_name = f"{group_name} Weekly"
        summary_rows = _build_summary_blocks(all_rows, config["regions"], config["summary_field"])
        try:
            ws = spreadsheet.worksheet(tab_name)
        except gspread.WorksheetNotFound:
            ws = spreadsheet.add_worksheet(title=tab_name, rows=2000, cols=5)
        _clear_sheet(spreadsheet, ws)
        if summary_rows:
            ws.append_rows(summary_rows)
            _apply_summary_colors(ws, summary_rows)

    # --- Stream tabs ---
    for group_name, config in region_groups.items():
        tab_name = f"{group_name} Stream"
        include_region = config["include_region"]
        built_rows = _build_stream_rows(
            all_rows, config["regions"], config["summary_field"], include_region,
        )

        if include_region:
            header = ASIA_STREAM_HEADER
            sentiment_col, severity_col, end_col = 3, 5, "K"
        else:
            header = EN_STREAM_HEADER
            sentiment_col, severity_col, end_col = 2, 4, "H"

        try:
            ws = spreadsheet.worksheet(tab_name)
        except gspread.WorksheetNotFound:
            ws = spreadsheet.add_worksheet(title=tab_name, rows=max(len(built_rows) + 10, 1000), cols=12)
        _clear_sheet(spreadsheet, ws)
        ws.append_row(header)
        if built_rows:
            ws.append_rows(built_rows)
            _apply_stream_colors(ws, built_rows, sentiment_col, severity_col, end_col)

            if include_region:
                formulas = [[f'=GOOGLETRANSLATE(H{row_num}, "ja", "en")']
                            for row_num in range(2, len(built_rows) + 2)]
                ws.update(f"I2:I{len(built_rows) + 1}", formulas,
                          value_input_option="USER_ENTERED")

    # Dynamic tab reordering
    tab_types = ["Trends", "Weekly", "Stream"]
    desired_order = [f"{g} {t}" for t in tab_types for g in region_groups.keys()]
    existing = {ws.title: ws for ws in spreadsheet.worksheets()}
    ordered = [existing[name] for name in desired_order if name in existing]
    for ws in spreadsheet.worksheets():
        if ws.title not in desired_order:
            ordered.append(ws)
    spreadsheet.reorder_worksheets(ordered)

    logger.info("Exported %d items to Google Sheets", len(all_rows))
```

- [ ] **Step 2: Rewrite `tests/test_sheets.py`**

```python
from unittest.mock import MagicMock, patch
from outputs.sheets import _build_stream_rows, _build_summary_blocks


def _make_classified_row(sentiment="negative", categories=None,
                         severity="moderate", region="en", source="discord"):
    if categories is None:
        categories = ["bugs_performance"]
    return {
        "feedback_raw": {
            "posted_at": "2026-03-10T12:00:00+00:00",
            "source": source,
            "region": region,
            "source_url": "https://example.com",
        },
        "sentiment": sentiment,
        "categories": categories,
        "severity": severity,
        "language": "en",
        "summary": "User reports bug",
        "summary_jp": "\u30e6\u30fc\u30b6\u30fc\u304c\u30d0\u30b0\u3092\u5831\u544a",
        "key_quotes": ["broke my layout"],
    }


def test_build_stream_rows_filters_by_region():
    rows = [
        _make_classified_row(region="en"),
        _make_classified_row(region="jp"),
        _make_classified_row(region="en"),
    ]
    en_rows = _build_stream_rows(rows, regions=["en"])
    assert len(en_rows) == 2


def test_build_summary_blocks_groups_by_week():
    rows = [
        _make_classified_row(sentiment="negative", severity="critical"),
        _make_classified_row(sentiment="positive"),
    ]
    blocks = _build_summary_blocks(rows, regions=["en"])
    assert len(blocks) > 0
    # First row should be a week header
    assert blocks[0][0].startswith("20") and "-W" in blocks[0][0]
```

- [ ] **Step 3: Run tests**

Run: `.venv/bin/python3 -m pytest tests/test_sheets.py -v`
Expected: All 2 tests PASS

- [ ] **Step 4: Commit**

```bash
git add outputs/sheets.py tests/test_sheets.py
git commit -m "refactor: sheets export reads config from game_config dict"
```

---

### Task 8: Update Slack digest

**Files:**
- Modify: `outputs/slack.py` (parameterize with game_config)
- Modify: `tests/test_slack.py`

- [ ] **Step 1: Update `outputs/slack.py`**

Update `_build_stats_context` (line 14):

```python
def _build_stats_context(classified_rows: list[dict], game_config: dict) -> str:
    sections = []
    region_groups = game_config["sheet_region_groups"]

    for group_name, group_config in region_groups.items():
        group_regions = group_config["regions"]
        filtered = [
            r for r in classified_rows
            if r.get("feedback_raw", {}).get("region") in group_regions
        ]

        if not filtered:
            sections.append(f"{group_name}: No data this week")
            continue

        total = len(filtered)
        sentiment_counter = Counter(r.get("sentiment") for r in filtered)
        category_counter = Counter()
        for r in filtered:
            for cat in r.get("categories", []):
                category_counter[cat] += 1

        critical_items = [r for r in filtered if r.get("severity") == "critical"]

        section = f"{group_name} ({total} items):\n"
        section += f"  Sentiment: {dict(sentiment_counter)}\n"
        section += f"  Top categories: {category_counter.most_common(5)}\n"
        section += f"  Critical items: {len(critical_items)}\n"

        if critical_items:
            section += "  Critical details:\n"
            for item in critical_items[:5]:
                section += f"    - {item.get('summary', 'N/A')}\n"

        section += "  Sample feedback summaries:\n"
        for item in filtered[:20]:
            section += f"    - [{item.get('sentiment')}] {item.get('summary', 'N/A')}\n"

        sections.append(section)

    return "\n".join(sections)
```

Update `build_digest_message` (line 55):

```python
def build_digest_message(classified_rows: list[dict], sheet_url: str, game_config: dict) -> str:
    now = datetime.now(timezone.utc)
    week_str = now.strftime("%b %d, %Y")
    display_name = game_config["display_name"]
    game_desc = game_config["game_description"]

    stats_context = _build_stats_context(classified_rows, game_config)

    try:
        client = anthropic.Anthropic(max_retries=3)

        region_groups = game_config["sheet_region_groups"]
        region_instructions = "\n".join(
            f"- {name} Summary section with {cfg['flag']} flag: item count, top 3 issues with counts, "
            "sentiment percentages, critical items count with brief description, any notable trends"
            for name, cfg in region_groups.items()
        )

        response = client.messages.create(
            model="claude-sonnet-4-6-20250514",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": f"""Summarize this week's user feedback for {display_name} ({game_desc}) into a Slack digest.

Data for week of {week_str}:

{stats_context}

Format as a Slack message with:
- Header with week date
{region_instructions}
- Keep it concise but insightful — highlight what the team should pay attention to
- Use Slack markdown (*bold*, bullet points with \u2022)
- End with :link: <{sheet_url}|Full report>

Output ONLY the Slack message text, nothing else.""",
            }],
        )
        return response.content[0].text
    except Exception as e:
        logger.error("Sonnet digest generation failed, using fallback: %s", e)
        return _build_fallback_digest(classified_rows, sheet_url, week_str, game_config)
```

Update `_build_fallback_digest` (line 91):

```python
def _build_fallback_digest(classified_rows: list[dict], sheet_url: str,
                           week_str: str, game_config: dict) -> str:
    display_name = game_config["display_name"]
    region_groups = game_config["sheet_region_groups"]

    sections = [f"*{display_name} Feedback \u2014 Week of {week_str}*\n"]

    for group_name, group_config in region_groups.items():
        flag = group_config["flag"]
        group_regions = group_config["regions"]
        filtered = [r for r in classified_rows if r.get("feedback_raw", {}).get("region") in group_regions]

        if not filtered:
            sections.append(f"{flag} *{group_name} Summary:* No data this week\n")
            continue

        total = len(filtered)
        category_counter = Counter()
        for r in filtered:
            for cat in r.get("categories", []):
                category_counter[cat] += 1

        top_3 = ", ".join(f"{c} ({n})" for c, n in category_counter.most_common(3))
        critical = sum(1 for r in filtered if r.get("severity") == "critical")

        lines = [f"{flag} *{group_name} Summary ({total} items):*", f"\u2022 Top issues: {top_3}"]
        if critical:
            lines.append(f"\u2022 :red_circle: {critical} critical items")
        sections.append("\n".join(lines) + "\n")

    sections.append(f":link: <{sheet_url}|Full report>")
    return "\n".join(sections)
```

- [ ] **Step 2: Update `tests/test_slack.py`**

Add config fixture at top, update every test call to pass `game_config`:

```python
from unittest.mock import patch, MagicMock
from outputs.slack import build_digest_message, _build_fallback_digest, _build_stats_context, post_slack_digest

LIVLY_CONFIG = {
    "slug": "livly",
    "display_name": "Livly Island",
    "game_description": "a mobile pet game by Cocone",
    "sheet_region_groups": {
        "EN": {"regions": ["en"], "summary_field": "summary", "include_region": False, "flag": ":gb:"},
        "ASIA": {"regions": ["jp", "tw", "hk"], "summary_field": "summary_jp", "include_region": True, "flag": ":jp:"},
    },
}


def _make_classified_rows():
    base = {
        "feedback_raw": {
            "posted_at": "2026-03-10T12:00:00+00:00",
            "source": "discord",
            "region": "en",
        },
        "sentiment": "negative",
        "categories": ["bugs_performance"],
        "severity": "moderate",
        "summary": "Bug report",
        "summary_jp": "\u30d0\u30b0\u5831\u544a",
    }
    return [
        {**base},
        {**base, "sentiment": "positive", "categories": ["general_praise"], "severity": "minor"},
        {**base, "severity": "critical"},
        {
            **base,
            "feedback_raw": {**base["feedback_raw"], "region": "jp"},
            "categories": ["events"],
            "sentiment": "positive",
        },
    ]


def test_build_stats_context_includes_both_regions():
    rows = _make_classified_rows()
    ctx = _build_stats_context(rows, LIVLY_CONFIG)
    assert "EN (3 items)" in ctx
    assert "ASIA (1 items)" in ctx


def test_build_stats_context_shows_critical_details():
    rows = _make_classified_rows()
    ctx = _build_stats_context(rows, LIVLY_CONFIG)
    assert "Critical items: 1" in ctx


def test_fallback_digest_contains_both_regions():
    rows = _make_classified_rows()
    msg = _build_fallback_digest(rows, sheet_url="https://sheets.example.com",
                                 week_str="Mar 10, 2026", game_config=LIVLY_CONFIG)
    assert "EN Summary" in msg
    assert "ASIA Summary" in msg
    assert "critical" in msg.lower()
    assert "Livly Island" in msg


@patch("outputs.slack.anthropic.Anthropic")
def test_build_digest_message_calls_sonnet(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="*Livly Island Feedback \u2014 Week of Mar 10, 2026*\nEN Summary")]
    mock_client.messages.create.return_value = mock_response

    rows = _make_classified_rows()
    msg = build_digest_message(rows, sheet_url="https://sheets.example.com", game_config=LIVLY_CONFIG)

    mock_client.messages.create.assert_called_once()
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert "sonnet" in call_kwargs["model"]
    assert "EN Summary" in msg


@patch("outputs.slack.anthropic.Anthropic")
def test_build_digest_message_falls_back_on_error(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.side_effect = Exception("API down")

    rows = _make_classified_rows()
    msg = build_digest_message(rows, sheet_url="https://sheets.example.com", game_config=LIVLY_CONFIG)

    assert "Livly Island Feedback" in msg


@patch("outputs.slack.httpx.post")
def test_post_slack_digest_sends_webhook(mock_post):
    mock_post.return_value = MagicMock(status_code=200)
    post_slack_digest("Test message", webhook_url="https://hooks.slack.com/test")
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert "text" in call_args[1].get("json", {}) or "text" in call_args.kwargs.get("json", {})
```

- [ ] **Step 3: Run tests**

Run: `.venv/bin/python3 -m pytest tests/test_slack.py -v`
Expected: All 6 tests PASS

- [ ] **Step 4: Commit**

```bash
git add outputs/slack.py tests/test_slack.py
git commit -m "refactor: slack digest uses game_config for regions, name, and flags"
```

---

### Task 9: Update `main.py` (wire everything together)

**Files:**
- Modify: `main.py` (add --game, load config, uniform dispatch, table check)
- Modify: `tests/test_main.py`

- [ ] **Step 1: Rewrite `main.py`**

```python
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
```

- [ ] **Step 2: Update `tests/test_main.py`**

```python
from unittest.mock import patch, MagicMock
from main import run, parse_args


def test_parse_args_defaults():
    args = parse_args(["--scrapers", "all"])
    assert args.game == "livly"
    assert args.classify is False
    assert args.export is False


def test_parse_args_game_flag():
    args = parse_args(["--game", "pokecolo", "--scrapers", "appstore"])
    assert args.game == "pokecolo"
    assert args.scrapers == "appstore"


def test_parse_args_scrapers_all():
    args = parse_args(["--scrapers", "all"])
    assert args.scrapers == "all"


def test_parse_args_scrapers_discord():
    args = parse_args(["--scrapers", "discord"])
    assert args.scrapers == "discord"


def test_parse_args_classify_flag():
    args = parse_args(["--scrapers", "all", "--classify"])
    assert args.classify is True


def test_parse_args_export_flag():
    args = parse_args(["--scrapers", "all", "--export"])
    assert args.export is True


def test_parse_args_sheets_id_override():
    args = parse_args(["--scrapers", "all", "--sheets-id", "CUSTOM_ID"])
    assert args.sheets_id == "CUSTOM_ID"
```

- [ ] **Step 3: Run all tests**

Run: `.venv/bin/python3 -m pytest tests/test_main.py -v`
Expected: All 7 tests PASS

- [ ] **Step 4: Run full test suite**

Run: `.venv/bin/python3 -m pytest tests/ -v`
Expected: All tests PASS across all files

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: main.py wires game_config through entire pipeline with --game flag"
```

---

### Task 10: Create pokecolo Google Sheet and Supabase tables

**Files:**
- Modify: `games.json` (set pokecolo sheets_id)

- [ ] **Step 1: Create pokecolo Google Sheet programmatically**

Run this one-off script to create the sheet:

```bash
.venv/bin/python3 -c "
from dotenv import load_dotenv; load_dotenv()
import json, os, gspread
from google.oauth2.service_account import Credentials

creds = Credentials.from_service_account_info(
    json.loads(os.environ['GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON']),
    scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
)
gc = gspread.authorize(creds)
sh = gc.create('Pokecolo Feedback')
print(f'Created sheet: {sh.id}')
print(f'URL: {sh.url}')
"
```

- [ ] **Step 2: Update `games.json` with the new sheet ID**

Set `pokecolo.sheets_id` to the ID printed in step 1.

- [ ] **Step 3: Create pokecolo Supabase tables**

Run the DDL from the spec in Supabase SQL editor. The full SQL is in `docs/superpowers/specs/2026-04-09-multi-game-config-design.md` under "Supabase Prerequisites".

- [ ] **Step 4: Commit**

```bash
git add games.json
git commit -m "feat: add pokecolo Google Sheet ID to config"
```

---

### Task 11: Post-refactor verification

- [ ] **Step 1: Grep for hardcoded table names**

Run: `grep -rn '"feedback_raw"\|"feedback_classified"\|"scrape_runs"\|"unclassified_feedback"' *.py scrapers/*.py db/*.py classifier/*.py outputs/*.py`

Expected: matches only in `config.py` (validation strings) and `db/dedup.py` (default parameter value). Any other match is a missed hardcoded reference — fix it.

- [ ] **Step 2: Run full test suite**

Run: `.venv/bin/python3 -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 3: Smoke test Livly pipeline (dry run)**

Run the Livly pipeline to verify it works identically to before:

```bash
.venv/bin/python3 -c "
from dotenv import load_dotenv; load_dotenv()
from config import load_game_config
config = load_game_config('livly')
print(f'Game: {config[\"display_name\"]}')
print(f'Tables: {config[\"tables\"]}')
print(f'Regions: {list(config[\"country_to_region\"].keys())}')
print('Config loaded successfully')
"
```

- [ ] **Step 4: Smoke test pokecolo config**

```bash
.venv/bin/python3 -c "
from dotenv import load_dotenv; load_dotenv()
from config import load_game_config
config = load_game_config('pokecolo')
print(f'Game: {config[\"display_name\"]}')
print(f'Tables: {config[\"tables\"]}')
print(f'Regions: {list(config[\"country_to_region\"].keys())}')
print(f'Sheets: {config[\"sheets_id\"]}')
print('Config loaded successfully')
"
```

- [ ] **Step 5: Final commit**

If any fixes were needed:

```bash
git add -A
git commit -m "fix: post-refactor cleanup"
```
