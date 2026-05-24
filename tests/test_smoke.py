"""Minimal pytest smoke tests so CI has at least one collected item."""

from pathlib import Path


def test_repo_has_pytest_ini():
    assert Path(__file__).resolve().parent.parent.joinpath("pytest.ini").is_file()


def test_health_route_registered_when_app_loaded():
    from app import create_app

    app = create_app("testing")
    # Flask registers '/' from blueprint without trailing slash rule quirks here.
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/" in rules or "/health" in rules

