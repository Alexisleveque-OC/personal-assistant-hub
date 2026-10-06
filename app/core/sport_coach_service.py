"""Service d'intelligence de coaching running et de planification hebdomadaire proactive (Étape 6)."""
from datetime import date, timedelta
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional
import httpx

from app.config import settings
from app.connectors.sheets.sport_connector import SportConnector
from app.connectors.sheets.sport_models import (
    SportPlannedSessionProposal,
    SportSession,
    SportSessionStatus,
    SportSessionType,
    SportWeeklyPlanProposal,
    SportWeeklySummary,
    format_pace,
)
from app.core.llm.gemini_client import (
    GEMINI_API_BASE_URL,
    GeminiClient,
    get_gemini_client,
)

logger = logging.getLogger(__name__)

SPORT_COACH_SYSTEM_PROMPT = """Tu es Otis, le coach personnel d'Alexis en course à pied et renforcement musculaire.
Tu es un expert bienveillant, scientifique, attentif et protecteur contre les blessures (notamment la périostite tibiale).

DÉCISION AUTOMATIQUE SEMAINE NORMALE VS SEMAINE DE REPOS (DELOAD) :
C'est à toi (Otis) de déterminer intelligemment si la semaine doit être normale ou de repos :
- Semaine de repos / décharge (3 séances) : Si l'analyse des séances récentes montre des RPE élevés (RPE >= 8), une charge excessive, ou des mentions de douleurs (périostite, tibia, mollet) dans les remarques ou notes, OU si Alexis demande expressément du repos. Tu dois alors expliquer clairement pourquoi le repos est nécessaire pour régénérer le corps.
- Semaine normale (4 séances) : Si Alexis n'a pas trop forcé sur les points RPE (RPE modérés <= 7) et qu'aucune douleur n'est signalée. Ne pas appliquer de règle mécanique rigide (ex: 3 semaines puis repos automatique) : c'est l'écoute du corps et les données réelles (RPE, douleurs, sensations) qui priment.

CALIBRAGE STRICT DES SÉANCES ET DURÉES :
1. Endurance Fondamentale (EF) :
   - DURÉE STRICTE : Entre 30 et 35 minutes environ (JAMAIS 8 km !).
   - Distance typique : entre 4,5 km et 5,5 km selon l'allure d'Alexis.
   - Allure aisance respiratoire (Zone 2), sol souple / sous-bois fortement recommandé pour préserver les tibias.
2. Sortie Longue (SL) :
   - DURÉE STRICTE : Environ 1 heure (1h / 60 minutes).
   - Distance typique : entre 8,5 km et 10 km max.
   - Allure Zone 2 identique à l'EF (ne JAMAIS prévoir une EF plus lente que la SL : sur 1h comme sur 30 min, la base reste l'aisance respiratoire stricte pour préserver les tibias).
3. Fractionné (Lundi) :
   - DURÉE STRICTE : Entre 30 et 35 minutes au total (échauffement 10-15 min + blocs d'intervalles type 300m/400m + 5-10 min retour au calme).
   - Distance totale : environ 5 à 5,5 km.
4. Renforcement musculaire & PPG (Mardi) - PRESCRIPTION CHIRURGICALE SANS JARGON MÉDICAL :
   - VULGARISATION STRICTE (ZÉRO JARGON KINÉ INCOMPRÉHENSIBLE) :
     Alexis n'est pas kiné et ne connaît pas les termes anatomiques obscurs comme "soléaires" ou "gastrocnémiens".
     Prohibition totale du jargon médical brut ! Tu dois obligatoirement utiliser des descriptions concrètes, visuelles et vulgarisées que tout coureur comprend immédiatement :
     * Mardi normal (30 min renfo périostite & fessiers) :
       "1. Descente de mollets sur une marche (jambes tendues) : 3x15 réps (montée 2 pieds, descente lente freinée 3s sur 1 jambe, repos 1min) | 2. Mollets bas & tendons sur marche (genoux pliés à 45°) : 3x15 réps (descente freinée 3s) | 3. Pont fessier au sol sur 1 jambe : 3x12 réps/jambe | 4. Gainage planche ventrale et sur les côtés : 3x45s"
     * Mardi repos (25-30 min mobilité & décharge) :
       "1. Massage sous la voûte plantaire avec une balle : 3 min/côté | 2. Étirement du mollet bas contre le mur (genou plié, talon au sol) : 3x30s sans à-coup | 3. Étirement du mollet haut contre le mur (jambe arrière tendue, talon au sol) : 3x30s | 4. Mobilisation douce des chevilles et chaîne postérieure"

MARGE DE PROGRESSION ET ALLURES CIBLES (+/-) :
- Pour chaque course (Fractionné, EF, Sortie Longue), tu DOIS obligatoirement indiquer son allure cible ET sa vitesse cible avec une marge de tolérance (+/-) pour jauger les sensations et la progression :
  Ex : "06:20/km (+/- 15s)" et "9.5 km/h (+/- 0.4 km/h)" sur l'EF de jeudi.
  Ex : "06:20/km (+/- 15s)" et "9.5 km/h (+/- 0.4 km/h)" sur la SL de samedi (même plage Zone 2 que l'EF !).
  Ex : "04:15/km (+/- 10s)" et "14.1 km/h (+/- 0.5 km/h)" sur les répétitions rapides du fractionné.
- Dans `spoken_summary` : mentionne clairement les allures et vitesses cibles pour les séances clés de running afin qu'Alexis ait ses repères à l'oral.

SYNTHÈSE HEBDOMADAIRE MULTICRITÈRE & PROGRESSION GÉNÉRALE :
Alexis analyse sa progression sur 3 axes fondamentaux :
1. Évolution du volume (Km-effort) vs S-1
2. Évolution de la vitesse moyenne vs S-1
3. Évolution de la charge interne RPE vs S-1
Progression Générale = moyenne de ces 3 évolutions.
ATTENTION : Une progression en volume faible (ex: +1.8% en S40) peut cacher une explosion de la charge interne RPE (+34.5%) et de la vitesse (+4.3%), amenant une Progression Générale de +13.5% qui explique la fatigue ou le réveil d'une périostite tibiale !
Tu DOIS impérativement analyser ces données dans `analyse_historique` et en tenir compte pour décider du repos ou du dosage des séances futures.

RÈGLES D'OR DE STRUCTURE :
1. Semaine Normale (4 séances obligatoires) :
   - Lundi : Fractionné (~30-35 min, ~5 km, échauffement + intervalles avec allure cible +/- + RAC)
   - Mardi : Renforcement musculaire kiné (30 min, distance = null)
   - Jeudi : EF (30 à 35 min, ~4.5 à 5.5 km, allure cible +/- sur sol souple)
   - Samedi : Sortie Longue (~1h / 60 min, ~8.5 à 10 km max, allure progressive +/-)

2. Semaine de Repos / Décharge (3 séances obligatoires) :
   - Mardi : Renforcement étirements & mobilité douce (25-30 min, distance = null)
   - Jeudi : EF récupération (environ 30 min, ~4.5 km, allure très tranquille +/-)
   - Samedi : Sortie Longue allégée (~45-50 min, ~7 à 8 km, allure très souple)

RÈGLES PHYSIOLOGIQUES ET SÉCURITÉ :
- Règle des +10% max en km-effort : Le total prévisionnel de la semaine ne doit jamais augmenter de plus de 10% par rapport à la semaine précédente.
- Conseil périostite tibiale : Toujours inclure un conseil spécifique (sol souple, herbe, glaçage, étirement soléaires).
- Souhaits d'Alexis : Si Alexis formule un souhait (ex: "je veux faire 15 km samedi"), analyse-le avec ton œil de coach : valide-le ou préviens-le avec bienveillance dans `avis_sur_souhaits_alexis` s'il dépasse les limites de sécurité.
- Ton oral concis : Génère un résumé oral direct, motivant et complice dans `spoken_summary` (2 phrases max).
"""

