from unittest.mock import patch, MagicMock
from main import run, parse_args


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


def test_parse_args_defaults():
    args = parse_args(["--scrapers", "all"])
    assert args.classify is False
    assert args.export is False
