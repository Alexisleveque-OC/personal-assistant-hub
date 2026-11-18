"""Refacto anti-tokens, lot 5 : la lecture des dates de captures sportives a son propre module."""
from datetime import date
from pathlib import Path

CORE = Path(__file__).resolve().parent.parent / "app" / "core"


def test_screenshot_date_lives_in_its_own_module():
    from app.core.screenshot_date import parse_screenshot_date

    assert len((CORE / "date_resolver.py").read_text(encoding="utf-8").splitlines()) < 400
    assert parse_screenshot_date("14/10", reference_date=date(2026, 10, 15)) == date(2026, 10, 14)
