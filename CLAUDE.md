# Livly Feedback Pipeline

## How to run

Python venv: `.venv/bin/python3`

Load env vars from `.env` using `python-dotenv` (installed in venv):
```python
from dotenv import load_dotenv; load_dotenv()
```

### Export only (no scraping)
```
.venv/bin/python3 -c "
from dotenv import load_dotenv; load_dotenv()
import main, argparse
args = argparse.Namespace(scrapers=None, classify=False, export=True, sheets_id='1BBwdagVzBhKPPS8oMTTeWp3JQorgfq_fm-ya0WnkACM', sheet_url=None)
main.run(args)
"
```

### Full pipeline (scrape + classify + export)
```
.venv/bin/python3 -c "
from dotenv import load_dotenv; load_dotenv()
import main, argparse
args = argparse.Namespace(scrapers='appstore,google_play', classify=True, export=True, sheets_id='1BBwdagVzBhKPPS8oMTTeWp3JQorgfq_fm-ya0WnkACM', sheet_url=None)
main.run(args)
"
```

## Config

- Supabase project: `kwmakskyfrfnkydvpams` (FeedbackScraper, eu-west-3)
- Google Sheets ID: `1BBwdagVzBhKPPS8oMTTeWp3JQorgfq_fm-ya0WnkACM`
- All secrets are in `.env` — never commit this file
- GitHub Actions secrets/vars mirror `.env` for CI runs

## Architecture

- `main.py` — CLI entrypoint with `--scrapers`, `--classify`, `--export` flags
- `scrapers/` — App Store RSS, Google Play, Discord, Reddit scrapers
- `db/dedup.py` — SHA-256 content hash dedup on insert
- `classifier/classify.py` — Claude Haiku 4.5 classification via tool-use
- `outputs/sheets.py` — Google Sheets weekly export with Trends + Weekly tabs
- `outputs/slack.py` — Slack digest (disabled until SLACK_WEBHOOK_URL is set)

## Known issues

- Discord bot token not configured yet (daily workflow is manual-only)
- Reddit API credentials pending approval
- Supabase free tier can 502 under load — `db/retry.py` handles retries
