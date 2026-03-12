"""Google Sheets weekly export via gspread."""

import json
import os
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

SEVERITY_ORDER = {"critical": 0, "moderate": 1, "minor": 2}
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _get_sheets_client() -> gspread.Client:
    creds_json = os.environ["GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON"]
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)


def _build_weekly_rows(classified_rows: list[dict], region: str) -> list[list]:
    filtered = [
        r for r in classified_rows
        if r.get("feedback_raw", {}).get("region") == region
    ]

    rows = []
    for r in filtered:
        raw = r.get("feedback_raw", {})
        rows.append([
            raw.get("posted_at", ""),
            raw.get("source", ""),
            r.get("sentiment", ""),
            ", ".join(r.get("categories", [])),
            r.get("severity", ""),
            r.get("summary", ""),
            "; ".join(r.get("key_quotes", [])),
            raw.get("source_url", ""),
        ])

    rows.sort(key=lambda row: SEVERITY_ORDER.get(row[4], 99))
    return rows


def _build_trends_data(classified_rows: list[dict], region: str) -> dict:
    filtered = [
        r for r in classified_rows
        if r.get("feedback_raw", {}).get("region") == region
    ]

    sentiment_counter = Counter()
    category_counter = Counter()
    for r in filtered:
        sentiment_counter[r.get("sentiment", "unknown")] += 1
        for cat in r.get("categories", []):
            category_counter[cat] += 1

    return {
        "total": len(filtered),
        "sentiment_breakdown": dict(sentiment_counter),
        "top_categories": category_counter.most_common(10),
    }


HEADER_ROW = ["Date", "Source", "Sentiment", "Categories", "Severity", "Summary", "Key Quotes", "URL"]

SEVERITY_COLORS = {
    "critical": {"red": 1, "green": 0.8, "blue": 0.8},
    "moderate": {"red": 1, "green": 1, "blue": 0.8},
    "minor": {"red": 1, "green": 1, "blue": 1},
}


def _apply_severity_colors(ws, rows: list[list], start_row: int = 2):
    for i, row in enumerate(rows):
        severity = row[4] if len(row) > 4 else "minor"
        color = SEVERITY_COLORS.get(severity, SEVERITY_COLORS["minor"])
        row_num = start_row + i
        ws.format(f"A{row_num}:H{row_num}", {"backgroundColor": color})


def export_to_sheets(supabase_client, spreadsheet_id: str) -> None:
    gc = _get_sheets_client()
    spreadsheet = gc.open_by_key(spreadsheet_id)

    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    weekly_classified = (
        supabase_client.table("feedback_classified")
        .select("*, feedback_raw(*)")
        .gte("classified_at", week_ago)
        .execute()
    )
    weekly_rows = weekly_classified.data or []

    four_weeks_ago = (datetime.now(timezone.utc) - timedelta(weeks=4)).isoformat()
    trends_classified = (
        supabase_client.table("feedback_classified")
        .select("*, feedback_raw(*)")
        .gte("classified_at", four_weeks_ago)
        .execute()
    )
    trends_rows = trends_classified.data or []

    for region, tab_name in [("en", "EN Weekly"), ("jp", "JP Weekly")]:
        built_rows = _build_weekly_rows(weekly_rows, region)
        try:
            ws = spreadsheet.worksheet(tab_name)
        except gspread.WorksheetNotFound:
            ws = spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=10)
        ws.clear()
        ws.append_row(HEADER_ROW)
        if built_rows:
            ws.append_rows(built_rows)
            _apply_severity_colors(ws, built_rows)

    for region, tab_name in [("en", "EN Trends"), ("jp", "JP Trends")]:
        trends = _build_trends_data(trends_rows, region)
        try:
            ws = spreadsheet.worksheet(tab_name)
        except gspread.WorksheetNotFound:
            ws = spreadsheet.add_worksheet(title=tab_name, rows=100, cols=5)
        ws.clear()
        ws.append_row(["Metric", "Value"])
        ws.append_row(["Period", "Last 4 weeks"])
        ws.append_row(["Total items", trends["total"]])
        for sentiment, count in trends["sentiment_breakdown"].items():
            ws.append_row([f"Sentiment: {sentiment}", count])
        ws.append_row([])
        ws.append_row(["Top Categories", "Count"])
        for cat, count in trends["top_categories"]:
            ws.append_row([cat, count])

    twelve_weeks_ago = (datetime.now(timezone.utc) - timedelta(weeks=12)).isoformat()
    raw_classified = (
        supabase_client.table("feedback_classified")
        .select("*, feedback_raw(*)")
        .gte("classified_at", twelve_weeks_ago)
        .execute()
    )
    all_rows = raw_classified.data or []
    try:
        ws = spreadsheet.worksheet("Raw Data")
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title="Raw Data", rows=5000, cols=12)
    ws.clear()
    raw_header = ["Date", "Source", "Region", "Sentiment", "Categories", "Severity",
                   "Language", "Summary EN", "Summary JP", "Key Quotes", "URL"]
    ws.append_row(raw_header)
    raw_rows = []
    for r in all_rows:
        raw = r.get("feedback_raw", {})
        raw_rows.append([
            raw.get("posted_at", ""),
            raw.get("source", ""),
            raw.get("region", ""),
            r.get("sentiment", ""),
            ", ".join(r.get("categories", [])),
            r.get("severity", ""),
            r.get("language", ""),
            r.get("summary", ""),
            r.get("summary_jp", ""),
            "; ".join(r.get("key_quotes", [])),
            raw.get("source_url", ""),
        ])
    if raw_rows:
        ws.append_rows(raw_rows)

    logger.info("Exported %d weekly + %d raw items to Google Sheets", len(weekly_rows), len(all_rows))
