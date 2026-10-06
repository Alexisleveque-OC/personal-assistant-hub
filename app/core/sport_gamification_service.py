"""Service de gamification, détection de records personnels (PRs), badges et anecdotes sportives (Otis)."""
from datetime import date as dt_date
from typing import Any, Dict, List, Optional

from app.connectors.sheets.sport_models import (
    BadgeCategory,
    ImminentMilestone,
    PersonalRecord,
    SportBadge,
    SportFunFact,
    SportGamificationSummary,
    SportSession,
    SportSessionStatus,
    SportSessionType,
    format_pace,
)


class SportGamificationService:
    """Moteur pur d'évaluation des accomplissements, des records et des équivalences fun."""

    def compute_summary(
        self,
        sessions: List[SportSession],
        reference_date: Optional[dt_date] = None,
    ) -> SportGamificationSummary:
        """Calcule l'ensemble des trophées, anecdotes et records sur l'historique fourni."""
        realised = [s for s in sessions if s.statut == SportSessionStatus.REALISE]
        ref_today = reference_date or dt_date.today()

        # 1. Cumuls globaux
        total_dist = round(sum(s.distance_km or 0.0 for s in realised), 2)
        total_dplus = sum(s.denivele_d_plus or 0 for s in realised)
        total_duree = sum(s.duree_secondes or 0 for s in realised)
        total_seances = len(realised)
        total_renfo = sum(1 for s in realised if s.type_seance == SportSessionType.RENFORCEMENT)
        total_charge_rpe = sum(s.charge_rpe or 0 for s in realised)

        # 2. Détection des Records Personnels (PR)
        prs = self._compute_personal_records(realised)

        # 3. Évaluation des Badges
        badges = self._evaluate_badges(
            realised=realised,
            total_dist=total_dist,
            total_dplus=total_dplus,
            total_duree=total_duree,
            total_seances=total_seances,
            total_renfo=total_renfo,
        )

        unlocked_count = sum(1 for b in badges if b.is_unlocked)
        total_badges = len(badges)

        # 4. Paliers imminents (doses de dopamine & motivation)
        imminent = self._detect_imminent_milestones(badges)

        # 5. Anecdotes et équivalences insolites
        fun_facts = self._generate_fun_facts(
            total_dist=total_dist,
            total_dplus=total_dplus,
            total_duree=total_duree,
            total_seances=total_seances,
        )

        # 6. Annonces marquantes ("OMG", Marathons cumulés, D+ monumental)
        announcements: List[str] = []
        nb_marathons = int(total_dist // 42.195)
        if nb_marathons >= 10:
            announcements.append(f"🔥 OMG ! Tu as couru l'équivalent de {nb_marathons} marathons complets ! C'est monumental !")
        elif nb_marathons >= 5:
            announcements.append(f"🔥 Déjà {nb_marathons} marathons complets cumulés dans les jambes ! Quelle régularité !")
        elif nb_marathons >= 1:
            announcements.append(f"🏅 Tu as cumulé l'équivalent de {nb_marathons} marathon{'s' if nb_marathons > 1 else ''} entier{'s' if nb_marathons > 1 else ''} ({total_dist:.1f} km) !")

        if total_dplus >= 10000:
            announcements.append(f"👑 Défi Titanesque : Tu as franchi le cap mythique des {int(total_dplus // 10000) * 10000:,} m de D+ cumulés !".replace(",", " "))
        elif total_dplus >= 5000:
            announcements.append(f"⛰️ Plus de {int(total_dplus // 1000) * 1000:,} m de dénivelé positif gravi !".replace(",", " "))

        if total_dist >= 1000:
            announcements.append(f"💎 Cap Historique : Tu as franchi les {int(total_dist // 1000) * 1000:,} km cumulés !".replace(",", " "))

        # 7. Annonce du jour / Mot d'Otis (Daily Spotlight contextuel)
        daily_spotlight = self._compute_daily_spotlight(
            sessions=sessions,
            total_dist=total_dist,
            ref_today=ref_today,
            imminent=imminent,
            announcements=announcements,
            fun_facts=fun_facts,
        )

        next_target_msg = imminent[0].message if imminent else None

        return SportGamificationSummary(
            badges=badges,
            unlocked_count=unlocked_count,
            total_badges=total_badges,
            personal_records=prs,
            fun_facts=fun_facts,
            imminent_milestones=imminent,
            announcements=announcements,
            daily_spotlight=daily_spotlight,
            next_target_message=next_target_msg,
        )

    def _compute_personal_records(self, realised: List[SportSession]) -> List[PersonalRecord]:
        """Extrait les records personnels remarquables."""
        prs: List[PersonalRecord] = []

        # Sortie la plus longue
        runs = [s for s in realised if s.distance_km and s.distance_km > 0]
        if runs:
            longest = max(runs, key=lambda s: s.distance_km or 0.0)
            prs.append(
                PersonalRecord(
                    record_type="longest_run",
                    title="Plus Longue Sortie",
                    value=float(longest.distance_km or 0.0),
                    formatted_value=f"{longest.distance_km} km",
                    date=longest.date,
                    session_type=longest.type_seance.value if longest.type_seance else None,
                )
            )
        else:
            prs.append(
                PersonalRecord(
                    record_type="longest_run",
                    title="Plus Longue Sortie",
                    value=0.0,
                    formatted_value="-",
                )
            )

        # Dénivelé max sur une séance
        elevations = [s for s in realised if s.denivele_d_plus and s.denivele_d_plus > 0]
        if elevations:
            max_dplus = max(elevations, key=lambda s: s.denivele_d_plus or 0)
            prs.append(
                PersonalRecord(
                    record_type="max_elevation",
                    title="Plus Gros Dénivelé (D+)",
                    value=float(max_dplus.denivele_d_plus or 0),
                    formatted_value=f"{max_dplus.denivele_d_plus} m D+",
                    date=max_dplus.date,
                    session_type=max_dplus.type_seance.value if max_dplus.type_seance else None,
                )
            )
        else:
            prs.append(
                PersonalRecord(
                    record_type="max_elevation",
                    title="Plus Gros Dénivelé (D+)",
                    value=0.0,
                    formatted_value="-",
                )
            )

        # Meilleure allure sur une sortie de course (>= 3 km pour être significatif)
        paced_runs = [
            s for s in runs
            if s.allure_secondes and s.allure_secondes > 0 and (s.distance_km or 0) >= 3.0
            and s.type_seance != SportSessionType.RENFORCEMENT
        ]
        if paced_runs:
            fastest = min(paced_runs, key=lambda s: s.allure_secondes or 999999)
            prs.append(
                PersonalRecord(
                    record_type="best_pace",
                    title="Allure Record (≥3 km)",
                    value=float(fastest.allure_secondes or 0),
                    formatted_value=f"{fastest.allure_formatted or format_pace(fastest.allure_secondes)} /km",
                    date=fastest.date,
                    session_type=fastest.type_seance.value if fastest.type_seance else None,
                )
            )
        else:
            prs.append(
                PersonalRecord(
                    record_type="best_pace",
                    title="Allure Record (≥3 km)",
                    value=0.0,
                    formatted_value="-",
                )
            )

        return prs

    def _evaluate_badges(
        self,
        realised: List[SportSession],
        total_dist: float,
        total_dplus: int,
        total_duree: int,
        total_seances: int,
        total_renfo: int,
    ) -> List[SportBadge]:
        """Évalue l'ensemble des badges du catalogue."""
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

        # --- BADGES POP-CULTURE (Astérix Otis, Seigneur des Anneaux, Roshar) ---
        # 1. Astérix & Obélix : Mission Cléopâtre (Otis)
        # Situation
        otis_sit_unlocked = any("situation" in (s.remarques or "").lower() or "rencontre" in (s.remarques or "").lower() for s in realised)
        badges.append(
            SportBadge(
                id="pop_otis_situation",
                title="Pas de Bonne ou Mauvaise Situation 📜",
                description="Vous savez, moi je ne crois pas qu'il y ait de bonne ou de mauvaise situation...",
                icon="📜",
                category=BadgeCategory.POP_CULTURE,
                is_unlocked=otis_sit_unlocked,
                rarity="or",
            )
        )

        # Pierres & Construction
        otis_pierres_unlocked = any(
            any(w in (s.remarques or "").lower() for w in ["pierre", "construction", "dalle", "chantier"])
            for s in realised
        )
        badges.append(
            SportBadge(
                id="pop_otis_pierres",
                title="Pas de Pierres, Pas de Construction ! 🏛️",
                description="Quand on n'a pas de pierres, on ne peut pas construire... mais on peut faire du renfo !",
                icon="🏛️",
                category=BadgeCategory.POP_CULTURE,
                is_unlocked=otis_pierres_unlocked,
                rarity="bronze",
            )
        )

        # Lion mort
        otis_lion_unlocked = any(
            any(w in (s.remarques or "").lower() for w in ["lion", "désert", "desert", "chaleur écrasante"])
            for s in realised
        )
        badges.append(
            SportBadge(
                id="pop_otis_lion",
                title="Un Lion Mort dans le Désert 🦁",
                description="Courir sous un soleil de plomb digne d'Alexandrie !",
                icon="🦁",
                category=BadgeCategory.POP_CULTURE,
                is_unlocked=otis_lion_unlocked,
                rarity="argent",
            )
        )

        # Scribe d'Alexandrie (notes longues > 25 mots)
        otis_scribe_unlocked = any(len((s.remarques or "").split()) >= 25 for s in realised)
        badges.append(
            SportBadge(
                id="pop_otis_scribe",
                title="Le Scribe d'Alexandrie ✍️",
                description="Rédiger un véritable monologue inspiré dans les remarques de séance !",
                icon="✍️",
                category=BadgeCategory.POP_CULTURE,
                is_unlocked=otis_scribe_unlocked,
                rarity="argent",
            )
        )

        # Deuxième porte à gauche
        otis_porte_unlocked = any(
            (s.allure_secondes and s.allure_secondes < 300) or ("porte" in (s.remarques or "").lower())
            for s in realised
        )
        badges.append(
            SportBadge(
                id="pop_otis_porte_gauche",
                title="Deuxième Porte à Gauche 🚪",
                description="Filez vite ! Séance avec grosse pointe de vitesse ou passage de porte.",
                icon="🚪",
                category=BadgeCategory.POP_CULTURE,
                is_unlocked=otis_porte_unlocked,
                rarity="bronze",
            )
        )

        # Itinéris ne capte plus
        otis_itineris_unlocked = any(
            any(w in (s.remarques or "").lower() for w in ["calme", "déconnexion", "sans musique", "nature", "forêt"])
            for s in realised
        )
        badges.append(
            SportBadge(
                id="pop_otis_itineris",
                title="Itinéris ne Capte Plus 📵",
                description="Courir déconnecté du réseau en pleine nature !",
                icon="📵",
                category=BadgeCategory.POP_CULTURE,
                is_unlocked=otis_itineris_unlocked,
                rarity="bronze",
            )
        )

        # 2. Le Seigneur des Anneaux (LOTR)
        # Road to Mordor (trajet de Frodon : 2 850 km cumulés)
        mordor_target = 2850.0
        mordor_unlocked = total_dist >= mordor_target
        badges.append(
            SportBadge(
                id="pop_lotr_mordor",
                title="Road to Mordor 🌋 (2 850 km)",
                description="Parcourir à pied la distance exacte reliant Cul-de-Sac à la Montagne du Destin !",
                icon="🌋",
                category=BadgeCategory.POP_CULTURE,
                is_unlocked=mordor_unlocked,
                current_value=total_dist,
                target_value=mordor_target,
                unit="km",
                progress_pct=min(100, int((total_dist / mordor_target) * 100)),
                rarity="mythique",
            )
        )

        # Deuxième petit-déjeuner
        lotr_dej_unlocked = any(
            any(w in (s.remarques or "").lower() for w in ["petit-déjeuner", "petit dejeuner", "faim", "croissant"])
            for s in realised
        )
        badges.append(
            SportBadge(
                id="pop_lotr_second_dejeuner",
                title="Le Deuxième Petit-Déjeuner 🥐",
                description="Rentrer de sortie le ventre affamé comme un Hobbit affamé !",
                icon="🥐",
                category=BadgeCategory.POP_CULTURE,
                is_unlocked=lotr_dej_unlocked,
                rarity="bronze",
            )
        )

        # En route pour Fondcombe (135 km)
        fondcombe_target = 135.0
        fondcombe_unlocked = total_dist >= fondcombe_target
        badges.append(
            SportBadge(
                id="pop_lotr_fondcombe",
                title="En Route pour Fondcombe 🧝 (135 km)",
                description="La distance de Hobbitebourg au refuge d'Elrond franchie en baskets !",
                icon="🧝",
                category=BadgeCategory.POP_CULTURE,
                is_unlocked=fondcombe_unlocked,
                current_value=total_dist,
                target_value=fondcombe_target,
                unit="km",
                progress_pct=min(100, int((total_dist / fondcombe_target) * 100)),
                rarity="argent",
            )
        )

        # Vous ne passerez pas ! (D+ > 200m d'un coup ou remarque)
        passerez_unlocked = any(
            (s.denivele_d_plus and s.denivele_d_plus >= 200) or ("passerez pas" in (s.remarques or "").lower())
            for s in realised
        )
        badges.append(
            SportBadge(
                id="pop_lotr_vous_ne_passerez_pas",
                title="Vous Ne Passerez Pas ! 🧙",
                description="Barrer la route au dénivelé sur une ascension redoutable !",
                icon="🧙",
                category=BadgeCategory.POP_CULTURE,
                is_unlocked=passerez_unlocked,
                rarity="argent",
            )
        )

        # L'Anneau Unique (boucle parfaite)
        anneau_unlocked = any(
            any(w in (s.remarques or "").lower() for w in ["boucle", "anneau", "tour du lac", "circuit"])
            for s in realised
        )
        badges.append(
            SportBadge(
                id="pop_lotr_anneau_unique",
                title="L'Anneau Unique 💍",
                description="Boucler un parcours en boucle parfaite sans faire demi-tour !",
                icon="💍",
                category=BadgeCategory.POP_CULTURE,
                is_unlocked=anneau_unlocked,
                rarity="argent",
            )
        )

        # Pas un orque en vue
        orque_unlocked = any(
            any(w in (s.remarques or "").lower() for w in ["brouillard", "brume", "seul", "nappe"])
            for s in realised
        )
        badges.append(
            SportBadge(
                id="pop_lotr_pas_un_orque",
                title="Pas un Orque en Vue 🌫️",
                description="Courir dans la brume matinale enveloppé dans le silence.",
                icon="🌫️",
                category=BadgeCategory.POP_CULTURE,
                is_unlocked=orque_unlocked,
                rarity="bronze",
            )
        )

        # 3. Brandon Sanderson - Les Archives de Roshar
        # Pont Quatre (Bridge Four - RPE 9 ou 10)
        pont4_unlocked = any(
            (s.ressenti_rpe and s.ressenti_rpe >= 9) or ("pont quatre" in (s.remarques or "").lower() or "bridge four" in (s.remarques or "").lower())
            for s in realised
        )
        badges.append(
            SportBadge(
                id="pop_roshar_pont_quatre",
                title="Pont Quatre (Bridge Four) 🪵",
                description="La vie avant la mort, la force avant la faiblesse : surmonter une séance extrême à RPE 9 ou 10 !",
                icon="🪵",
                category=BadgeCategory.POP_CULTURE,
                is_unlocked=pont4_unlocked,
                rarity="or",
            )
        )

        # Haute-Tempête (courir sous la pluie / tempête / déluge)
        tempete_unlocked = any(
            any(w in (s.remarques or "").lower() for w in ["haute-tempête", "haute-tempete", "déluge", "deluge", "tempête", "orage"])
            for s in realised
        )
        badges.append(
            SportBadge(
                id="pop_roshar_haute_tempete",
                title="Au Cœur de la Haute-Tempête ⚡",
                description="Affronter le cataclysme en baskets et en sortir victorieux !",
                icon="⚡",
                category=BadgeCategory.POP_CULTURE,
                is_unlocked=tempete_unlocked,
                rarity="or",
            )
        )

        # Marcheur du Vent (Windrunner - vitesse ou rafales)
        wind_unlocked = any(
            (s.vitesse_kmh and s.vitesse_kmh >= 12.0) or any(w in (s.remarques or "").lower() for w in ["marcheur du vent", "rafales", "voler", "vent de dos"])
            for s in realised
        )
        badges.append(
            SportBadge(
                id="pop_roshar_marcheur_du_vent",
                title="Marcheur du Vent (Windrunner) 💨",
                description="Fendre l'air avec fluidité et vitesse sur le bitume !",
                icon="💨",
                category=BadgeCategory.POP_CULTURE,
                is_unlocked=wind_unlocked,
                rarity="argent",
            )
        )

        # Danseur de Pierre (Stoneward - sentier / cailloux / D+)
        stone_unlocked = any(
            any(w in (s.remarques or "").lower() for w in ["danseur de pierre", "cailloux", "rocher", "roc", "sentier"])
            for s in realised
        )
        badges.append(
            SportBadge(
                id="pop_roshar_danseur_de_pierre",
                title="Danseur de Pierre (Stoneward) 🪨",
                description="Fouler le roc avec la solidité inébranlable d'un radiant !",
                icon="🪨",
                category=BadgeCategory.POP_CULTURE,
                is_unlocked=stone_unlocked,
                rarity="argent",
            )
        )

        # Les Idéaux des Radiants (séances consécutives ou persévérance)
        ideaux_unlocked = total_seances >= 15 or any("idéaux" in (s.remarques or "").lower() or "serment" in (s.remarques or "").lower() for s in realised)
        badges.append(
            SportBadge(
                id="pop_roshar_ideaux_radieux",
                title="Les Idéaux des Radiants 🛡️",
                description="Le voyage avant la destination : 15 séances d'engagement loyal !",
                icon="🛡️",
                category=BadgeCategory.POP_CULTURE,
                is_unlocked=ideaux_unlocked,
                rarity="or",
            )
        )

        # Infusion de Fulgurance (allure record ou énergie)
        fulgurance_unlocked = any(
            (s.allure_secondes and s.allure_secondes <= 315) or ("fulgurance" in (s.remarques or "").lower())
            for s in realised
        )
        badges.append(
            SportBadge(
                id="pop_roshar_fulgurance",
                title="Infusion de Fulgurance 💎",
                description="Briller d'une énergie éclatante sur une séance rapide !",
                icon="💎",
                category=BadgeCategory.POP_CULTURE,
                is_unlocked=fulgurance_unlocked,
                rarity="argent",
            )
        )

        # Le Spren de la Douleur
        spren_unlocked = any(
            any(w in (s.remarques or "").lower() for w in ["spren", "mental", "dur", "au mental", "tenu bon"])
            for s in realised
        )
        badges.append(
            SportBadge(
                id="pop_roshar_spren_douleur",
                title="Le Spren de la Douleur 👹",
                description="Triompher de l'inconfort et transformer l'effort en victoire pure !",
                icon="👹",
                category=BadgeCategory.POP_CULTURE,
                is_unlocked=spren_unlocked,
                rarity="bronze",
            )
        )

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

    def _detect_imminent_milestones(self, badges: List[SportBadge]) -> List[ImminentMilestone]:
        """Détecte les badges sur le point d'être débloqués pour injecter de la motivation."""
        imminent: List[ImminentMilestone] = []

        for b in badges:
            if b.is_unlocked or not b.target_value:
                continue

            # Pour la distance : à moins de 15 km du cap
            if b.category == BadgeCategory.DISTANCE:
                rem = round(b.target_value - b.current_value, 1)
                if 0 < rem <= 15.0:
                    imminent.append(
                        ImminentMilestone(
                            badge_id=b.id,
                            title=b.title,
                            remaining=rem,
                            unit="km",
                            message=f"Plus que {rem} km avant le cap '{b.title}' ! C'est peut-être pour aujourd'hui !",
                        )
                    )

            # Pour le D+ : à moins de 100 m du cap
            elif b.category == BadgeCategory.DENIVELE:
                rem_m = round(b.target_value - b.current_value, 0)
                if 0 < rem_m <= 100.0:
                    imminent.append(
                        ImminentMilestone(
                            badge_id=b.id,
                            title=b.title,
                            remaining=rem_m,
                            unit="m",
                            message=f"Plus que {int(rem_m)} m de dénivelé avant le badge '{b.title}' !",
                        )
                    )

        return imminent

    def _compute_daily_spotlight(
        self,
        sessions: List[SportSession],
        total_dist: float,
        ref_today: dt_date,
        imminent: List[ImminentMilestone],
        announcements: List[str],
        fun_facts: List[SportFunFact],
    ) -> Optional[str]:
        """Génère l'annonce phare du jour ou de fin de séance (Coach Otis)."""
        # 1. Vérifier si une séance est prévue aujourd'hui et fait franchir un palier de 100 km ou un jalon majeur
        today_planned = [
            s for s in sessions
            if s.date == ref_today and s.statut == SportSessionStatus.PLANIFIE
        ]
        if today_planned:
            planned_dist = sum(s.distance_km or 0.0 for s in today_planned)
            if planned_dist > 0:
                future_dist = total_dist + planned_dist
                current_hundred = int(total_dist // 100)
                future_hundred = int(future_dist // 100)
                if future_hundred > current_hundred:
                    cap = future_hundred * 100
                    return (
                        f"📢 Annonce du jour : Aujourd'hui, avec ta séance de {planned_dist:.1f} km prévue, "
                        f"on passe le cap des {cap} km cumulés ! C'est génial, donne tout !"
                    )
                # Vérifier si on franchit les 10 km ou le marathon
                if total_dist < 10.0 and future_dist >= 10.0:
                    return (
                        f"📢 Annonce du jour : Aujourd'hui avec ta séance de {planned_dist:.1f} km, "
                        "on passe le cap des 10 km cumulés ! Superbe étape !"
                    )
                if total_dist < 42.2 and future_dist >= 42.2:
                    return (
                        f"📢 Annonce du jour : Aujourd'hui avec ta séance de {planned_dist:.1f} km, "
                        "on franchit la distance mythique du Marathon cumulé (42.2 km) !"
                    )

        # 2. Vérifier si une séance réalisée aujourd'hui vient tout juste de faire franchir un cap
        today_done = [
            s for s in sessions
            if s.date == ref_today and s.statut == SportSessionStatus.REALISE
        ]
        if today_done:
            today_dist = sum(s.distance_km or 0.0 for s in today_done)
            prev_dist = max(0.0, total_dist - today_dist)
            current_hundred = int(total_dist // 100)
            prev_hundred = int(prev_dist // 100)
            if current_hundred > prev_hundred and current_hundred > 0:
                cap = current_hundred * 100
                return (
                    f"🎉 Fin de séance mémorable : Aujourd'hui on a passé le cap des {cap} km cumulés ! "
                    "C'est génial, félicitations pour ton engagement !"
                )

        # 3. Palier imminent (à moins de 15 km)
        if imminent:
            imm = imminent[0]
            return f"🎯 En ligne de mire : Plus que {imm.remaining:.1f} km avant de débloquer '{imm.title}' ! Prêt pour le défi ?"

        # 4. Annonce marquante (OMG, marathons cumulés, D+ colossal)
        if announcements:
            return announcements[0]

        # 5. Anecdote insolite du jour
        if fun_facts:
            chosen = next((f for f in fun_facts if f.category in ("vertical", "geo", "energy")), fun_facts[0])
            return f"💡 L'anecdote du jour : {chosen.text}"

        return "🏃 Chaque foulée compte ! Prêt à repousser tes limites aujourd'hui ?"

    def _generate_fun_facts(
        self,
        total_dist: float,
        total_dplus: int,
        total_duree: int,
        total_seances: int,
    ) -> List[SportFunFact]:
        """Génère des anecdotes ludiques et des équivalences mémorables."""
        facts: List[SportFunFact] = []

        # 1. Équivalence verticale (D+)
        eiffel_count = round(total_dplus / 300.0, 1) if total_dplus > 0 else 0
        if eiffel_count >= 1.0:
            facts.append(
                SportFunFact(
                    id="fact_vertical_eiffel",
                    title="Ascension Verticale",
                    text=f"Avec tes {total_dplus} m de D+ cumulés, tu as grimpé l'équivalent de {eiffel_count} fois la Tour Eiffel !",
                    icon="🗼",
                    category="vertical",
                )
            )
        else:
            facts.append(
                SportFunFact(
                    id="fact_vertical_eiffel_intro",
                    title="Ascension Verticale",
                    text=f"Déjà {total_dplus} m de dénivelé positif gravi ! La Tour Eiffel culmine à 300 m.",
                    icon="⛰️",
                    category="vertical",
                )
            )

        # 2. Équivalences géographiques
        if total_dist >= 180:
            facts.append(
                SportFunFact(
                    id="fact_geo_gr20",
                    title="Traversée Mythique",
                    text=f"Tes {total_dist} km dépassent la distance intégrale du mythique GR20 en Corse (180 km) !",
                    icon="🏝️",
                    category="geo",
                )
            )
        elif total_dist >= 90:
            facts.append(
                SportFunFact(
                    id="fact_geo_chartres",
                    title="Échappée Régionale",
                    text=f"Tes {total_dist} km te permettraient de rallier Paris à la cathédrale de Chartres à pied !",
                    icon="🏰",
                    category="geo",
                )
            )
        elif total_dist >= 40:
            facts.append(
                SportFunFact(
                    id="fact_geo_annecy",
                    title="Liaison Alpine",
                    text=f"Tes {total_dist} km représentent la liaison directe d'une seule traite entre Annecy et Genève (42 km) !",
                    icon="🏔️",
                    category="geo",
                )
            )
        else:
            facts.append(
                SportFunFact(
                    id="fact_geo_start",
                    title="Sur la Route",
                    text=f"Déjà {total_dist} km d'asphalte et de sentiers au compteur !",
                    icon="🗺️",
                    category="geo",
                )
            )

        # 3. Équivalence énergétique (croissants / pizzas)
        # Estimation classique : 65 kcal par km de course à pied
        approx_kcal = int(total_dist * 65)
        croissants = round(approx_kcal / 400.0, 1)
        facts.append(
            SportFunFact(
                id="fact_energy_croissants",
                title="Carburant & Calories",
                text=f"Tes sorties représentent environ {approx_kcal:,} kcal brûlées, soit l'équivalent énergétique de {croissants} croissants pur beurre !".replace(",", " "),
                icon="🥐",
                category="energy",
            )
        )

        # 4. Équivalence cosmique / absurde
        moon_dist = 384400.0
        rem_moon = int(moon_dist - total_dist)
        facts.append(
            SportFunFact(
                id="fact_absurd_moon",
                title="Objectif Alunissage",
                text=f"Plus que {rem_moon:,} km avant de poser tes baskets sur la surface de la Lune !".replace(",", " "),
                icon="🚀",
                category="cosmique",
            )
        )

        return facts

    def get_morning_chronicle_snippet(self, summary: SportGamificationSummary) -> str:
        """Génère une phrase punchy et motivante pour la chronique matinale ou le coach.
        
        Priorités :
        1. Palier imminent si disponible (dopamine immédiate : 'Allez, plus que X km...').
        2. Anecdote insolite ou équivalence fun.
        """
        if summary.imminent_milestones:
            imm = summary.imminent_milestones[0]
            return f"🎯 Défi du jour : {imm.message}"

        if summary.fun_facts:
            # Choisir une anecdote marquante (verticale, géo ou croissants)
            top_facts = [f for f in summary.fun_facts if f.category in ("vertical", "geo", "energy")]
            chosen = top_facts[0] if top_facts else summary.fun_facts[0]
            return f"{chosen.icon} Le savais-tu ? {chosen.text}"

        return "🏃 Belle journée sportive à toi !"
