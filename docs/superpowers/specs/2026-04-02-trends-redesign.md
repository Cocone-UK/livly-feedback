# Trends Tab Redesign

## Problem

The current Trends tabs show a flat category table with "This week / Last week / Delta" columns based on calendar dates. When historical data is bulk-imported, these columns are all zeros because no reviews fall in the last 14 days. The view is also not suitable for executive presentation.

## Context

- Audience: Vice Chairman presentation to secure Livly fork development for Cocone UK team
- Data: ~2 years of classified feedback (2022-W09 through 2026-W13), EN and JP regions
- Tabs: EN Trends and JP Trends (names unchanged)

## Design

Two sections on each Trends tab, monthly granularity, last 6 months.

### Section 1: Sentiment Timeline (top)

One row per month, newest first. Tells the headline story: is the product getting better or worse?

| Column | Description |
|--------|-------------|
| Month | Format: `Mar'26` |
| Items | Total feedback count that month |
| Positive | Count of positive sentiment |
| Negative | Count of negative sentiment |
| Mixed | Count of mixed sentiment |
| %Negative | `negative / total`, formatted as percentage |
| #1 Issue | Category with most negative+mixed items that month |
| Critical | Count of critical-severity items |

Formatting:
- Header row: bold, bordered, light gray background (consistent with Weekly tabs)
- `%Negative` cells: red intensity scaling (higher % = darker red)
- Section label "SENTIMENT OVER TIME" in row 1, bold

### Section 2: Category Heat Map (below, separated by one empty row)

Rows = categories (sorted by total descending), columns = months (oldest to newest, left to right).

| Element | Description |
|---------|-------------|
| Row per category | Only categories that appear in the 6-month window |
| Cell values | Count of negative + mixed items only |
| Column order | Oldest month left, newest right (trend reads naturally) |
| Sorting | Categories sorted by total count across all months, descending |

Formatting:
- Section label "COMPLAINTS BY CATEGORY" in first row, bold
- Header row (month names): bold, bordered, light gray background
- Data cells: red intensity scaling (0 = white, high value = dark red)

### Data source

Uses `posted_at` from `feedback_raw` for month grouping (not `classified_at`). The existing `all_rows` fetch (currently 12 weeks for Raw Data) will be expanded to 6 months so both Raw Data and Trends use the same query. This means Raw Data also grows from 12 to 26 weeks — acceptable since it's a presentation asset.

### Changes to existing code

- Replace `_build_trends_rows()` in `outputs/sheets.py` with new function that builds both sections
- Expand the raw data fetch from 12 weeks to 6 months to cover the full trends window
- Use `_clear_sheet()` instead of value-only update to reset formatting between runs
- Remove the Google Sheets table-preservation logic for Trends (no longer needed since we clear and rebuild)

### What stays the same

- Tab names: EN Trends, JP Trends
- All other tabs unchanged (EN/JP Weekly, EN/JP Stream, Raw Data)
- No new dependencies or API calls
