"""Google Sheets weekly export via gspread."""

import json
import os
import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone
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


def _clear_sheet(spreadsheet, ws):
    """Clear both values and formatting from a worksheet."""
    ws.clear()
    spreadsheet.batch_update({
        "requests": [{
            "repeatCell": {
                "range": {"sheetId": ws.id},
                "cell": {"userEnteredFormat": {}},
                "fields": "userEnteredFormat",
            }
        }]
    })


def _build_stream_rows(classified_rows: list[dict], regions: list[str],
                       summary_field: str = "summary", include_region: bool = True) -> list[list]:
    """Build a full per-region feed of all classified items, newest first."""
    filtered = [
        r for r in classified_rows
        if r.get("feedback_raw", {}).get("region") in regions
    ]

    rows = []
    for r in filtered:
        raw = r.get("feedback_raw", {})
        if include_region:
            rows.append([
                raw.get("posted_at", ""),
                raw.get("source", ""),
                raw.get("region", ""),
                r.get("sentiment", ""),
                ", ".join(r.get("categories", [])),
                r.get("severity", ""),
                r.get("language", ""),
                r.get(summary_field, ""),
                "",  # Translation (filled with formula post-write)
                "; ".join(r.get("key_quotes", [])),
                raw.get("source_url", ""),
            ])
        else:
            rows.append([
                raw.get("posted_at", ""),
                raw.get("source", ""),
                r.get("sentiment", ""),
                ", ".join(r.get("categories", [])),
                r.get("severity", ""),
                r.get(summary_field, ""),
                "; ".join(r.get("key_quotes", [])),
                raw.get("source_url", ""),
            ])

    rows.sort(key=lambda row: row[0] or "", reverse=True)
    return rows


def _parse_posted_at(r: dict) -> datetime | None:
    posted = r.get("feedback_raw", {}).get("posted_at")
    if not posted:
        return None
    return datetime.fromisoformat(posted.replace("Z", "+00:00"))


def _month_label(dt: datetime) -> str:
    """Return 'Mon'YY' label for a datetime, e.g. \"Mar'26\"."""
    return dt.strftime("%b'%y")


def _build_trends_sections(classified_rows: list[dict], regions: list[str],
                           categories: list[str], since_year: int = 2025) -> tuple[list[list], int]:
    """Build Sentiment Timeline + Category Heat Map for a region. Returns (rows, timeline_row_count)."""
    cutoff = datetime(since_year, 1, 1, tzinfo=timezone.utc)

    # Filter by region and date, group by month
    by_month: dict[str, list[dict]] = defaultdict(list)
    for r in classified_rows:
        if r.get("feedback_raw", {}).get("region") not in regions:
            continue
        dt = _parse_posted_at(r)
        if dt is None or dt < cutoff:
            continue
        by_month[dt.strftime("%Y-%m")].append(r)

    if not by_month:
        return [], 0

    month_keys = sorted(by_month.keys())  # oldest first
    month_labels = []
    for mk in month_keys:
        dt = datetime.strptime(mk, "%Y-%m").replace(tzinfo=timezone.utc)
        month_labels.append(_month_label(dt))

    # --- Section 1: Sentiment Timeline (newest first) ---
    rows = [["SENTIMENT OVER TIME", "", "", "", "", "", "", ""]]
    rows.append(["Month", "Items", "Positive", "Negative", "Mixed", "%Negative", "#1 Issue", "Critical"])

    for mk in month_keys:
        items = by_month[mk]
        total = len(items)
        sentiments = Counter(r.get("sentiment", "unknown") for r in items)
        positive = sentiments.get("positive", 0)
        negative = sentiments.get("negative", 0)
        mixed = sentiments.get("mixed", 0)
        pct_neg = round(negative / total * 100) if total else 0

        # #1 issue: category with most negative+mixed
        issue_counter: Counter = Counter()
        critical_count = 0
        for r in items:
            if r.get("sentiment") in ("negative", "mixed"):
                for cat in r.get("categories", []):
                    issue_counter[cat] += 1
            if r.get("severity") == "critical":
                critical_count += 1
        top_issue = issue_counter.most_common(1)[0][0] if issue_counter else ""

        dt = datetime.strptime(mk, "%Y-%m").replace(tzinfo=timezone.utc)
        rows.append([_month_label(dt), total, positive, negative, mixed,
                      f"{pct_neg}%", top_issue, critical_count])

    # --- Section 2: Category Heat Map side-by-side (starting at column J) ---
    category_columns = categories

    HEATMAP_OFFSET = 9  # column J (0-indexed)

    # Count negative+mixed per category per month
    cat_month: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for mk in month_keys:
        for r in by_month[mk]:
            if r.get("sentiment") not in ("negative", "mixed"):
                continue
            for cat in r.get("categories", []):
                cat_month[mk][cat] += 1

    # Pad existing rows to include heatmap columns, add heatmap headers
    # Row 0: section labels
    rows[0].extend([""] * (HEATMAP_OFFSET - len(rows[0])) + ["COMPLAINTS BY CATEGORY"] + [""] * (len(category_columns) - 1))
    # Row 1: headers
    rows[1].extend([""] * (HEATMAP_OFFSET - len(rows[1])) + ["Month"] + category_columns)

    # Data rows (starting at row index 2)
    for i, mk in enumerate(month_keys):
        row_idx = i + 2
        dt = datetime.strptime(mk, "%Y-%m").replace(tzinfo=timezone.utc)
        heatmap_cells = [_month_label(dt)] + [cat_month[mk].get(cat, 0) for cat in category_columns]

        if row_idx < len(rows):
            # Pad and extend existing sentiment row
            rows[row_idx].extend([""] * (HEATMAP_OFFSET - len(rows[row_idx])) + heatmap_cells)
        else:
            # Shouldn't happen since both use the same month_keys, but just in case
            rows.append([""] * HEATMAP_OFFSET + heatmap_cells)

    return rows, HEATMAP_OFFSET, len(category_columns)


