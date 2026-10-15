"""Service d'analyse multimodale de captures d'écran de séances de sport (Strava, Decathlon, Garmin)."""
import base64
from datetime import date, datetime, timedelta
import json
import logging
import re
from typing import Any, Dict, Optional

import httpx

from app.core.models import SportScreenshotAnalysisResult
from app.core.llm.gemini_client import (
    GEMINI_API_BASE_URL,
    GeminiClient,
    get_gemini_client,
)
from app.core.date_resolver import parse_screenshot_date

logger = logging.getLogger(__name__)

GEMINI_SPORT_VISION_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "is_sport_session": {
            "type": "BOOLEAN",
            "description": "True s'il s'agit d'une capture d'écran de séance sportive (running, renforcement)",
        },
        "app_source": {
            "type": "STRING",
            "description": "Nom de l'application ou de la montre (ex: Strava, Decathlon Coach, Decathlon Connect (CW500 M), Garmin, Apple Forme)",
        },
        "date": {
            "type": "STRING",
            "description": "Date de la séance au format ISO YYYY-MM-DD",
        },
        "heure_depart": {
            "type": "STRING",
            "description": "Heure de départ au format HH:MM le cas échéant",
        },
        "type_seance": {
            "type": "STRING",
            "description": "Type de séance : EF, Sortie Longue, Fractionné, Renforcement, Vitesse, Course",
        },
        "distance_km": {
            "type": "NUMBER",
            "description": "Distance parcourue en kilomètres (ex: 5.12)",
        },
        "duree_secondes": {
            "type": "INTEGER",
            "description": "Durée active de déplacement convertie en total de secondes (ex: 31'23\" -> 1883)",
        },
        "denivele_d_plus": {
            "type": "INTEGER",
            "description": "Dénivelé positif (D+) en mètres (ex: 31)",
        },
        "allure_moyenne": {
            "type": "STRING",
            "description": "Allure moyenne au format mm:ss (ex: 06:07)",
        },
        "vitesse_kmh": {
            "type": "NUMBER",
            "description": "Vitesse moyenne en km/h le cas échéant (ex: 9.79)",
        },
        "fc_moyenne": {
            "type": "INTEGER",
            "description": "Fréquence cardiaque moyenne en bpm (ex: 163)",
        },
        "fc_max": {
            "type": "INTEGER",
            "description": "Fréquence cardiaque maximale en bpm si visible",
        },
        "cadence_spm": {
            "type": "INTEGER",
            "description": "Cadence moyenne en pas/min si affichée",
        },
        "calories_kcal": {
            "type": "INTEGER",
            "description": "Calories brûlées en kcal",
        },
        "titre": {
            "type": "STRING",
            "description": "Titre affiché de l'activité (ex: Course à pied du midi)",
        },
        "message": {
            "type": "STRING",
            "description": "Motif de rejet si non sportive ou remarques particulières",
        },
    },
    "required": ["is_sport_session", "app_source"],
}


