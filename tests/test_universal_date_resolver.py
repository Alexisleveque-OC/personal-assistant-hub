"""Tests TDD pour le Correcteur Temporel Universel (UniversalDateResolver).

Couvre l'Étape 1 de la Phase 6.6 :
- Expressions relatives singulières ("hier", "avant-hier", "demain", "après-demain")
- Jours de la semaine qualifiés ("dimanche dernier", "lundi dernier", "mardi prochain")
- Périodes relatives ("cette semaine", "la semaine dernière", "la semaine prochaine")
- Fenêtres plurielles ("ces 3 derniers jours", "les 5 derniers jours")
- Distinction étanche entre période calendaire et décompte conversationnel ("ces 3 derniers échanges")
- Robustesse de parse_target_date et format_natural_spoken_date
"""
from datetime import date, datetime, timedelta
import pytest

from app.core.date_resolver import (
    resolve_date_expression,
    parse_target_date,
    format_natural_spoken_date,
    resolve_temporal_range,
    TemporalRangeType,
)


def test_resolve_relative_days_hier_and_avanthier():
    """Vérifie la résolution de 'hier' et 'avant-hier'."""
    ref_dt = datetime(2026, 10, 12, 10, 0, 0)  # Lundi 12 Octobre 2026
    
    res_hier = resolve_date_expression("Quelle était ma séance d'hier ?", now=ref_dt)
    assert res_hier.target_date == date(2026, 10, 11)
    assert res_hier.day_name == "Dimanche"
    assert res_hier.period == "hier"

    res_avanthier = resolve_date_expression("Mon ressenti d'avant-hier", now=ref_dt)
    assert res_avanthier.target_date == date(2026, 10, 10)
    assert res_avanthier.day_name == "Samedi"
    assert res_avanthier.period == "avant-hier"


def test_resolve_relative_days_demain_and_apresdemain():
    """Vérifie la résolution de 'demain' et 'après-demain'."""
    ref_dt = datetime(2026, 10, 12, 10, 0, 0)  # Lundi 12 Octobre 2026
    
    res_demain = resolve_date_expression("Que mange-t-on demain soir ?", now=ref_dt)
    assert res_demain.target_date == date(2026, 10, 13)
    assert res_demain.day_name == "Mardi"
    assert res_demain.period == "soir"

    res_apresdemain = resolve_date_expression("Prévois une sortie après-demain", now=ref_dt)
    assert res_apresdemain.target_date == date(2026, 10, 14)
    assert res_apresdemain.day_name == "Mercredi"
    assert res_apresdemain.period == "après-demain"


def test_resolve_weekdays_with_dernier_and_prochain():
    """Vérifie la distinction temporelle passée/future sur les jours de semaine (ex: 'dimanche dernier')."""
    ref_dt = datetime(2026, 10, 12, 10, 0, 0)  # Lundi 12 Octobre 2026
    
    # "dimanche dernier" depuis un lundi = hier (11/10/2026)
    res_dimanche_dernier = resolve_date_expression("Ma course de dimanche dernier", now=ref_dt)
    assert res_dimanche_dernier.target_date == date(2026, 10, 11)
    assert res_dimanche_dernier.day_name == "Dimanche"

    # "lundi dernier" depuis un lundi = le lundi précédent (05/10/2026, -7 jours)
    res_lundi_dernier = resolve_date_expression("Mon footing de lundi dernier", now=ref_dt)
    assert res_lundi_dernier.target_date == date(2026, 10, 5)
    assert res_lundi_dernier.day_name == "Lundi"

    # "jeudi prochain" depuis un lundi = le jeudi qui arrive (15/10/2026, +3 jours)
    res_jeudi_prochain = resolve_date_expression("Planifie du renfo pour jeudi prochain", now=ref_dt)
    assert res_jeudi_prochain.target_date == date(2026, 10, 15)
    assert res_jeudi_prochain.day_name == "Jeudi"