def _col_letter(index: int) -> str:
    """Convert 0-based column index to spreadsheet letter (0=A, 25=Z, 26=AA)."""
    result = ""
    while True:
        result = chr(ord("A") + index % 26) + result
        index = index // 26 - 1
        if index < 0:
            break
    return result


def _apply_trends_colors(ws, rows: list[list], heatmap_offset: int, num_categories: int):
    """Apply formatting to both Trends sections (side by side)."""
    formats = []
    header_fmt = {
        "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95},
        "textFormat": {"bold": True},
        "borders": {
            "top": BORDER_STYLE, "bottom": BORDER_STYLE,
            "left": BORDER_STYLE, "right": BORDER_STYLE,
        },
    }
    section_label_fmt = {"textFormat": {"bold": True, "fontSize": 11}}

    # Section 1: Sentiment Timeline (columns A-H)
    formats.append({"range": "A1:H1", "format": section_label_fmt})
    formats.append({"range": "A2:H2", "format": header_fmt})

    # %Negative column (F) — red intensity
    for i in range(2, len(rows)):
        row = rows[i]
        row_num = i + 1
        pct_str = row[5] if len(row) > 5 else "0%"
        pct = int(pct_str.replace("%", "")) if isinstance(pct_str, str) and "%" in pct_str else 0
        intensity = min(pct / 50, 1.0)
        color = {"red": 1, "green": 1 - intensity * 0.4, "blue": 1 - intensity * 0.4}
        formats.append({"range": f"F{row_num}:F{row_num}", "format": {"backgroundColor": color}})

    # Section 2: Category Heat Map (starting at heatmap_offset)
    hm_start = _col_letter(heatmap_offset)
    hm_end = _col_letter(heatmap_offset + num_categories)
    formats.append({"range": f"{hm_start}1:{hm_end}1", "format": section_label_fmt})
    formats.append({"range": f"{hm_start}2:{hm_end}2", "format": header_fmt})

    # Heat map cells — red intensity
    max_val = 0
    for row in rows[2:]:
        for v in row[heatmap_offset + 1:]:
            if isinstance(v, int) and v > max_val:
                max_val = v

    if max_val > 0:
        for i in range(2, len(rows)):
            row = rows[i]
            row_num = i + 1
            for j in range(heatmap_offset + 1, len(row)):
                v = row[j]
                if not isinstance(v, int):
                    continue
                intensity = v / max_val
                col = _col_letter(j)
                color = {"red": 1, "green": 1 - intensity * 0.4, "blue": 1 - intensity * 0.4}
                formats.append({"range": f"{col}{row_num}:{col}{row_num}", "format": {"backgroundColor": color}})

    if formats:
        ws.batch_format(formats)


EN_STREAM_HEADER = ["Date", "Source", "Sentiment", "Categories", "Severity", "Summary", "Key Quotes", "URL"]
ASIA_STREAM_HEADER = ["Date", "Source", "Region", "Sentiment", "Categories", "Severity", "Language", "Summary", "Translation", "Key Quotes", "URL"]

