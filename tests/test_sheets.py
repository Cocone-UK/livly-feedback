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
