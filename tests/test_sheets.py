from unittest.mock import MagicMock, patch
from outputs.sheets import _build_weekly_rows, _build_trends_data


def _make_classified_row(sentiment="negative", categories=["bugs_performance"],
                         severity="moderate", region="en", source="discord"):
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
        "summary_jp": "ユーザーがバグを報告",
        "key_quotes": ["broke my layout"],
    }


def test_build_weekly_rows_filters_by_region():
    rows = [
        _make_classified_row(region="en"),
        _make_classified_row(region="jp"),
        _make_classified_row(region="en"),
    ]
    en_rows = _build_weekly_rows(rows, region="en")
    assert len(en_rows) == 2


def test_build_weekly_rows_sorts_by_severity():
    rows = [
        _make_classified_row(severity="minor"),
        _make_classified_row(severity="critical"),
        _make_classified_row(severity="moderate"),
    ]
    result = _build_weekly_rows(rows, region="en")
    severities = [r[4] for r in result]  # severity column
    assert severities == ["critical", "moderate", "minor"]


def test_build_trends_data():
    rows = [
        _make_classified_row(sentiment="negative", categories=["bugs_performance"]),
        _make_classified_row(sentiment="negative", categories=["bugs_performance"]),
        _make_classified_row(sentiment="positive", categories=["general_praise"]),
    ]
    trends = _build_trends_data(rows, region="en")
    assert trends["total"] == 3
    assert trends["sentiment_breakdown"]["negative"] == 2
    assert trends["top_categories"][0][0] == "bugs_performance"