GEMINI_WEEKLY_PLAN_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "semaine": {"type": "INTEGER"},
        "annee": {"type": "INTEGER"},
        "est_semaine_repos": {"type": "BOOLEAN"},
        "analyse_historique": {"type": "STRING"},
        "km_effort_total_prevu": {"type": "NUMBER"},
        "plafond_recommande": {"type": "NUMBER"},
        "respecte_regle_10_pct": {"type": "BOOLEAN"},
        "conseil_blessure_periostite": {"type": "STRING"},
        "seances": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "jour": {"type": "STRING", "enum": ["Lundi", "Mardi", "Jeudi", "Samedi"]},
                    "type_seance": {
                        "type": "STRING",
                        "enum": ["Fractionné", "Renforcement", "EF", "Sortie Longue", "Seuil", "Récup"],
                    },
                    "distance_km": {"type": "NUMBER"},
                    "duree_minutes": {"type": "INTEGER"},
                    "allure_cible": {"type": "STRING"},
                    "vitesse_cible": {"type": "STRING"},
                    "programme": {"type": "STRING"},
                    "remarques_coach": {"type": "STRING"},
                },
                "required": ["jour", "type_seance", "duree_minutes", "programme"],
            },
        },
        "avis_sur_souhaits_alexis": {"type": "STRING"},
        "spoken_summary": {"type": "STRING"},
    },
    "required": [
        "semaine",
        "annee",
        "est_semaine_repos",
        "analyse_historique",
        "km_effort_total_prevu",
        "plafond_recommande",
        "respecte_regle_10_pct",
        "conseil_blessure_periostite",
        "seances",
        "spoken_summary",
    ],
}