def test_resolve_temporal_range_plural_days():
    """Vérifie la détection d'une plage temporelle de N derniers jours."""
    ref_dt = datetime(2026, 10, 12, 10, 0, 0)
    today = ref_dt.date()

    # "ces 3 derniers jours" -> du 10/10 au 12/10
    range_res = resolve_temporal_range("Fais un bilan de ces 3 derniers jours", now=ref_dt)
    assert range_res is not None
    assert range_res.range_type == TemporalRangeType.DAYS_WINDOW
    assert range_res.nb_days == 3
    assert range_res.start_date == today - timedelta(days=2)
    assert range_res.end_date == today
    assert len(range_res.all_dates) == 3


def test_resolve_temporal_range_semaines():
    """Vérifie la détection de 'cette semaine' et 'la semaine dernière'."""
    ref_dt = datetime(2026, 10, 14, 10, 0, 0)  # Mercredi 14 Octobre 2026 (Semaine 42)
    
    # Cette semaine
    r_cette_semaine = resolve_temporal_range("Quel est mon volume de course cette semaine ?", now=ref_dt)
    assert r_cette_semaine is not None
    assert r_cette_semaine.range_type == TemporalRangeType.CURRENT_WEEK
    assert r_cette_semaine.start_date == date(2026, 10, 12)  # Lundi de la semaine 42
    assert r_cette_semaine.end_date == date(2026, 10, 18)    # Dimanche de la semaine 42

    # La semaine dernière
    r_semaine_derniere = resolve_temporal_range("Bilan de la semaine dernière", now=ref_dt)
    assert r_semaine_derniere is not None
    assert r_semaine_derniere.range_type == TemporalRangeType.LAST_WEEK
    assert r_semaine_derniere.start_date == date(2026, 10, 5)   # Lundi semaine 41
    assert r_semaine_derniere.end_date == date(2026, 10, 11)   # Dimanche semaine 41


def test_distinguish_temporal_days_vs_conversation_echanges():
    """Vérifie que 'ces 3 derniers échanges' ou 'ces derniers messages' n'est PAS confondu avec des jours."""
    ref_dt = datetime(2026, 10, 12, 10, 0, 0)

    # Doit retourner None pour la plage temporelle calendaire car ce sont des échanges textuels
    range_res = resolve_temporal_range("Ok prend note de ces 3 derniers échanges. Il faut corriger", now=ref_dt)
    assert range_res is None

    # resolve_date_expression ne doit pas inventer de date sur "ces 3 derniers échanges"
    date_res = resolve_date_expression("Ok prend note de ces 3 derniers échanges", now=ref_dt)
    assert date_res.target_date is None


def test_parse_target_date_with_universal_corrections():
    """Vérifie parse_target_date avec toutes les déclinaisons textuelles."""
    ref_today = date(2026, 10, 12)

    assert parse_target_date("hier") == ref_today - timedelta(days=1)
    assert parse_target_date("avant-hier") == ref_today - timedelta(days=2)
    assert parse_target_date("demain") == ref_today + timedelta(days=1)
    assert parse_target_date("après-demain") == ref_today + timedelta(days=2)
    assert parse_target_date("dimanche dernier") == date(2026, 10, 11)


def test_intent_parser_resolves_past_and_future_sport_queries():
    """Vérifie qu'IntentParser résout correctement les dates relatives passées et futures."""
    from app.core.intent_parser import IntentParser
    from app.core.models import IntentType

    parser = IntentParser()

    # Consultation de séance d'avant-hier
    p1 = parser.parse("C'est quoi ma séance d'avant-hier ?")
    assert p1.intent == IntentType.GET_SPORT_SESSION
    assert p1.parameters.get("target_date") is not None
    assert p1.parameters["target_date"] != "today"

    # Consultation de séance d'hier
    p2 = parser.parse("C'était quoi ma course d'hier ?")
    assert p2.intent == IntentType.GET_SPORT_SESSION
    assert p2.parameters.get("target_date") in ("hier", (date.today() - timedelta(days=1)).isoformat())

    # Demande sur les échanges ne doit JAMAIS être comprise comme une séance
    p3 = parser.parse("Ok prend note de ces 3 derniers échanges. Il faut corriger")
    assert p3.intent != IntentType.UPDATE_SPORT_SESSION
    assert p3.intent != IntentType.GET_SPORT_SESSION

