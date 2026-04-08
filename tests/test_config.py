import pytest
from config import load_game_config


def test_load_livly_config():
    config = load_game_config("livly")
    assert config["slug"] == "livly"
    assert config["display_name"] == "Livly Island"
    assert config["appstore_id"] == "1553045339"
    assert config["tables"]["feedback_raw"] == "feedback_raw"


def test_load_pokecolo_config():
    config = load_game_config("pokecolo")
    assert config["slug"] == "pokecolo"
    assert config["appstore_id"] == "451684733"
    assert config["tables"]["feedback_raw"] == "pokecolo_feedback_raw"


def test_slug_injected_from_key():
    config = load_game_config("livly")
    assert "slug" in config
    assert config["slug"] == "livly"


def test_unknown_slug_raises():
    with pytest.raises(ValueError, match="Unknown game 'nonexistent'"):
        load_game_config("nonexistent")


def test_country_cross_validation(tmp_path, monkeypatch):
    """A country in google_play_regions but not in country_to_region should fail."""
    import json
    bad_config = {
        "bad_game": {
            "display_name": "Bad",
            "game_description": "test",
            "appstore_id": "1",
            "google_play_id": "com.test",
            "google_play_regions": [["en", "xx"]],
            "country_to_region": {"us": "en"},
            "categories": ["ux"],
            "tables": {
                "feedback_raw": "t1",
                "feedback_classified": "t2",
                "scrape_runs": "t3",
                "unclassified_rpc": "t4",
            },
            "sheets_id": None,
            "sheet_region_groups": {},
            "legacy_tabs_to_remove": [],
            "slack_webhook_url": None,
        }
    }
    config_file = tmp_path / "games.json"
    config_file.write_text(json.dumps(bad_config))
    monkeypatch.setattr("config.CONFIG_PATH", str(config_file))

    with pytest.raises(ValueError, match="country 'xx'.*missing from country_to_region"):
        load_game_config("bad_game")
