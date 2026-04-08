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
