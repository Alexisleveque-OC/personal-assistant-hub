"""Voie rapide regex du mode agent : les demandes simples et non ambiguës évitent l'appel Gemini (latence, quota).

Une phrase n'y reste que si la regex l'a classée dans une intention éligible ET qu'elle ne contient aucun
indice d'ambiguïté (autre domaine, action composée, nuance). Dans le doute, l'agent décide.
"""
import re

from app.core.models import IntentType, ParsedIntent

FAST_LANE_INTENTS = frozenset({
    IntentType.ADD_SHOPPING_ITEM,
    IntentType.GET_SHOPPING_LIST,
    IntentType.GET_MEAL_PLAN,
    IntentType.CLEAR_SHOPPING_LIST,
})

_ACTION_VERBS = (
    r"ajoute[sz]?|rajoute[sz]?|mets|mettre|retire[sz]?|enl[eè]ve[sz]?|supprime[sz]?|efface[sz]?|coche[sz]?|"
    r"d[ée]coche[sz]?|vide[sz]?|remplace[sz]?|range[sz]?|d[ée]place[sz]?|change[sz]?|modifie[sz]?|annule[sz]?|"
    r"note[sz]?|planifie[sz]?|pr[ée]vois|programme[sz]?|d[ée]cale[sz]?|inverse[sz]?|[ée]change[sz]?"
)
_ACTION = re.compile(rf"\b(?:{_ACTION_VERBS})\b", re.IGNORECASE)
# Seconde action enchaînée : « ajoute du pain, et coche le lait », « … puis vide la liste ».
_COMPOUND = re.compile(rf"(?:,|;|\.|\bet\b|\bpuis\b|\bensuite\b)\s*(?:aussi\s+)?(?:{_ACTION_VERBS})\b", re.IGNORECASE)
_SPORT_WORDS = re.compile(
    r"\b(?:séances?|seances?|entra[iî]nements?|footing|fractionn[ée]|renfo|renforcement|sortie\s+longue|course\s+à\s+pied)\b",
    re.IGNORECASE,
)
# « ajoute X » : tout ce qui dépasse un simple article (repas, date, rayon, note, nuance) part à l'agent.
_NOT_A_SIMPLE_ITEM = re.compile(
    r"\b(?:rayon|repas|menu|planning|recettes?|ingr[ée]dients?|midi|soir|demain|aujourd['’]hui|hier|lundi|mardi|"
    r"mercredi|jeudi|vendredi|samedi|dimanche|semaine|notes?|rappels?|t[âa]ches?|minutes?|que|qu['’]|sauf|sans|"
    r"au\s+lieu|plut[ôo]t)\b",
    re.IGNORECASE,
)
_MAX_ITEM_WORDS = 4
# « est-ce qu'il reste du café sur la liste ? » : question précise, pas une lecture de toute la liste.
_MEMBERSHIP_QUESTION = re.compile(
    r"(?:est[- ]ce\s+qu['’]il\s+(?:y\s+a|reste)|y\s+a[- ]t[- ]il|reste[- ]t[- ]il)\s+(?:du|de\s+la|des|de\s+l['’]|d['’]|le|la|les|un|une)\b",
    re.IGNORECASE,
)
_MEAL_BEYOND_ONE_SLOT = re.compile(
    r"\b(?:et|semaine|week[- ]end|recettes?|ingr[ée]dients?|courses?)\b",
    re.IGNORECASE,
)
_PLAIN_CLEAR = re.compile(r"^(?:vide|nettoie)\s+(?:la\s+)?liste\s+(?:de\s+|des\s+)?courses?\s*[.!]*$", re.IGNORECASE)


def is_fast_lane(parsed: ParsedIntent, query: str) -> bool:
    text = query.strip()
    match parsed.intent:
        case IntentType.ADD_SHOPPING_ITEM:
            items = parsed.parameters.get("items") or [parsed.parameters.get("item", "")]
            return (
                not _SPORT_WORDS.search(text)
                and not _NOT_A_SIMPLE_ITEM.search(text)
                and not _COMPOUND.search(text)
                and all(item and len(item.split()) <= _MAX_ITEM_WORDS for item in items)
            )
        case IntentType.GET_SHOPPING_LIST:
            return not _ACTION.search(text) and not _MEMBERSHIP_QUESTION.search(text)
        case IntentType.GET_MEAL_PLAN:
            return not _ACTION.search(text) and not _MEAL_BEYOND_ONE_SLOT.search(text)
        case IntentType.CLEAR_SHOPPING_LIST:
            return bool(_PLAIN_CLEAR.match(text))
        case _:
            return False
