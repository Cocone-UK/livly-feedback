from unittest.mock import MagicMock, patch
from classifier.classify import classify_feedback, CLASSIFICATION_TOOL, CATEGORIES


def test_categories_match_spec():
    expected = [
        "ux", "tutorial_onboarding", "gacha_monetization", "social",
        "bugs_performance", "content_request", "account_login",
        "art_aesthetics", "general_praise", "events", "localization",
    ]
    for cat in expected:
        assert cat in CATEGORIES


def test_classification_tool_has_required_fields():
    props = CLASSIFICATION_TOOL["input_schema"]["properties"]
    assert "sentiment" in props
    assert "categories" in props
    assert "severity" in props
    assert "language" in props
    assert "summary_en" in props
    assert "summary_jp" in props
    assert "key_quotes" in props


@patch("classifier.classify.anthropic.Anthropic")
def test_classify_feedback_returns_classification(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    mock_tool_block = MagicMock()
    mock_tool_block.type = "tool_use"
    mock_tool_block.input = {
        "sentiment": "negative",
        "categories": ["bugs_performance"],
        "severity": "moderate",
        "language": "en",
        "summary_en": "User reports island layout broken after update",
        "summary_jp": "ユーザーがアップデート後に島のレイアウトが壊れたと報告",
        "key_quotes": ["broke my island layout"],
    }

    mock_response = MagicMock()
    mock_response.content = [mock_tool_block]
    mock_response.model = "claude-haiku-4-5-20251001"
    mock_client.messages.create.return_value = mock_response

    result = classify_feedback(
        feedback_id="test-id",
        content="The new update broke my island layout",
        source="discord",
        rating=None,
    )

    assert result["sentiment"] == "negative"
    assert result["severity"] == "moderate"
    assert result["model_used"] == "claude-haiku-4-5-20251001"
    assert "bugs_performance" in result["categories"]


@patch("classifier.classify.anthropic.Anthropic")
def test_classify_feedback_handles_api_error(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.side_effect = Exception("Rate limited")

    result = classify_feedback(
        feedback_id="test-id",
        content="test",
        source="discord",
        rating=None,
    )

    assert result is None
