"""Badges à paliers du catalogue d'origine : distance, dénivelé, temps d'effort, exploits en une séance,
renforcement, météo difficile, bouclier tibial et régularité hebdomadaire. Fonction pure, sans état.
"""
from datetime import date as dt_date
from typing import Any, Dict, List, Optional

from app.connectors.sheets.sport_models import BadgeCategory, SportBadge, SportSession


def evaluate_tier_badges(
    realised: List[SportSession],
    total_dist: float,
    total_dplus: int,
    total_duree: int,
    total_renfo: int,
) -> List[SportBadge]:
    badges: List[SportBadge] = []

    # --- Paliers Distance réguliers (Doses de dopamine fréquentes & tous les 100 km) ---
    dist_tiers = [
        ("dist_10k", "Premier 10 km Cumulé", "Franchir ses premiers 10 km sur l'application", "🏃", 10.0, "bronze"),
        ("dist_marathon", "Premier Marathon Cumulé", "Franchir la barre mythique des 42.195 km", "🏅", 42.2, "bronze"),
    ]

    # Tranches régulières de 100 km (100, 200, 300...) au minimum jusqu'à 500 km et toujours jusqu'au palier suivant
    max_hundred = max(int(total_dist // 100) + 1, 5)
    for h in range(1, max_hundred + 1):
        target = h * 100.0
        b_id = f"dist_{int(target)}k"
        if h == 1:
            title, rarity, icon = "Centurion (100 km)", "argent", "🥉"
        elif h == 2:
            title, rarity, icon = "Double Centurion (200 km)", "argent", "🥈"
        elif h == 3:
            title, rarity, icon = "Trident (300 km)", "argent", "🔱"
        elif h == 4:
            title, rarity, icon = "Quadra (400 km)", "argent", "🏃"
        elif h == 5:
            title, rarity, icon = "Demi-Millier (500 km)", "or", "🥇"
        else:
            title, rarity, icon = f"Cap des {int(target)} km", "or", "🏃"
        desc = f"Franchir {int(target)} km de course cumulés"
        dist_tiers.append((b_id, title, desc, icon, target, rarity))

    # Grands jalons de distance (> 1000 km)
    major_dist_milestones = [
        ("dist_1000k", "Millénaire (1 000 km)", "Le club très fermé des 1 000 km !", "💎", 1000.0, "diamant"),
        ("dist_2000k", "Grand Voyageur (2 000 km)", "2 000 km d'efforts cumulés", "💎", 2000.0, "diamant"),
        ("dist_5000k", "Le Tour de France (5 000 km)", "Une épopée à travers routes et sentiers", "👑", 5000.0, "mythique"),
        ("dist_10000k", "L'Olympe du Running (10 000 km)", "10 000 km : l'excellence absolue !", "👑", 10000.0, "mythique"),
    ]
    for item in major_dist_milestones:
        if not any(t[0] == item[0] for t in dist_tiers):
            dist_tiers.append(item)

    for b_id, title, desc, icon, target, rarity in dist_tiers:
        unlocked = total_dist >= target
        pct = min(100, int((total_dist / target) * 100)) if target > 0 else 100
        badges.append(
            SportBadge(
                id=b_id,
                title=title,
                description=desc,
                icon=icon,
                category=BadgeCategory.DISTANCE,
                is_unlocked=unlocked,
                current_value=total_dist,
                target_value=target,
                unit="km",
                progress_pct=pct,
                rarity=rarity,
            )
        )

    # --- Paliers Dénivelé réguliers (tous les 1 000 m D+ & 10 000 m D+) ---
    dplus_tiers = [
        ("dplus_300m", "Tour Eiffel (300 m D+)", "Grimper l'équivalent de la Dame de Fer", "🗼", 300, "bronze"),
    ]

    # Tranches régulières de 1 000 m D+ (1000, 2000, 3000...) au minimum jusqu'à 5000 m et au-delà
    max_thousand = max(int(total_dplus // 1000) + 1, 5)
    for k in range(1, max_thousand + 1):
        target = k * 1000
        b_id = f"dplus_{target}m"
        if k == 1:
            title, rarity, icon = "Kilomètre Vertical (1 000 m D+)", "argent", "⛰️"
        elif k == 2:
            title, rarity, icon = "Double Vertical (2 000 m D+)", "argent", "⛰️"
        elif k == 3:
            title, rarity, icon = "Le Dôme des Neiges (3 000 m D+)", "argent", "🏔️"
        elif k == 4:
            title, rarity, icon = "Les 4 000 (4 000 m D+)", "or", "🏔️"
        elif k == 5:
            title, rarity, icon = "L'Alpiniste (5 000 m D+)", "or", "🧗"
        else:
            title, rarity, icon = f"Cap des {target} m D+", "or", "🧗"
        desc = f"{target:,} mètres d'ascension cumulés".replace(",", " ")
        dplus_tiers.append((b_id, title, desc, icon, target, rarity))

    # Grands jalons D+
    major_dplus = [
        ("dplus_2500m", "Col du Galibier (2 500 m D+)", "Franchir le dénivelé des géants du Tour", "🚵", 2500, "or"),
        ("dplus_4807m", "Mont Blanc (4 807 m D+)", "Se hisser au sommet de l'Europe occidentale", "🏔️", 4807, "diamant"),
        ("dplus_8848m", "Everest Express (8 848 m D+)", "Le toit du monde conquis en foulées !", "👑", 8848, "mythique"),
        ("dplus_10000m", "L'Étoile des Cimes (10 000 m D+)", "10 000 mètres d'ascension verticale !", "👑", 10000, "diamant"),
        ("dplus_20000m", "La Stratosphère (20 000 m D+)", "Deux fois l'Everest dans les cuisses !", "🪐", 20000, "mythique"),
    ]
    for item in major_dplus:
        if not any(t[0] == item[0] for t in dplus_tiers):
            dplus_tiers.append(item)

    for b_id, title, desc, icon, target, rarity in dplus_tiers:
        unlocked = total_dplus >= target
        pct = min(100, int((total_dplus / target) * 100)) if target > 0 else 100
        badges.append(
            SportBadge(
                id=b_id,
                title=title,
                description=desc,
                icon=icon,
                category=BadgeCategory.DENIVELE,
                is_unlocked=unlocked,
                current_value=float(total_dplus),
                target_value=float(target),
                unit="m",
                progress_pct=pct,
                rarity=rarity,
            )
        )

    # --- Paliers Temps d'effort (comparés en jours) ---
    time_tiers = [
        ("time_10h", "10 Heures d'Effort", "Cumuler 10h de pratique active", "⏱️", 36000, "bronze", "10 h"),
        ("time_24h", "24 Heures Chrono", "Un jour complet passé à courir ou se renforcer", "⏳", 86400, "argent", "24 h"),
        ("time_50h", "50 Heures de Sueur", "50h d'investissement sportif", "⚡", 180000, "or", "50 h"),
        ("time_96h", "4 Jours Pleins à Courir (96h)", "96h d'effort cumulé : 4 jours et nuits entiers !", "🏃", 345600, "or", "4 jours"),
        ("time_240h", "10 Jours Ininterrompus (240h)", "240h d'effort cumulé : 10 jours complets à fouler la terre !", "🌟", 864000, "diamant", "10 jours"),
        ("time_480h", "20 Jours de Foulée (480h)", "480h d'effort : presque 3 semaines non-stop !", "💎", 1728000, "diamant", "20 jours"),
        ("time_960h", "La Quarantaine du Runner (960h)", "960h : 40 jours d'épopée active !", "👑", 3456000, "mythique", "40 jours"),
        ("time_1920h", "Le Tour du Monde en 80 Jours (1920h)", "1920h d'effort cumulé : 80 jours entiers de mouvement !", "🪐", 6912000, "mythique", "80 jours"),
    ]

    for b_id, title, desc, icon, target_sec, rarity, unit_lbl in time_tiers:
        unlocked = total_duree >= target_sec
        pct = min(100, int((total_duree / target_sec) * 100)) if target_sec > 0 else 100
        badges.append(
            SportBadge(
                id=b_id,
                title=title,
                description=desc,
                icon=icon,
                category=BadgeCategory.TEMPS,
                is_unlocked=unlocked,
                current_value=round(total_duree / 3600.0, 1),
                target_value=round(target_sec / 3600.0, 1),
                unit="h",
                progress_pct=pct,
                rarity=rarity,
            )
        )

    # --- Exploits en une seule séance (Mono-Session) ---
    max_single_dist = max((s.distance_km or 0.0 for s in realised), default=0.0)
    max_single_duree = max((s.duree_secondes or 0 for s in realised), default=0)

    mono_dist_tiers = [
        ("mono_dist_10k", "Premier Dix Bornes", "Boucler 10 km d'une seule traite", "🥉", 10.0, "bronze"),
        ("mono_dist_15k", "L'Explorateur des 15", "Dépasser 15 km en une seule sortie", "🥈", 15.0, "bronze"),
        ("mono_dist_semi", "Le Semi-Marathon", "Franchir les 21.1 km d'un seul coup !", "🥇", 21.1, "argent"),
        ("mono_dist_30k", "Le Mur des Trente", "30 km d'affilée dans les jambes", "💎", 30.0, "or"),
        ("mono_dist_marathon", "L'Épreuve d'Athènes", "42.195 km bouclés en une seule sortie !", "👑", 42.2, "diamant"),
        ("mono_dist_100k", "Le Cent-Bornard Fou", "Courir 100 km d'un seul coup ! L'ultra légendaire", "🪐", 100.0, "mythique"),
    ]

    for b_id, title, desc, icon, target, rarity in mono_dist_tiers:
        unlocked = max_single_dist >= target
        pct = min(100, int((max_single_dist / target) * 100)) if target > 0 else 100
        badges.append(
            SportBadge(
                id=b_id,
                title=title,
                description=desc,
                icon=icon,
                category=BadgeCategory.MONO_SESSION,
                is_unlocked=unlocked,
                current_value=round(max_single_dist, 1),
                target_value=target,
                unit="km",
                progress_pct=pct,
                rarity=rarity,
            )
        )

    mono_duree_tiers = [
        ("mono_duree_1h", "L'Heure Pleine (1h)", "Courir ou s'entraîner 1h sans s'arrêter", "⏱️", 3600, "bronze"),
        ("mono_duree_1h15", "Le Cap des 75 min", "1h15 d'effort continu d'une seule traite", "⏱️", 4500, "bronze"),
        ("mono_duree_1h30", "L'Endurant des 90 min", "1h30 d'effort ininterrompu", "⚡", 5400, "argent"),
        ("mono_duree_2h", "La Sortie Royale (2h)", "2 heures continues sous le harnais", "🌟", 7200, "argent"),
        ("mono_duree_3h", "Le Guerrier du Long Cours (3h)", "3 heures d'effort ininterrompu", "🔥", 10800, "or"),
        ("mono_duree_24h", "La Ronde des 24 Heures", "24 heures d'affilée sans dormir ! Absurde et titanesque", "👑", 86400, "mythique"),
    ]

    for b_id, title, desc, icon, target_sec, rarity in mono_duree_tiers:
        unlocked = max_single_duree >= target_sec
        pct = min(100, int((max_single_duree / target_sec) * 100)) if target_sec > 0 else 100
        badges.append(
            SportBadge(
                id=b_id,
                title=title,
                description=desc,
                icon=icon,
                category=BadgeCategory.MONO_SESSION,
                is_unlocked=unlocked,
                current_value=round(max_single_duree / 3600.0, 1),
                target_value=round(target_sec / 3600.0, 1),
                unit="h",
                progress_pct=pct,
                rarity=rarity,
            )
        )

    # --- Renforcement Musculaire Progressif jusqu'à 100 séances ---
    renfo_tiers = [
        ("renfo_complet", "L'Athlète Complet", "Réaliser au moins 3 séances de renforcement musculaire", "🏋️", 3, "bronze"),
        ("renfo_5", "Les Premières Dalles", "5 séances de renforcement musculaire accomplies", "🧱", 5, "bronze"),
        ("renfo_10", "Gainage d'Acier", "10 séances de renfo : le tronc est solide !", "🔩", 10, "bronze"),
        ("renfo_25", "Chantier Musculaire", "25 séances : une structure à l'épreuve des chocs", "🏗️", 25, "argent"),
        ("renfo_50", "La Machine de Guerre", "50 séances de renforcement : puissance et stabilité !", "⚔️", 50, "or"),
        ("renfo_75", "Le Colosse", "75 séances de renforcement au compteur", "🛡️", 75, "diamant"),
        ("renfo_100", "Titan du Renforcement (100 séances)", "100 séances de renforcement musculaire ! Respect absolu", "👑", 100, "mythique"),
    ]

    for b_id, title, desc, icon, target_cnt, rarity in renfo_tiers:
        unlocked = total_renfo >= target_cnt
        pct = min(100, int((total_renfo / target_cnt) * 100)) if target_cnt > 0 else 100
        badges.append(
            SportBadge(
                id=b_id,
                title=title,
                description=desc,
                icon=icon,
                category=BadgeCategory.REGULARITE,
                is_unlocked=unlocked,
                current_value=float(total_renfo),
                target_value=float(target_cnt),
                unit="séances",
                progress_pct=pct,
                rarity=rarity,
            )
        )

    # --- Météo Difficile Progressive ---
    warrior_keywords = ["pluie", "averse", "drache", "vent", "tempête", "tempete", "froid", "boue", "orage", "grêle", "grele"]
    meteo_hard_count = sum(
        1 for s in realised
        if any(kw in (s.remarques or "").lower() for kw in warrior_keywords)
    )

    meteo_tiers = [
        ("meteo_1", "Baptême de Pluie", "Bravé la pluie, le vent ou le froid pour la première fois", "🌧️", 1, "bronze"),
        ("resilience_guerrier", "Guerrier des Éléments", "Réaliser des séances bravant la pluie, le vent ou la boue", "🌧️", 1, "argent"),
        ("meteo_5", "Escargot Tout-Terrain", "5 séances réalisées sous des conditions météo difficiles", "🐌", 5, "argent"),
        ("meteo_10", "Légionnaire des Tempêtes", "10 séances bravant les éléments déchaînés", "⚡", 10, "or"),
        ("meteo_20", "Guerrier Immortel des Éléments", "20 séances dans la boue et sous le déluge ! Rien ne t'arrête", "👑", 20, "diamant"),
    ]

    for b_id, title, desc, icon, target_cnt, rarity in meteo_tiers:
        unlocked = meteo_hard_count >= target_cnt
        pct = min(100, int((meteo_hard_count / target_cnt) * 100)) if target_cnt > 0 else 100
        badges.append(
            SportBadge(
                id=b_id,
                title=title,
                description=desc,
                icon=icon,
                category=BadgeCategory.REGULARITE,
                is_unlocked=unlocked,
                current_value=float(meteo_hard_count),
                target_value=float(target_cnt),
                unit="séances",
                progress_pct=pct,
                rarity=rarity,
            )
        )

    # Bouclier Tibial (au moins 5 séances sans douleur tibiale)
    pain_keywords = ["périost", "periost", "tibia", "douleur", "mal"]
    pain_free_count = 0
    for s in realised:
        rem = (s.remarques or "").lower()
        if not any(kw in rem for kw in pain_keywords):
            pain_free_count += 1
        else:
            pain_free_count = 0
    tibia_unlocked = pain_free_count >= 5
    badges.append(
        SportBadge(
            id="resilience_tibia",
            title="Bouclier Tibial",
            description="Enchaîner 5 séances consécutives sans douleur ni alerte périostite",
            icon="🛡️",
            category=BadgeCategory.REGULARITE,
            is_unlocked=tibia_unlocked,
            current_value=min(float(pain_free_count), 5.0),
            target_value=5.0,
            unit="séances",
            progress_pct=min(100, int((pain_free_count / 5.0) * 100)),
            rarity="or",
        )
    )

    # Semaine parfaite : 7 séances dans la même semaine
    sessions_per_week: Dict[Any, int] = {}
    for s in realised:
        yr, wk, _ = s.date.isocalendar()
        sessions_per_week[(yr, wk)] = sessions_per_week.get((yr, wk), 0) + 1
    max_seances_same_week = max(sessions_per_week.values(), default=0)
    unlocked_7_week = max_seances_same_week >= 7
    badges.append(
        SportBadge(
            id="reg_7_seances_semaine",
            title="Grand Chelem Hebdo (7/7)",
            description="Réaliser 7 séances de sport dans la même semaine ! L'assiduité sans faille",
            icon="🔥",
            category=BadgeCategory.REGULARITE,
            is_unlocked=unlocked_7_week,
            current_value=float(max_seances_same_week),
            target_value=7.0,
            unit="séances",
            progress_pct=min(100, int((max_seances_same_week / 7.0) * 100)),
            rarity="or",
        )
    )

    # 4 séances par semaine pendant 8 semaines consécutives
    consecutive_4plus_weeks = 0
    max_consecutive_4plus_weeks = 0
    if sessions_per_week:
        sorted_weeks = sorted(
            sessions_per_week.keys(),
            key=lambda item: dt_date.fromisocalendar(item[0], item[1], 1)
        )
        prev_monday: Optional[dt_date] = None
        for yr, wk in sorted_weeks:
            curr_monday = dt_date.fromisocalendar(yr, wk, 1)
            count = sessions_per_week[(yr, wk)]
            if count >= 4:
                if prev_monday and (curr_monday - prev_monday).days == 7:
                    consecutive_4plus_weeks += 1
                else:
                    consecutive_4plus_weeks = 1
                max_consecutive_4plus_weeks = max(max_consecutive_4plus_weeks, consecutive_4plus_weeks)
                prev_monday = curr_monday
            else:
                consecutive_4plus_weeks = 0
                prev_monday = None

    unlocked_4s_8w = max_consecutive_4plus_weeks >= 8
    badges.append(
        SportBadge(
            id="reg_4seances_8semaines",
            title="Discipline de Fer (8 Semaines)",
            description="Valider au moins 4 séances par semaine pendant 8 semaines consécutives !",
            icon="👑",
            category=BadgeCategory.REGULARITE,
            is_unlocked=unlocked_4s_8w,
            current_value=float(max_consecutive_4plus_weeks),
            target_value=8.0,
            unit="semaines",
            progress_pct=min(100, int((max_consecutive_4plus_weeks / 8.0) * 100)),
            rarity="diamant",
        )
    )
    return badges
