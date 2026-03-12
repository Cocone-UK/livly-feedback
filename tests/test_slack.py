from unittest.mock import patch, MagicMock
from outputs.slack import build_digest_message, _build_fallback_digest, _build_stats_context, post_slack_digest


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
        "summary_jp": "バグ報告",
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
    ctx = _build_stats_context(rows)
    assert "EN (3 items)" in ctx
    assert "JP (1 items)" in ctx


def test_build_stats_context_shows_critical_details():
    rows = _make_classified_rows()
    ctx = _build_stats_context(rows)
    assert "Critical items: 1" in ctx


def test_fallback_digest_contains_both_regions():
    rows = _make_classified_rows()
    msg = _build_fallback_digest(rows, sheet_url="https://sheets.example.com", week_str="Mar 10, 2026")
    assert "EN Summary" in msg
    assert "JP Summary" in msg
    assert "critical" in msg.lower()


@patch("outputs.slack.anthropic.Anthropic")
def test_build_digest_message_calls_sonnet(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="*Livly Island Feedback — Week of Mar 10, 2026*\nEN Summary")]
    mock_client.messages.create.return_value = mock_response

    rows = _make_classified_rows()
    msg = build_digest_message(rows, sheet_url="https://sheets.example.com")

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
    msg = build_digest_message(rows, sheet_url="https://sheets.example.com")

    assert "Livly Island Feedback" in msg


@patch("outputs.slack.httpx.post")
def test_post_slack_digest_sends_webhook(mock_post):
    mock_post.return_value = MagicMock(status_code=200)
    post_slack_digest("Test message", webhook_url="https://hooks.slack.com/test")
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert "text" in call_args[1].get("json", {}) or "text" in call_args.kwargs.get("json", {})
