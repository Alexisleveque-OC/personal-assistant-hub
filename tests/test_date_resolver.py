"""Tests unitaires pour le résolveur de dates relatives en français."""
from datetime import date, datetime
import pytest
from app.core.date_resolver import resolve_date_expression, ResolvedDate


def test_resolve_today():
    """Détecte 'aujourd'hui', 'ce midi', 'ce soir'."""
    ref_dt = datetime(2026, 9, 21, 10, 0, 0)  # Lundi 21 Septembre 2026
    
    res1 = resolve_date_expression("qu'est-ce qu'on mange aujourd'hui", now=ref_dt)
    assert res1.target_date == date(2026, 9, 21)
    assert res1.period == "jour"
    
    res2 = resolve_date_expression("on mange quoi ce midi ?", now=ref_dt)
    assert res2.target_date == date(2026, 9, 21)
    assert res2.period == "midi"
    
    res3 = resolve_date_expression("mets des pâtes ce soir", now=ref_dt)
    assert res3.target_date == date(2026, 9, 21)
    assert res3.period == "soir"


def test_resolve_tomorrow():
    """Détecte 'demain', 'demain midi', 'demain soir'."""
    ref_dt = datetime(2026, 9, 21, 10, 0, 0)  # Lundi 21 Septembre 2026
    
    res1 = resolve_date_expression("qu'est-ce qu'on mange demain", now=ref_dt)
    assert res1.target_date == date(2026, 9, 22)
    assert res1.period == "demain"
    
    res2 = resolve_date_expression("prévois du poisson pour demain midi", now=ref_dt)
    assert res2.target_date == date(2026, 9, 22)
    assert res2.period == "midi"
    
    res3 = resolve_date_expression("demain soir", now=ref_dt)
    assert res3.target_date == date(2026, 9, 22)
    assert res3.period == "soir"


def test_resolve_weekday_relative():
    """Depuis lundi 21/09/2026, 'jeudi' ou 'jeudi prochain' résout au 24/09/2026."""
    ref_dt = datetime(2026, 9, 21, 10, 0, 0)  # Lundi 21 Septembre 2026
    
    res1 = resolve_date_expression("Qu'est ce qu'on mange Jeudi prochain ?", now=ref_dt)
    assert res1.target_date == date(2026, 9, 24)
    assert res1.day_name == "Jeudi"
    assert res1.period == "jour"
    
    res2 = resolve_date_expression("que mange t-on jeudi prochain ?", now=ref_dt)
    assert res2.target_date == date(2026, 9, 24)
    assert res2.day_name == "Jeudi"
    
    res3 = resolve_date_expression("prévois du poulet pour jeudi", now=ref_dt)
    assert res3.target_date == date(2026, 9, 24)
    assert res3.day_name == "Jeudi"
    
    res4 = resolve_date_expression("vendredi soir", now=ref_dt)
    assert res4.target_date == date(2026, 9, 25)
    assert res4.day_name == "Vendredi"
    assert res4.period == "soir"


def test_resolve_explicit_calendar_date():
    """Détecte 'le 24 septembre', 'le 24/09', 'le 24/09/2026'."""
    ref_dt = datetime(2026, 9, 21, 10, 0, 0)
    
    res1 = resolve_date_expression("qu'est-ce qu'on mange le 24 septembre ?", now=ref_dt)
    assert res1.target_date == date(2026, 9, 24)
    
    res2 = resolve_date_expression("prévois une pizza le 25/09", now=ref_dt)
    assert res2.target_date == date(2026, 9, 25)

    res3 = resolve_date_expression("qu'est ce qu'on mange dimanche 20 septembre ?", now=ref_dt)
    assert res3.target_date == date(2026, 9, 20)
    assert res3.date_str == "20/09/2026"
    assert res3.day_name == "Dimanche"

    res4 = resolve_date_expression("on mange quoi dimanche 20/09 ?", now=ref_dt)
    assert res4.target_date == date(2026, 9, 20)
    assert res4.date_str == "20/09/2026"
    assert res4.day_name == "Dimanche"


def test_resolve_no_date_expression():
    """Quand aucun repère temporel n'est présent."""
    ref_dt = datetime(2026, 9, 21, 10, 0, 0)
    res = resolve_date_expression("on mange quoi ?", now=ref_dt)
    assert res.target_date is None
    assert res.period == "prochain"


def test_parse_screenshot_date_past_weekdays():
    """Garantit que les noms de jours extraits d'une capture sportive résolvent dans le passé."""
    from app.core.date_resolver import parse_screenshot_date
    ref = date(2026, 10, 15)  # Jeudi 15 Octobre 2026

    # 'mercredi' depuis un jeudi doit donner hier (14/10), JAMAIS mercredi prochain (21/10)
    assert parse_screenshot_date("mercredi", reference_date=ref) == date(2026, 10, 14)
    assert parse_screenshot_date("Mercredi", reference_date=ref) == date(2026, 10, 14)
    assert parse_screenshot_date("mardi", reference_date=ref) == date(2026, 10, 13)
    assert parse_screenshot_date("dimanche", reference_date=ref) == date(2026, 10, 11)


def test_parse_screenshot_date_decathlon_formats():
    """Vérifie la robustesse face aux formats textuels de Decathlon Coach & Connect."""
    from app.core.date_resolver import parse_screenshot_date
    ref = date(2026, 10, 15)

    assert parse_screenshot_date("Mercredi 14", reference_date=ref) == date(2026, 10, 14)
    assert parse_screenshot_date("mercredi 14 oct", reference_date=ref) == date(2026, 10, 14)
    assert parse_screenshot_date("14/10", reference_date=ref) == date(2026, 10, 14)
    assert parse_screenshot_date("14/10 à 18:30", reference_date=ref) == date(2026, 10, 14)
    assert parse_screenshot_date("14/10 - 18h30", reference_date=ref) == date(2026, 10, 14)
    assert parse_screenshot_date("Hier, 18:45", reference_date=ref) == date(2026, 10, 14)
    assert parse_screenshot_date("Course à pied - 14 oct.", reference_date=ref) == date(2026, 10, 14)
    assert parse_screenshot_date("Course à pied du 14 octobre", reference_date=ref) == date(2026, 10, 14)

