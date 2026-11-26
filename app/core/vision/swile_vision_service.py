"""Lecture d'une capture de l'appli Swile (Phase 10, étape 8) : lignes de paiement, crédits et solde Titres-resto.

Gemini ne fait que lire : la date est rendue telle qu'affichée et résolue ensuite (`swile_import.dates`), le
montant garde son signe (paiement négatif, crédit positif).
"""
from typing import Optional

from app.core.llm.gemini_client import GeminiClient, get_gemini_client
from app.core.swile_import.models import SwileCapture
from app.core.vision.gemini_vision import generate_vision_json

GEMINI_SWILE_VISION_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "is_swile": {"type": "BOOLEAN", "description": "True si l'image est une capture de l'appli Swile."},
        "solde": {
            "type": "NUMBER",
            "description": "Solde Titres-resto affiché en haut de l'accueil « Avantages » (ex: 95.64), sinon null.",
            "nullable": True,
        },
        "lignes": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "marchand": {"type": "STRING", "description": "Nom affiché (ex: Intermarche, Crédit titres-resto)."},
                    "date_texte": {
                        "type": "STRING",
                        "description": "Date et heure recopiées telles qu'affichées (ex: « Hier, 17:35 »).",
                    },
                    "montant": {"type": "NUMBER", "description": "Montant signé : -12.81 pour « -12,81 € »."},
                },
                "required": ["marchand", "date_texte", "montant"],
            },
        },
        "message": {"type": "STRING", "description": "Motif si ce n'est pas une capture Swile."},
    },
    "required": ["is_swile", "lignes", "solde"],
}


class SwileVisionService:
    def __init__(self, gemini_client: Optional[GeminiClient] = None) -> None:
        self.gemini_client = gemini_client or get_gemini_client()

    def build_prompt(self) -> str:
        return (
            "Tu lis une capture d'écran de l'application Swile (titres-restaurant) envoyée par Alexis.\n"
            "Recopie fidèlement, sans rien inventer ni calculer :\n"
            "1. lignes : chaque paiement ou crédit de la liste (écrans « Derniers paiements » ou accueil "
            "« Avantages »), de haut en bas.\n"
            "   - marchand : le nom en gras tel qu'écrit (ex: 'Intermarche', 'Burger King', 'Crédit titres-resto').\n"
            "   - date_texte : la ligne grise sous le nom, recopiée mot pour mot (ex: 'mercredi 25 nov. 2026, 17:35', "
            "'Hier, 17:35', 'lundi, 12:52', '14 novembre, 11:10'). Ne la convertis pas.\n"
            "   - montant : nombre signé, virgule décimale convertie en point : un paiement '-12,81 €' est NÉGATIF "
            "(-12.81) ; un crédit en vert '+242,00 €' est POSITIF (242.0).\n"
            "   - Ignore toute ligne coupée par le bord de l'écran ou dont le nom, la date ou le montant n'est pas "
            "entièrement lisible.\n"
            "   - Ignore les titres de section (« Novembre », « Octobre »), les bannières et publicités.\n"
            "2. solde : le montant affiché à droite de « Titres-resto » en haut de l'accueil « Avantages » "
            "(ex: '95,64 €' → 95.64). Ce n'est PAS le plafond « Aujourd'hui, dépensez jusqu'à … ». "
            "null s'il n'est pas visible.\n"
            "3. is_swile : false si l'image n'est pas une capture Swile (lignes vides, solde null, message "
            "expliquant ce que montre l'image).\n"
        )

    async def analyze_screenshot(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> SwileCapture:
        """Lève VisionServiceUnavailableError si la clé est absente ou si tous les modèles échouent."""
        raw = await generate_vision_json(
            self.gemini_client, image_bytes, mime_type, self.build_prompt(), GEMINI_SWILE_VISION_SCHEMA,
            tag="SwileVisionService",
        )
        return SwileCapture.model_validate(raw)


_instance: Optional[SwileVisionService] = None


def get_swile_vision_service() -> SwileVisionService:
    global _instance
    if _instance is None:
        _instance = SwileVisionService()
    return _instance