class SportVisionService:
    """Service d'extraction de métriques sportives depuis des images de montres et d'applications."""

    def __init__(self, gemini_client: Optional[GeminiClient] = None) -> None:
        self.gemini_client = gemini_client or get_gemini_client()

    def build_prompt(self, reference_date: Optional[date] = None) -> str:
        ref_d = reference_date or date.today()
        ref_iso = ref_d.isoformat()

        return (
            "Tu es Otis, le coach personnel d'entraînement d'Alexis.\n"
            f"Alexis t'envoie une capture d'écran d'une séance sportive (Date de référence du jour : {ref_iso}).\n"
            "Analyse minutieusement l'image et extrait avec une exactitude mathématique toutes les métriques visibles :\n"
            "\n"
            "1. Détection de l'application / source :\n"
            "   - 'Strava' : interface sombre, libellés 'Distance', 'Durée de déplacement', 'Allure moyenne', 'Dénivelé positif'.\n"
            "   - 'Decathlon Coach' : tracé GPS avec carte, splits/laps en bas, grands chiffres 'XX.XX km', durée 'XX'XX\"', allure 'XX'XX\"/km', dénivelé '+XX m'. La date se trouve en haut dans l'en-tête (ex: 'Mercredi 14 oct.', '14/10', 'Hier à 18:30').\n"
            "   - 'Decathlon Connect (CW500 M)' : icône coureur bleue, onglet 'Résumé', 'Durée H:MM:SS', 'Distance X,Xkm', 'Fréqu. cardiaque moy XXXbpm', 'Cadence moyenne XXXpas/min'. La date est en haut sous le titre.\n"
            "   - 'Garmin Connect', 'Apple Forme', 'Kiprun', etc.\n"
            "\n"
            "2. Si l'image NE REPRÉSENTE PAS une séance sportive :\n"
            "   - is_sport_session: false, message: 'Cette image ne semble pas être un récapitulatif de séance sportive.'\n"
            "\n"
            "3. Conversion et normalisation stricte des métriques :\n"
            "   - distance_km : nombre décimal en km (ex: 5.09, 5.12, 4.9).\n"
            "   - duree_secondes : convertis impérativement la durée affichée en TOTAL DE SECONDES ENTIER :\n"
            "     * '30:40' -> 30*60 + 40 = 1840 secondes\n"
            "     * '31\\'23\"' -> 31*60 + 23 = 1883 secondes\n"
            "     * '0:33:07' -> 33*60 + 7 = 1987 secondes\n"
            "     * '1:10:15' -> 1*3600 + 10*60 + 15 = 4215 secondes\n"
            "   - denivele_d_plus : D+ en mètres entiers (ex: 20, 31). Mettre 0 si non mentionné.\n"
            "   - fc_moyenne : Fréquence cardiaque moyenne en bpm (ex: 163 bpm -> 163). Ne pas confondre avec la cadence.\n"
            "   - fc_max : Fréquence cardiaque max si disponible.\n"
            "   - cadence_spm : Cadence en pas par minute (ex: 170 pas/min -> 170).\n"
            "   - allure_moyenne : Formater strictement en mm:ss (ex: '06:01', '06:07', '06:43').\n"
            "   - date : Date de la séance (au format ISO YYYY-MM-DD ou format textuel brut extrait de l'en-tête) :\n"
            "     * Regarde impérativement en haut : sous le titre ('Course à pied'), dans le bandeau supérieur à côté de la flèche ou sous la carte.\n"
            "     * Pour Decathlon Coach ou Decathlon Connect, la date est souvent 'Mercredi 14 oct.', '14/10', '14/10/2026', '14 oct. 2026' ou 'Hier à 18:30'.\n"
            f"     * Si la date est explicite ou relative, convertis-la par rapport à la date de référence ({ref_iso}).\n"
            "     * Attention : une séance enregistrée est TOUJOURS passée ou du jour (jamais future). Par exemple, 'Mercredi' correspond au mercredi passé le plus récent.\n"
            "     * Si aucune date n'est visible sur la capture, mets null (ne mets PAS la date du jour par défaut si tu ne la vois pas).\n"
            "   - type_seance :\n"
            "     * 'Fractionné' si blocs, répétitions ou mention explicite fractionné.\n"
            "     * 'Sortie Longue' si distance > 10 km ou libellé sortie longue.\n"
            "     * 'Renforcement' si exercices musculaires.\n"
            "     * 'EF' par défaut pour les footings d'endurance fondamentale.\n"
        )

    def analyze_screenshot(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        reference_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Appelle Gemini Vision et retourne le dictionnaire de métriques extraites."""
        client = self.gemini_client
        if not client or not client.api_key:
            logger.warning("[SportVisionService] Clé Gemini absente, fallback mock local.")
            return self._fallback_analysis(reference_date)

        prompt = self.build_prompt(reference_date)
        b64_img = base64.b64encode(image_bytes).decode("utf-8")

        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": mime_type,
                                "data": b64_img,
                            }
                        },
                        {"text": prompt},
                    ]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": GEMINI_SPORT_VISION_SCHEMA,
                "temperature": 0.1,
            },
        }

        # Liste prioritaire des modèles multimodaux stables
        candidates = client.get_candidate_models() if hasattr(client, "get_candidate_models") else []
        preferred_models = [
            "gemini-3.8-flash",
            "gemini-3.5-flash",
            "gemini-flash-latest",
            "gemini-3.6-flash",
            "gemini-3.7-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
        ]
        to_try: list[str] = []
        for m in candidates + preferred_models:
            clean = m.replace("models/", "").strip()
            # Écarter les versions dépréciées (404)
            if clean and clean not in to_try and not any(old in clean for old in ("2.5", "1.5", "2.0")):
                to_try.append(clean)

        for model_name in to_try:
            url = f"{GEMINI_API_BASE_URL}/models/{model_name}:generateContent?key={client.api_key}"
            try:
                with httpx.Client(timeout=25.0) as http_client:
                    resp = http_client.post(url, json=payload)
                    if resp.status_code == 200:
                        res_json = resp.json()
                        cands = res_json.get("candidates", [])
                        if cands:
                            raw_text = cands[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                            parsed = json.loads(raw_text)
                            if parsed.get("date"):
                                parsed["date"] = parse_screenshot_date(parsed["date"], reference_date=reference_date).isoformat()
                            if hasattr(client, "set_active_working_model"):
                                client.set_active_working_model(model_name)
                            return parsed
                    elif resp.status_code in (429, 503):
                        if hasattr(client, "mark_model_temporarily_unavailable"):
                            client.mark_model_temporarily_unavailable(model_name, 30.0)
                        logger.warning(
                            f"[SportVisionService] Modèle {model_name} indisponible ({resp.status_code}), tentative candidat suivant..."
                        )
                        continue
                    else:
                        logger.warning(
                            f"[SportVisionService] Modèle {model_name} erreur ({resp.status_code}): {resp.text[:150]}"
                        )
                        continue
            except Exception as exc:
                logger.warning(f"[SportVisionService] Échec appel {model_name} : {exc}")
                continue

        logger.error("[SportVisionService] Tous les modèles Gemini Vision ont échoué, repli local.")
        return self._fallback_analysis(reference_date)

    def _fallback_analysis(self, reference_date: Optional[date] = None) -> Dict[str, Any]:
        ref_d = reference_date or date.today()
        return {
            "is_sport_session": False,
            "app_source": "Inconnu",
            "date": ref_d.isoformat(),
            "message": "Impossible d'analyser la capture d'écran sans connexion à Gemini Vision.",
        }


_sport_vision_service_instance: Optional[SportVisionService] = None


def get_sport_vision_service() -> SportVisionService:
    global _sport_vision_service_instance
    if _sport_vision_service_instance is None:
        _sport_vision_service_instance = SportVisionService()
    return _sport_vision_service_instance