SEVERITY_COLORS = {
    "critical": {"red": 1, "green": 0.8, "blue": 0.8},
    "moderate": {"red": 1, "green": 1, "blue": 0.8},
    "minor": {"red": 1, "green": 1, "blue": 1},
}
POSITIVE_COLOR = {"red": 0.85, "green": 1, "blue": 0.85}


def _apply_stream_colors(ws, rows: list[list], sentiment_col: int, severity_col: int,
                         end_col: str, start_row: int = 2):
    """Apply severity colors to negative/mixed/neutral rows, green to positive rows."""
    formats = []
    for i, row in enumerate(rows):
        sentiment = row[sentiment_col] if len(row) > sentiment_col else ""
        severity = row[severity_col] if len(row) > severity_col else "minor"
        row_num = start_row + i
        if sentiment == "positive":
            color = POSITIVE_COLOR
        else:
            color = SEVERITY_COLORS.get(severity, SEVERITY_COLORS["minor"])
        formats.append({"range": f"A{row_num}:{end_col}{row_num}", "format": {"backgroundColor": color}})
    if formats:
        ws.batch_format(formats)


def _iso_week_label(dt: datetime) -> str:
    """Return 'YYYY-Www' label for a datetime."""
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _build_summary_blocks(classified_rows: list[dict], regions: list[str], summary_field: str = "summary") -> list[list]:
    """Build summary blocks grouped by posted_at week, newest first."""

    # Group by ISO week based on posted_at
    by_week: dict[str, list[dict]] = defaultdict(list)
    for r in classified_rows:
        if r.get("feedback_raw", {}).get("region") not in regions:
            continue
        dt = _parse_posted_at(r)
        if dt is None:
            continue
        by_week[_iso_week_label(dt)].append(r)

    if not by_week:
        return []

    rows = []
    for week_label in sorted(by_week, reverse=True):
        items = by_week[week_label]

        sentiments = Counter(r.get("sentiment", "unknown") for r in items)
        split_parts = [f"{sentiments.get(s, 0)} {s}" for s in ["positive", "negative", "neutral", "mixed"] if sentiments.get(s)]
        split_str = " · ".join(split_parts)

        count = len(items)
        rows.append([week_label, f"{count} {'item' if count == 1 else 'items'}", split_str])

        complaints = [r for r in items if r.get("sentiment") in ("negative", "mixed")]
        complaints.sort(key=lambda r: SEVERITY_ORDER.get(r.get("severity", ""), 99))
        if complaints:
            rows.append(["Complaints", "", ""])
            for r in complaints[:3]:
                cats = ", ".join(r.get("categories", []))
                rows.append([r.get("severity", ""), cats, r.get(summary_field, "")])

        praises = [r for r in items if r.get("sentiment") == "positive"]
        if praises:
            rows.append(["Praises", "", ""])
            for r in praises[:3]:
                cats = ", ".join(r.get("categories", []))
                rows.append(["", cats, r.get(summary_field, "")])

        rows.append([])

    return rows


BORDER_STYLE = {"style": "SOLID", "colorStyle": {"rgbColor": {"red": 0.7, "green": 0.7, "blue": 0.7}}}
WEEK_HEADER_FORMAT = {
    "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95},
    "textFormat": {"bold": True},
    "borders": {
        "top": BORDER_STYLE,
        "bottom": BORDER_STYLE,
        "left": BORDER_STYLE,
        "right": BORDER_STYLE,
    },
}


def _apply_summary_colors(ws, rows: list[list]):
    """Apply severity colors to complaint rows, green to praise rows, borders to week headers."""
    formats = []
    for i, row in enumerate(rows):
        row_num = i + 1
        if not row:
            continue
        # Week header row (e.g. "2026-W09")
        if row[0].startswith("20") and "-W" in row[0]:
            formats.append({"range": f"A{row_num}:C{row_num}", "format": WEEK_HEADER_FORMAT})
        elif row[0] in SEVERITY_COLORS:
            formats.append({"range": f"A{row_num}:C{row_num}", "format": {"backgroundColor": SEVERITY_COLORS[row[0]]}})
        elif row[0] == "" and row[1] != "" and row[1] != "":
            # Praise rows
            formats.append({"range": f"A{row_num}:C{row_num}", "format": {"backgroundColor": {"red": 0.85, "green": 1, "blue": 0.85}}})
    if formats:
        ws.batch_format(formats)


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
