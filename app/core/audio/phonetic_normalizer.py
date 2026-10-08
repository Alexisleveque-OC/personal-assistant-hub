"""Couche de normalisation phonétique pour corriger les confusions récurrentes de transcription vocale."""
import re


def normalize_phonetics(raw_text: str) -> str:
    """Nettoie et normalise phonétiquement le texte issu de la reconnaissance vocale."""
    if not raw_text:
        return ""

    text = raw_text

    # 1. RPE / Ressenti d'effort : "à Troyes" / "à troyes" -> "à 3"
    text = re.sub(
        r"\b(?:rpe|ressenti|effort)\s+à\s+troyes\b",
        "RPE à 3",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\bà\s+troyes\s+sur\s+10\b",
        "à 3 sur 10",
        text,
        flags=re.IGNORECASE,
    )

    # 2. Confusion sur le prénom Otis ("autiste", "notice", "hotis", "hostis")
    text = re.sub(
        r"\b(?:autiste|notice|hotis|hostis)\b",
        "Otis",
        text,
        flags=re.IGNORECASE,
    )

    # 3. Sport & Renforcement : "renfort" -> "renforcement"
    # Ex: "30 minutes de renfort", "séance de renfort", "fait du renfort", "un peu de renfort"
    text = re.sub(
        r"\b(?:de|du|en)\s+renfort\b",
        lambda m: m.group(0).replace("renfort", "renforcement"),
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\brenfort\s+musculaire\b",
        "renforcement musculaire",
        text,
        flags=re.IGNORECASE,
    )

    # 4. Dénivelé : "des plus" / "d plus" -> "D+"
    # Ex: "150 des plus", "dénivelé de 120 des plus", "120 d plus"
    text = re.sub(
        r"(\d+)\s+(?:des\s+plus|d\s+plus)\b",
        r"\1 D+",
        text,
        flags=re.IGNORECASE,
    )

    return text.strip()
