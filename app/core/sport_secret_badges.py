"""Badges secrets (easter eggs) et cosmiques du catalogue d'origine. Fonction pure, sans état.
"""
from typing import List

from app.connectors.sheets.sport_models import BadgeCategory, SportBadge, SportSession


def evaluate_secret_badges(realised: List[SportSession], total_dist: float) -> List[SportBadge]:
    badges: List[SportBadge] = []

    # --- Badges Secrets & Easter Eggs (Demandés par Alexis !) ---
    # 1. Le Déneigéré ❄️ (mot clé neige, blizzard, flocons)
    snow_keywords = ["neige", "neigeait", "blizzard", "flocons"]
    deneigere_unlocked = any(
        any(kw in (s.remarques or "").lower() for kw in snow_keywords)
        for s in realised
    )
    badges.append(
        SportBadge(
            id="secret_deneigere",
            title="Le Déneigéré ❄️" if deneigere_unlocked else "Badge Secret ❄️",
            description="Avoir couru dans la neige ou sous le blizzard" if deneigere_unlocked else "Conditions météorologiques givrées très particulières...",
            icon="☃️" if deneigere_unlocked else "🔒",
            category=BadgeCategory.SECRET,
            is_unlocked=deneigere_unlocked,
            is_secret=True,
            current_value=1.0 if deneigere_unlocked else 0.0,
            target_value=1.0,
            progress_pct=100 if deneigere_unlocked else 0,
            rarity="or",
        )
    )

    # 2. Pi Runner 🥧 (distance 3.14 km à ±0.03 près ou chrono 31:41)
    pi_unlocked = any(
        (s.distance_km and abs(s.distance_km - 3.14) <= 0.03) or (s.duree_secondes == 1901)
        for s in realised
    )
    badges.append(
        SportBadge(
            id="secret_pi_runner",
            title="Le Pi Runner 🥧" if pi_unlocked else "Badge Secret 🥧",
            description="Boucler une séance à exactement 3.14 km ou 31:41 !" if pi_unlocked else "Une énigme mathématique taillée pour les baskets...",
            icon="🥧" if pi_unlocked else "🔒",
            category=BadgeCategory.SECRET,
            is_unlocked=pi_unlocked,
            is_secret=True,
            current_value=1.0 if pi_unlocked else 0.0,
            target_value=1.0,
            progress_pct=100 if pi_unlocked else 0,
            rarity="or",
        )
    )

    # 3. Chrono d'Orfèvre ⏱️ (terminer pile à la minute ronde, secondes == 0, durée > 10 min)
    chrono_rond_unlocked = any(
        (s.duree_secondes and s.duree_secondes >= 600 and s.duree_secondes % 60 == 0)
        for s in realised
    )
    badges.append(
        SportBadge(
            id="secret_chrono_rond",
            title="Chrono d'Orfèvre ⏱️" if chrono_rond_unlocked else "Badge Secret ⏱️",
            description="Arrêter sa montre pile à la minute ronde (zéro seconde) !" if chrono_rond_unlocked else "Une précision d'horloger suisse...",
            icon="🎯" if chrono_rond_unlocked else "🔒",
            category=BadgeCategory.SECRET,
            is_unlocked=chrono_rond_unlocked,
            is_secret=True,
            current_value=1.0 if chrono_rond_unlocked else 0.0,
            target_value=1.0,
            progress_pct=100 if chrono_rond_unlocked else 0,
            rarity="argent",
        )
    )

    # 4. Coureur Nocturne 🔦 (remarque frontale / nuit)
    night_keywords = ["frontale", "nuit", "obscurité", "nocturne"]
    night_unlocked = any(
        any(kw in (s.remarques or "").lower() for kw in night_keywords)
        for s in realised
    )
    badges.append(
        SportBadge(
            id="secret_frontale",
            title="Coureur Nocturne 🔦" if night_unlocked else "Badge Secret 🔦",
            description="Courir à la lampe frontale dans l'obscurité" if night_unlocked else "Quand le soleil se couche mais pas les runners...",
            icon="🔦" if night_unlocked else "🔒",
            category=BadgeCategory.SECRET,
            is_unlocked=night_unlocked,
            is_secret=True,
            current_value=1.0 if night_unlocked else 0.0,
            target_value=1.0,
            progress_pct=100 if night_unlocked else 0,
            rarity="bronze",
        )
    )

    # --- Badges Absurdes & Cosmiques ---
    # Road to the Moon (384 400 km)
    moon_dist = 384400.0
    moon_pct = round((total_dist / moon_dist) * 100, 3)
    badges.append(
        SportBadge(
            id="absurd_moon",
            title="Objectif Lune 🚀",
            description="Parcourir la distance Terre-Lune (384 400 km). Un petit pas pour Otis...",
            icon="🌕",
            category=BadgeCategory.ABSURDE,
            is_unlocked=total_dist >= moon_dist,
            current_value=total_dist,
            target_value=moon_dist,
            unit="km",
            progress_pct=int(moon_pct),
            rarity="mythique",
        )
    )

    # Vers le Noyau Terrestre (Rayon de la Terre : 6 371 km)
    earth_r = 6371.0
    badges.append(
        SportBadge(
            id="absurd_earth_core",
            title="Rayon de la Terre 🌍",
            description="Atteindre le centre de la Terre en foulées cumulées (6 371 km)",
            icon="🪐",
            category=BadgeCategory.ABSURDE,
            is_unlocked=total_dist >= earth_r,
            current_value=total_dist,
            target_value=earth_r,
            unit="km",
            progress_pct=min(100, int((total_dist / earth_r) * 100)),
            rarity="mythique",
        )
    )

    # Le Tour de l'Équateur (40 075 km)
    equateur_dist = 40075.0
    badges.append(
        SportBadge(
            id="absurd_equateur",
            title="L'Équateur Terrestre 🌐",
            description="Boucler le tour complet de la planète Terre (40 075 km)",
            icon="🌐",
            category=BadgeCategory.ABSURDE,
            is_unlocked=total_dist >= equateur_dist,
            current_value=total_dist,
            target_value=equateur_dist,
            unit="km",
            progress_pct=min(100, int((total_dist / equateur_dist) * 100)),
            rarity="mythique",
        )
    )
    return badges
