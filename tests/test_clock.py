"""Tests unitaires du helper unique « aujourd'hui » en fuseau Europe/Paris (Phase 6.8 - Étape 0).

Le conteneur Cloud Run tourne en UTC : entre 00h et 02h (heure de Paris), un `date.today()`
naïf renvoie la veille. Le NLU doit raisonner sur la date vécue par l'utilisateur.
"""
from datetime import date, datetime, timezone

import pytest

from app.core.clock import APP_TIMEZONE, paris_now, paris_today


def test_app_timezone_is_europe_paris():
    assert str(APP_TIMEZONE) == "Europe/Paris"


def test_paris_today_after_utc_midnight_in_winter():
    """26/10 00h30 à Paris (UTC+1) = 25/10 23h30 UTC : aujourd'hui est déjà le 26."""
    now_utc = datetime(2026, 10, 25, 23, 30, tzinfo=timezone.utc)
    assert paris_today(now_utc) == date(2026, 10, 26)


def test_paris_today_after_utc_midnight_in_summer():
    """15/07 01h30 à Paris (UTC+2) = 14/07 23h30 UTC."""
    now_utc = datetime(2026, 7, 14, 23, 30, tzinfo=timezone.utc)
    assert paris_today(now_utc) == date(2026, 7, 15)


def test_paris_today_same_day_during_daytime():
    now_utc = datetime(2026, 10, 26, 10, 0, tzinfo=timezone.utc)
    assert paris_today(now_utc) == date(2026, 10, 26)


def test_paris_now_converts_aware_datetime():
    now_utc = datetime(2026, 7, 14, 22, 15, tzinfo=timezone.utc)
    result = paris_now(now_utc)
    assert result.tzinfo is APP_TIMEZONE
    assert (result.date(), result.hour, result.minute) == (date(2026, 7, 15), 0, 15)


def test_paris_now_without_argument_is_aware_and_in_paris():
    result = paris_now()
    assert result.tzinfo is APP_TIMEZONE
    assert paris_today() == result.date()


def test_naive_datetime_is_rejected():
    """Une date naïve est ambiguë (UTC ? Paris ?) : refus explicite plutôt qu'une supposition."""
    with pytest.raises(ValueError, match="fuseau"):
        paris_today(datetime(2026, 10, 25, 23, 30))