EXERCISE_GUIDE: Dict[str, Dict[str, str]] = {
    "mollets_marche": {
        "nom": "Descente de mollets sur une marche (jambes tendues)",
        "objectif": "Renforcer les mollets et tendons d'Achille pour absorber les chocs et soulager la périostite tibiale.",
        "installation": "Place l'avant de tes pieds sur le bord d'une marche d'escalier, les talons dans le vide. Prends appui sur une rampe ou un mur pour l'équilibre.",
        "mouvement": "Monte sur la pointe des deux pieds. Une fois en haut, lève une jambe et descends tout doucement sur le seul pied d'appui jusqu'à sentir le talon descendre sous la marche. Repose les deux pieds pour remonter.",
        "tempo": "Montée dynamique à deux pieds (1s), descente lente et freinée sur un pied en 3 secondes. 3 séries de 15 répétitions par jambe avec 1 minute de repos.",
        "sensations": "Chauffe intense dans le haut et le cœur du mollet, sans douleur aiguë osseuse sur le tibia.",
        "erreurs_a_eviter": "Ne rebondis pas en bas. La descente doit être lente et freinée pour stimuler les fibres tendineuses.",
    },
    "mollets_bas_genoux_plies": {
        "nom": "Mollets bas & tendons sur marche (genoux pliés)",
        "objectif": "Cibler le muscle profond sous le mollet, essentiel pour amortir chaque foulée en course à pied.",
        "installation": "Même position sur le bord de la marche, mais en pliant les deux genoux à environ 45 degrés dès le départ et en les gardant pliés pendant tout l'exercice.",
        "mouvement": "En gardant les genoux pliés, monte sur les pointes de pied, puis descends lentement les talons sous la marche.",
        "tempo": "Descente contrôlée et freinée en 3 secondes. 3 séries de 15 répétitions avec 1 minute de repos.",
        "sensations": "Chauffe profonde et diffuse dans la partie basse du mollet, juste au-dessus de la cheville.",
        "erreurs_a_eviter": "Ne retends pas les jambes ! Garder les genoux pliés est indispensable pour faire travailler le muscle profond protecteur.",
    },
    "pont_fessier": {
        "nom": "Pont fessier au sol sur 1 jambe",
        "objectif": "Renforcer les fessiers pour stabiliser le bassin et éviter que le genou et le tibia ne s'affaissent vers l'intérieur.",
        "installation": "Allongé sur le dos, genoux pliés, pieds à plat au sol. Tends une jambe vers l'avant.",
        "mouvement": "Pousse fort sur le talon du pied au sol pour décoller les fesses jusqu'à aligner la cuisse et le torse. Maintiens 2 secondes en haut puis redescends sans reposer les fesses au sol.",
        "tempo": "Montée dynamique, maintien 2s en haut, descente contrôlée. 3 séries de 10 à 12 répétitions par jambe.",
        "sensations": "Forte contraction de la fesse et de l'arrière de la cuisse.",
        "erreurs_a_eviter": "Ne cambre pas le bas du dos. La poussée doit venir exclusivement de la fesse d'appui.",
    },
    "gainage_planche": {
        "nom": "Gainage planche ventrale et sur les côtés",
        "objectif": "Gainer la sangle abdominale pour garder une posture droite et dynamique même avec la fatigue en fin de sortie.",
        "installation": "En appui sur les avant-bras et la pointe des pieds (ou sur un coude pour la planche sur le côté).",
        "mouvement": "Corps parfaitement rectiligne, nombril rentré, fessiers serrés. Respire calmement.",
        "tempo": "3 séries de 45 secondes en planche ventrale, puis 3 séries de 30 secondes de chaque côté.",
        "sensations": "Tension continue dans les abdominaux profonds.",
        "erreurs_a_eviter": "Ne laisse pas le bassin s'affaisser vers le sol et ne monte pas les fesses en l'air.",
    },
    "etirement_mollet_bas": {
        "nom": "Étirement du mollet bas contre un mur (genou plié)",
        "objectif": "Relâcher la tension sur le tendon et détendre l'attache basse du mollet.",
        "installation": "Face à un mur, mains en appui. Recule la jambe à étirer d'un pas. Fléchis les deux genoux en gardant le talon arrière collé au sol.",
        "mouvement": "Avance doucement le bassin vers le mur tout en gardant le genou arrière plié jusqu'à sentir un étirement au-dessus de la cheville.",
        "tempo": "3 fois 30 secondes par jambe. Respire profondément, sans à-coup.",
        "sensations": "Étirement doux et profond dans le bas du mollet.",
        "erreurs_a_eviter": "Ne décolle pas le talon arrière du sol et ne force pas comme une brute.",
    },
    "etirement_mollet_haut": {
        "nom": "Étirement du mollet haut contre un mur (jambe tendue)",
        "objectif": "Assouplir les gros muscles du mollet après les chocs de la course.",
        "installation": "Face au mur, recule la jambe arrière d'un grand pas, jambe arrière bien tendue et talon au sol.",
        "mouvement": "Plie la jambe avant et avance le bassin vers l'avant jusqu'à sentir l'étirement au cœur du mollet arrière.",
        "tempo": "3 fois 30 secondes par jambe.",
        "sensations": "Tension agréable au cœur du mollet.",
        "erreurs_a_eviter": "Garde les orteils pointés vers le mur, ne tourne pas le pied vers l'extérieur.",
    },
    "massage_voute_balle": {
        "nom": "Massage de la voûte plantaire avec une balle",
        "objectif": "Détendre l'arche du pied qui est directement reliée aux tendons et au périoste tibial.",
        "installation": "Debout ou assis, place une balle (de tennis ou de massage) sous la plante de ton pied nu.",
        "mouvement": "Fais rouler la balle d'avant en arrière sous le pied en appuyant modérément, en insistant sur les zones tendues pendant 2 à 3 minutes.",
        "tempo": "2 à 3 minutes par pied.",
        "sensations": "Décompression et soulagement sous le pied.",
        "erreurs_a_eviter": "N'appuie pas au point de déclencher une douleur aiguë.",
    },
}


