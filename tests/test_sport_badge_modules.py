"""Refacto anti-tokens, lot 5 : le catalogue de badges sort de sport_gamification_service.py
en modules de données (sur le modèle de sport_fun_badges.py), dans le même ordre qu'avant."""
from pathlib import Path

from app.core.sport_gamification_service import SportGamificationService
from app.core.sport_pop_badges import evaluate_pop_badges
from app.core.sport_secret_badges import evaluate_secret_badges
from app.core.sport_tier_badges import evaluate_tier_badges

CORE = Path(__file__).resolve().parent.parent / "app" / "core"


def test_service_delegates_the_catalogue_to_badge_modules():
    service = (CORE / "sport_gamification_service.py").read_text(encoding="utf-8")
    assert len(service.splitlines()) < 400
    for name in ("evaluate_tier_badges", "evaluate_pop_badges", "evaluate_secret_badges", "evaluate_fun_badges"):
        assert f"{name}(" in service, name
    for module in ("sport_tier_badges", "sport_pop_badges", "sport_secret_badges"):
        assert len((CORE / f"{module}.py").read_text(encoding="utf-8").splitlines()) < 400, module


def test_catalogue_order_is_tiers_then_pop_then_secrets_then_fun():
    badges = SportGamificationService()._badges_for([])
    ids = [b.id for b in badges]
    tiers = [b.id for b in evaluate_tier_badges([], 0.0, 0, 0, 0)]
    pop = [b.id for b in evaluate_pop_badges([], 0.0, 0)]
    secrets = [b.id for b in evaluate_secret_badges([], 0.0)]
    assert ids[: len(tiers) + len(pop) + len(secrets)] == tiers + pop + secrets
