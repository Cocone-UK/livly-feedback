# Livly Island Feedback System

Automated feedback collection and AI classification for Livly Island (Cocone).

## What it does

- Scrapes user feedback from iOS App Store, Google Play, Discord, and Reddit
- Classifies each item (sentiment, category, severity, language) using Claude AI
- Exports weekly reports to Google Sheets
- Posts weekly digests to Slack

## Setup

### 1. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Create Supabase project

Create a new project at [supabase.com](https://supabase.com) and run `db/migration.sql` in the SQL Editor.

### 3. Set environment variables

```bash
export SUPABASE_URL="https://xxx.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="your-key"
export ANTHROPIC_API_KEY="your-key"
export DISCORD_BOT_TOKEN="your-token"
export REDDIT_CLIENT_ID="your-id"
export REDDIT_CLIENT_SECRET="your-secret"
export REDDIT_USERNAME="your-username"
export REDDIT_PASSWORD="your-password"
export GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON='{"type":"service_account",...}'
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
export GOOGLE_SHEETS_ID="your-spreadsheet-id"
export GOOGLE_SHEETS_URL="https://docs.google.com/spreadsheets/d/your-id"
```

### 4. Run

```bash
# Scrape Discord only + classify
python main.py --scrapers discord --classify

# Scrape everything + classify + export
python main.py --scrapers all --classify --export --sheets-id YOUR_SHEET_ID --sheet-url YOUR_SHEET_URL

# Scrape specific sources
python main.py --scrapers appstore,google_play --classify
```

## GitHub Actions

- **Daily** (09:00 UTC): Discord scrape + classification
- **Weekly** (Monday 09:00 UTC): All sources + classification + Sheets export + Slack digest

Configure secrets in GitHub repo settings. Also set repository variables `GOOGLE_SHEETS_ID` and `GOOGLE_SHEETS_URL` (Settings > Variables > Actions). See `.github/workflows/` for details.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```