class SportCoachService:
    """Service d'intelligence artificielle pour l'analyse d'historique et la planification running proactive."""

    def __init__(
        self,
        connector: SportConnector,
        gemini_client: Optional[GeminiClient] = None,
    ) -> None:
        self.connector = connector
        self.gemini_client = gemini_client or get_gemini_client()

    def explain_exercise(self, exercise_query: str) -> str:
        """Fournit une explication orale claire, structurée et sans jargon médical d'un exercice de renfo ou d'étirement."""
        cleaned = (exercise_query or "").strip().lower()

        # Recherche de correspondance dans le guide
        matched_key = None
        if any(w in cleaned for w in ["marche", "descente", "jambe tendue", "escalier"]) and any(w in cleaned for w in ["mollet", "mollets", "stanish"]):
            matched_key = "mollets_marche"
        elif any(w in cleaned for w in ["mollet bas", "bas du mollet", "genou plié", "genoux pliés", "fléchi", "soléaire", "tendon"]):
            matched_key = "mollets_bas_genoux_plies"
        elif any(w in cleaned for w in ["fessier", "pont", "bassin", "glute"]):
            matched_key = "pont_fessier"
        elif any(w in cleaned for w in ["gainage", "planche", "abdo", "abdominaux"]):
            matched_key = "gainage_planche"
        elif "étirement" in cleaned or "etirement" in cleaned or "étirer" in cleaned or "etirer" in cleaned:
            if any(w in cleaned for w in ["bas", "plié", "soléaire", "cheville"]):
                matched_key = "etirement_mollet_bas"
            else:
                matched_key = "etirement_mollet_haut"
        elif any(w in cleaned for w in ["balle", "massage", "voûte", "voute", "plante"]):
            matched_key = "massage_voute_balle"
        elif "renfo" in cleaned or "renforcement" in cleaned:
            # Présentation d'ensemble
            return (
                "Voici comment faire tes exercices de renfo sans jargon : "
                "1. Descente de mollets sur marche jambes tendues : monte à deux pieds, descends lentement sur 1 jambe en 3 secondes. "
                "2. Mollets bas genoux pliés : pareil sur la marche mais avec les genoux pliés à 45 degrés pour cibler le muscle profond. "
                "3. Pont fessier sur 1 jambe au sol : pousse sur le talon pour bien aligner le bassin. "
                "4. Gainage planche : corps droit et nombril rentré pendant 45 secondes. "
                "Dis-moi si tu veux le détail pas à pas d'un de ces exercices !"
            )

        if matched_key and matched_key in EXERCISE_GUIDE:
            ex = EXERCISE_GUIDE[matched_key]
            return (
                f"Voici comment réaliser l'exercice '{ex['nom']}' : "
                f"Objectif : {ex['objectif']} "
                f"Installation : {ex['installation']} "
                f"Mouvement : {ex['mouvement']} "
                f"Tempo & Séries : {ex['tempo']} "
                f"Sensations : {ex['sensations']} "
                f"Erreurs à éviter : {ex['erreurs_a_eviter']}"
            )

        # Fallback général vulgarisé
        return (
            f"Pour l'exercice '{exercise_query}', le secret est de faire des mouvements contrôlés et freinés : "
            "monte en 1 seconde, descends lentement en retenant le poids sur 3 secondes, et respire calmement sans à-coup. "
            "Tu peux me demander des détails précis sur les mollets sur marche, le pont fessier, ou le gainage !"
        )

    async def plan_weekly_training(
        self,
        query: str = "",
        target_week: Optional[int] = None,
        target_year: Optional[int] = None,
    ) -> SportWeeklyPlanProposal:
        """Génère un plan d'entraînement hebdomadaire sur-mesure via Gemini Flash en analysant l'historique."""
        # 1. RÈGLE SUBLIME D'ALEXIS : Pas de mode hors-ligne. Erreur explicite obligatoire.
        if not self.gemini_client or not self.gemini_client.is_configured:
            raise RuntimeError(
                "La planification hebdomadaire nécessite une connexion active à l'intelligence Otis (Gemini). "
                "Impossible de générer un plan personnalisé hors-ligne."
            )

        # 2. Détermination de la semaine cible
        today = date.today()
        current_iso = today.isocalendar()
        target_w = target_week or (current_iso[1] if current_iso[2] < 7 else current_iso[1] + 1)
        target_y = target_year or current_iso[0]

        # 3. Récupération et synthèse de l'historique des 4 dernières semaines
        history_summaries: List[Dict[str, Any]] = []
        for w_offset in range(1, 5):
            past_w = target_w - w_offset
            past_y = target_y
            if past_w <= 0:
                past_w += 52
                past_y -= 1
            summary = self.connector.get_weekly_summary(past_w, past_y)
            if summary and summary.nb_seances > 0:
                history_summaries.append({
                    "semaine": summary.semaine,
                    "annee": summary.annee,
                    "km_effort_total": summary.km_effort_total,
                    "km_total": summary.km_total,
                    "duree_minutes": summary.duree_secondes // 60,
                    "allure_moyenne": summary.allure_moyenne_formatted,
                    "vitesse_moyenne_kmh": summary.vitesse_kmh,
                    "charge_rpe": summary.charge_rpe_totale,
                    "evolution_volume_pct": summary.evolution_volume_pct,
                    "evolution_vitesse_pct": summary.evolution_vitesse_pct,
                    "evolution_rpe_pct": summary.evolution_rpe_pct,
                    "progression_generale_pct": summary.progression_generale_pct,
                    "nb_renfo": summary.nb_renfo,
                    "alerte_securite": summary.alerte_securite,
                })

        # Détection des surcharges RPE et de la progression générale récente
        rpe_surges = []
        if history_summaries:
            latest = history_summaries[0]
            if latest.get("evolution_rpe_pct") is not None and latest["evolution_rpe_pct"] > 20.0:
                rpe_surges.append(f"Semaine {latest['semaine']}: Surcharge RPE de +{latest['evolution_rpe_pct']}% (Progression Générale: +{latest.get('progression_generale_pct')}%)")
            elif latest.get("progression_generale_pct") is not None and latest["progression_generale_pct"] > 10.0:
                rpe_surges.append(f"Semaine {latest['semaine']}: Progression Générale élevée de +{latest['progression_generale_pct']}%")

        # Dernière semaine de référence pour la règle des +10%
        ref_km_effort = 0.0
        if history_summaries:
            ref_km_effort = history_summaries[0]["km_effort_total"]
        plafond_conseille = round(ref_km_effort * 1.10, 1) if ref_km_effort > 0 else 15.0

        # Récupération des dernières séances pour détecter allures et douleurs
        recent_sessions = self.connector.get_week_sessions(target_w - 1, target_y)
        if not recent_sessions and history_summaries:
            recent_sessions = self.connector.get_week_sessions(history_summaries[0]["semaine"], history_summaries[0]["annee"])

        recent_sessions_info = []
        douleurs_detectees = []
        rpe_eleves = []
        for s in recent_sessions[-6:]:
            recent_sessions_info.append({
                "date": s.date.strftime("%d/%m"),
                "type": s.type_seance.value if hasattr(s.type_seance, "value") else str(s.type_seance),
                "distance_km": s.distance_km,
                "allure": s.allure_formatted,
                "rpe": s.ressenti_rpe,
                "programme": s.programme,
                "remarques": s.remarques,
            })
            if s.ressenti_rpe and s.ressenti_rpe >= 8:
                rpe_eleves.append(f"{s.date.strftime('%d/%m')}: RPE {s.ressenti_rpe}")
            for text_field in [s.remarques, s.notes]:
                if text_field and any(w in text_field.lower() for w in ["douleur", "périostite", "periostite", "mal", "tibia", "gêne", "gene", "raideur"]):
                    douleurs_detectees.append(f"{s.date.strftime('%d/%m')}: {text_field}")

        # 4. Construction du contexte et des instructions pour le LLM
        prompt_context = {
            "requete_alexis": query,
            "semaine_cible": target_w,
            "annee_cible": target_y,
            "plafond_recommande_km_effort": plafond_conseille,
            "volume_semaine_precedente_km_effort": ref_km_effort,
            "historique_4_semaines": history_summaries,
            "surcharges_detectees": rpe_surges,
            "dernieres_seances_realisees": recent_sessions_info,
            "alertes_douleurs_detectees": douleurs_detectees,
            "rpe_eleves_detectes": rpe_eleves,
        }

        alerts_summary = ""
        combined_alerts = douleurs_detectees + rpe_eleves + rpe_surges
        if combined_alerts:
            alerts_summary = f"ATTENTION : Alertes détectées récemment ({', '.join(combined_alerts)})."
        else:
            alerts_summary = "Aucune douleur notée récemment, charge RPE sous contrôle et progression saine."

        user_prompt = (
            f"Analyse l'historique d'Alexis et génère son plan d'entraînement personnalisé pour la semaine {target_w} de l'année {target_y}.\n"
            f"Voici les données d'historique et le contexte d'Alexis :\n"
            f"{json.dumps(prompt_context, ensure_ascii=False, indent=2)}\n\n"
            f"Consignes clés d'Alexis pour le coach Otis :\n"
            f"1. DÉCISION REPOS VS NORMALE : C'est à toi (Otis) de décider si la semaine doit être de Repos/Décharge (3 séances) ou Normale (4 séances). "
            f"{alerts_summary} Si des douleurs, des RPE élevés ou une surcharge RPE/Progression Générale élevée sont présents, ou si Alexis le demande, prévois impérativement une semaine de repos. "
            f"Sinon, propose une semaine normale sans appliquer de règle mécanique rigide de 3 semaines.\n"
            f"2. DURÉES STRICTES : EF = entre 30 et 35 minutes (~4.5 à 5.5 km, pas 8 km !), Sortie Longue = environ 1 heure (~8.5 à 10 km max), Fractionné = environ 30 à 35 minutes (~5 km au total).\n"
            f"3. ALLURES ET VITESSES CIBLES (+/-) : Indique OBLIGATOIREMENT pour chaque course son allure cible ET sa vitesse cible avec tolérance (+/-). "
            f"L'EF et la Sortie Longue sont en Zone 2 d'aisance respiratoire (ex: allure_cible='06:20/km (+/- 15s)', vitesse_cible='9.5 km/h (+/- 0.4 km/h)'). L'EF ne doit JAMAIS être plus lente que la Sortie Longue !\n"
            f"4. RENFORCEMENT PRESCRIPTIF SANS JARGON KINÉ : Pour le mardi, décris le programme EXACT avec exercices vulgarisés, séries, répétitions et tempo dans le champ `programme` (ex: Descente de mollets sur marche jambes tendues 3x15 réps, Mollets bas genoux pliés 3x15 réps, Pont fessier au sol sur 1 jambe 3x12 réps/jambe, Gainage planche 3x45s). Zéro terme anatomique obscur brut !\n"
            f"5. ANALYSE MULTICRITÈRE : Intègre explicitement dans ton diagnostic `analyse_historique` l'évolution du volume, de la vitesse et de la charge RPE."
        )

        # 5. Appel Gemini avec sortie structurée
        plan = await self._call_gemini_coach(SPORT_COACH_SYSTEM_PROMPT, user_prompt)

        # 6. Complétion des dates calendaires et garantie de cohérence des allures/vitesses cibles
        try:
            # Calcul du premier jour (lundi) de la semaine ISO cible
            first_day_of_year = date(target_y, 1, 4)  # 4 janvier est toujours dans S1
            start_of_week1 = first_day_of_year - timedelta(days=first_day_of_year.isoweekday() - 1)
            target_monday = start_of_week1 + timedelta(weeks=target_w - 1)

            day_offsets = {"Lundi": 0, "Mardi": 1, "Mercredi": 2, "Jeudi": 3, "Vendredi": 4, "Samedi": 5, "Dimanche": 6}
            for seance in plan.seances:
                if not seance.date_seance and seance.jour in day_offsets:
                    seance.date_seance = target_monday + timedelta(days=day_offsets[seance.jour])

                # Garantie de présence et cohérence pour allure_cible et vitesse_cible
                if seance.type_seance != SportSessionType.RENFORCEMENT:
                    if not seance.vitesse_cible and seance.allure_cible:
                        m = re.search(r"(\d{1,2})[:'h](\d{2})", seance.allure_cible)
                        if m:
                            sec = int(m.group(1)) * 60 + int(m.group(2))
                            if sec > 0:
                                spd = round(3600.0 / sec, 1)
                                seance.vitesse_cible = f"{spd} km/h (+/- 0.4 km/h)"
                    elif not seance.allure_cible and seance.vitesse_cible:
                        m = re.search(r"(\d+(?:[.,]\d+)?)", seance.vitesse_cible)
                        if m:
                            spd = float(m.group(1).replace(",", "."))
                            if spd > 0:
                                sec_km = int(round(3600.0 / spd))
                                seance.allure_cible = f"{format_pace(sec_km)}/km (+/- 15s)"
        except Exception as exc:
            logger.warning(f"Impossible d'ajuster les dates ou allures du plan : {exc}")

        return plan

    async def _call_gemini_coach(self, system_prompt: str, user_prompt: str) -> SportWeeklyPlanProposal:
        """Exécute l'appel Gemini API avec validation JSON stricte."""
        candidates = self.gemini_client.get_candidate_models()
        last_exception = None

        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}
            ],
            "generationConfig": {
                "temperature": 0.2,
                "response_mime_type": "application/json",
                "response_schema": GEMINI_WEEKLY_PLAN_SCHEMA,
            },
        }

        for candidate in candidates:
            url = f"{GEMINI_API_BASE_URL}/models/{candidate}:generateContent?key={self.gemini_client.api_key}"
            start_time = time.perf_counter()
            try:
                async with httpx.AsyncClient(timeout=self.gemini_client.timeout) as http_client:
                    response = await http_client.post(url, json=payload)
                    if response.status_code == 429:
                        self.gemini_client.mark_model_temporarily_unavailable(candidate, 60.0)
                        continue
                    if response.status_code in (503, 404):
                        continue
                    response.raise_for_status()
                    data = response.json()

                latency_ms = (time.perf_counter() - start_time) * 1000
                self.gemini_client.record_request(latency_ms)
                self.gemini_client.set_active_working_model(candidate)

                candidates_res = data.get("candidates", [])
                if not candidates_res:
                    raise ValueError("Aucun candidat retourné par Gemini")

                parts = candidates_res[0].get("content", {}).get("parts", [])
                if not parts:
                    raise ValueError("Aucune réponse textuelle reçue de Gemini")

                raw_json = parts[0].get("text", "{}")
                parsed_dict = json.loads(raw_json)
                return SportWeeklyPlanProposal.model_validate(parsed_dict)

            except Exception as exc:
                last_exception = exc
                logger.warning(f"Échec de l'appel coach Gemini sur le modèle {candidate} : {exc}")
                continue

        raise RuntimeError(
            f"Échec de la génération du plan d'entraînement par Gemini : {last_exception}. "
            "Vérifiez votre connexion réseau et vos quotas d'API."
        )
