from unittest.mock import patch, MagicMock
from main import run, parse_args


def test_parse_args_defaults():
    args = parse_args(["--scrapers", "all"])
    assert args.game == "livly"
    assert args.classify is False
    assert args.export is False


def test_parse_args_game_flag():
    args = parse_args(["--game", "pokecolo", "--scrapers", "appstore"])
    assert args.game == "pokecolo"
    assert args.scrapers == "appstore"


def test_parse_args_scrapers_all():
    args = parse_args(["--scrapers", "all"])
    assert args.scrapers == "all"


def test_parse_args_scrapers_discord():
    args = parse_args(["--scrapers", "discord"])
    assert args.scrapers == "discord"


def test_parse_args_classify_flag():
    args = parse_args(["--scrapers", "all", "--classify"])
    assert args.classify is True


def test_parse_args_export_flag():
    args = parse_args(["--scrapers", "all", "--export"])
    assert args.export is True


def test_parse_args_sheets_id_override():
    args = parse_args(["--scrapers", "all", "--sheets-id", "CUSTOM_ID"])
    assert args.sheets_id == "CUSTOM_ID"
