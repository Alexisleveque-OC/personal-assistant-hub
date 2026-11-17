"""Service de gamification, détection de records personnels (PRs), badges et anecdotes sportives (Otis)."""
from datetime import date as dt_date
from typing import Dict, List, Optional

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
from app.core.sport_equivalences import daily_equivalences
from app.core.sport_fun_badges import evaluate_fun_badges
from app.core.sport_pop_badges import evaluate_pop_badges
from app.core.sport_secret_badges import evaluate_secret_badges
from app.core.sport_tier_badges import evaluate_tier_badges


class SportGamificationService:
    """Moteur pur d'évaluation des accomplissements, des records et des équivalences fun."""

    def __init__(self) -> None:
        self._unlock_cache: Optional[tuple] = None

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

        self._stamp_unlock_dates(realised, badges)
        unlocked_count = sum(1 for b in badges if b.is_unlocked)
        total_badges = len(badges)

        # 4. Paliers imminents (doses de dopamine & motivation)
        imminent = self._detect_imminent_milestones(badges)

        # 5. Anecdotes et équivalences insolites
        fun_facts = daily_equivalences(total_km=total_dist, total_dplus=total_dplus, day=ref_today)

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

    def _badges_for(self, realised: List[SportSession]) -> List[SportBadge]:
        """Évalue les badges sur un ensemble de séances réalisées (utilisé pour rejouer l'historique)."""
        return self._evaluate_badges(
            realised=realised,
            total_dist=round(sum(s.distance_km or 0.0 for s in realised), 2),
            total_dplus=sum(s.denivele_d_plus or 0 for s in realised),
            total_duree=sum(s.duree_secondes or 0 for s in realised),
            total_seances=len(realised),
            total_renfo=sum(1 for s in realised if s.type_seance == SportSessionType.RENFORCEMENT),
        )

    def _stamp_unlock_dates(self, realised: List[SportSession], badges: List[SportBadge]) -> None:
        """Date de déblocage = jour de la séance qui a fait basculer le badge (rien n'est stocké).

        Les badges ne dépendent que des séances réalisées : on rejoue l'historique jour par jour.
        Un badge qui se reverrouille (séance modifiée) puis se redébloque prend la date du dernier basculement.
        """
        unlocked_ids = {b.id for b in badges if b.is_unlocked}
        if not unlocked_ids:
            return
        ordered = sorted(realised, key=lambda s: (s.date, s.id or 0))
        # Cache à une entrée : la clé est le contenu des séances, toute modification l'invalide.
        cache_key = tuple(s.model_dump_json() for s in ordered)
        if self._unlock_cache is None or self._unlock_cache[0] != cache_key:
            self._unlock_cache = (cache_key, self._replay_unlock_dates(ordered, unlocked_ids))
        since = self._unlock_cache[1]
        for badge in badges:
            if badge.id in since:
                badge.unlocked_at = since[badge.id].isoformat()

    def _replay_unlock_dates(self, ordered: List[SportSession], unlocked_ids: set) -> Dict[str, dt_date]:
        since: Dict[str, dt_date] = {}
        for day in sorted({s.date for s in ordered}):
            prefix = [s for s in ordered if s.date <= day]
            unlocked_now = {b.id for b in self._badges_for(prefix) if b.is_unlocked}
            for badge_id in unlocked_ids:
                if badge_id in unlocked_now:
                    since.setdefault(badge_id, day)
                else:
                    since.pop(badge_id, None)
        return since

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
        """Évalue l'ensemble des badges du catalogue, toujours dans le même ordre."""
        badges = evaluate_tier_badges(realised, total_dist, total_dplus, total_duree, total_renfo)
        badges.extend(evaluate_pop_badges(realised, total_dist, total_seances))
        badges.extend(evaluate_secret_badges(realised, total_dist))

        # Trophées pop-culture et secrets ajoutés le 16/11 (module dédié)
        badges.extend(evaluate_fun_badges(realised))
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
