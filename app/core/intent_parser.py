"""Moteur d'analyse et de classification d'intentions en langage naturel."""
import re
from typing import Optional
from app.core.models import IntentType, ParsedIntent


class IntentParser:
    """Analyseur d'intentions.
    
    Combine des règles heuristiques locales déterministes (ultra-rapides et sans coût)
    avec possibilité de délégation à un LLM pour les cas ambigus.
    """

    def parse(self, text: str) -> ParsedIntent:
        cleaned = text.strip().lower()

        # 1. Repas ("qu'est-ce qu'on mange ce soir / midi / demain ?")
        if any(kw in cleaned for kw in ["qu'est-ce qu'on mange", "qu'est ce qu'on mange", "menu de ce", "on mange quoi"]):
            period = "soir"
            if "midi" in cleaned:
                period = "midi"
            elif "demain" in cleaned:
                period = "demain"
            return ParsedIntent(
                intent=IntentType.GET_MEAL_PLAN,
                confidence=0.95,
                parameters={"period": period},
                raw_query=text,
            )

        # 2. Ajout liste de courses ("ajoute du lait à la liste de courses", "mets du pain sur la liste")
        add_shopping_match = re.search(
            r"(?:ajoute|mets|rajoute)\s+(.+?)\s+(?:à|sur|dans)\s+(?:la\s+)?liste\s+(?:de\s+)?courses?",
            cleaned,
            re.IGNORECASE,
        )
        if add_shopping_match:
            item = add_shopping_match.group(1).strip()
            return ParsedIntent(
                intent=IntentType.ADD_SHOPPING_ITEM,
                confidence=0.95,
                parameters={"item": item},
                raw_query=text,
            )

        # 3. Consultation liste de courses ("donne-moi la liste de courses", "qu'est-ce qu'il y a sur la liste de courses")
        if "liste de courses" in cleaned or "liste des courses" in cleaned:
            return ParsedIntent(
                intent=IntentType.GET_SHOPPING_LIST,
                confidence=0.90,
                parameters={},
                raw_query=text,
            )

        # 4. Solde budget ("combien il reste de budget", "quel est le solde du budget courses")
        if any(kw in cleaned for kw in ["reste de budget", "solde", "reste pour les courses", "combien il reste"]):
            category = "general"
            if "courses" in cleaned:
                category = "courses"
            elif "loisir" in cleaned:
                category = "loisirs"
            return ParsedIntent(
                intent=IntentType.GET_BUDGET_BALANCE,
                confidence=0.90,
                parameters={"category": category},
                raw_query=text,
            )

        # 5. Enregistrer une dépense ("j'ai acheté pour 45€ de courses", "dépense de 20 euros")
        expense_match = re.search(
            r"(?:acheté|dépensé|dépense de|payé)\s+(?:pour\s+)?(\d+(?:[.,]\d+)?)\s*(?:€|euros?)(?:\s+(?:en|de|pour)\s+([a-zA-ZÀ-ÿ]+))?",
            cleaned,
            re.IGNORECASE,
        )
        if expense_match:
            amount_str = expense_match.group(1).replace(",", ".")
            amount = float(amount_str)
            category = expense_match.group(2) or "divers"
            return ParsedIntent(
                intent=IntentType.LOG_EXPENSE,
                confidence=0.92,
                parameters={"amount": amount, "category": category.strip()},
                raw_query=text,
            )

        # 6. Tâches Google Tasks ("rappelle-moi d'...", "ajoute une tâche...")
        if cleaned.startswith("rappelle-moi") or "ajoute la tâche" in cleaned:
            task_content = re.sub(r"^(?:rappelle-moi\s+(?:de\s+|d')?|ajoute la tâche\s+)", "", cleaned).strip()
            return ParsedIntent(
                intent=IntentType.ADD_TASK,
                confidence=0.88,
                parameters={"task": task_content},
                raw_query=text,
            )
        if "mes tâches" in cleaned:
            return ParsedIntent(
                intent=IntentType.LIST_TASKS,
                confidence=0.90,
                parameters={},
                raw_query=text,
            )

        # 7. Gmail ("résume mes mails", "mails importants")
        if "mail" in cleaned or "e-mail" in cleaned or "courriel" in cleaned:
            return ParsedIntent(
                intent=IntentType.SUMMARIZE_EMAILS,
                confidence=0.85,
                parameters={},
                raw_query=text,
            )

        # 8. Domotique ("allume la prise", "éteins la prise")
        if "prise" in cleaned:
            action = "on" if any(w in cleaned for w in ["allume", "active", "lance"]) else "off"
            return ParsedIntent(
                intent=IntentType.TOGGLE_DEVICE,
                confidence=0.90,
                parameters={"device": "prise", "action": action},
                raw_query=text,
            )

        # Inconnu
        return ParsedIntent(
            intent=IntentType.UNKNOWN,
            confidence=0.20,
            parameters={},
            raw_query=text,
        )
