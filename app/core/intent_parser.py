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

        # 0. Nettoyage de la liste de courses ("vide la liste de courses", "nettoie la liste")
        if re.search(r"(?:vide|nettoie|supprime|efface)\s+(?:la\s+)?liste\s+(?:de\s+|des\s+)?courses?", cleaned):
            return ParsedIntent(
                intent=IntentType.CLEAR_SHOPPING_LIST,
                confidence=0.95,
                parameters={},
                raw_query=text,
            )

        # 1. Ajout d'ingrédients d'une recette ("ajoute les ingrédients du risotto de quinoa à la liste de courses")
        recipe_ing_add_match = re.search(
            r"(?:ajoute|mets)\s+les\s+ingr[ée]dients\s+(?:du|de\s+la|de\s+l'|de|d')\s*(.+)",
            cleaned,
            re.IGNORECASE,
        )
        if recipe_ing_add_match:
            rest = recipe_ing_add_match.group(1).strip()
            # Nettoyer d'éventuels points d'interrogation / ponctuation
            rest = re.sub(r"[?!.,;]+$", "", rest).strip()
            exclude_val = None
            if " sauf " in rest:
                rest, exclude_val = rest.split(" sauf ", 1)
                exclude_val = exclude_val.strip()
            # Nettoyer "à la liste de courses"
            rest = re.sub(r"\s+(?:[àa]|sur|dans)\s+(?:la\s+)?liste\s+(?:de\s+|des\s+)?courses?.*$", "", rest, flags=re.IGNORECASE).strip()
            params = {"recipe": rest}
            if exclude_val:
                params["exclude"] = exclude_val
            return ParsedIntent(
                intent=IntentType.ADD_RECIPE_INGREDIENTS,
                confidence=0.95,
                parameters=params,
                raw_query=text,
            )

        # 2. Consultation d'ingrédients d'une recette ("quels sont les ingrédients pour...", "qu'est-ce qu'il faut pour faire...")
        recipe_ing_match = re.search(
            r"(?:ingr[ée]dients\s+(?:pour|du|de\s+la|de\s+l'|de|d')|qu'est[- ]ce\s+qu'il\s+faut\s+pour\s+(?:faire\s+)?(?:du|de\s+la|de\s+l'|des|le|la|l'|d')?)\s*(.+)",
            cleaned,
            re.IGNORECASE,
        )
        if recipe_ing_match:
            recipe_name = recipe_ing_match.group(1).strip()
            recipe_name = re.sub(r"[?!.,;]+$", "", recipe_name).strip()
            recipe_name = re.sub(r"^(?:le|la|les|l'|du|de\s+la|des|un|une)\s+", "", recipe_name).strip()
            return ParsedIntent(
                intent=IntentType.GET_RECIPE_INGREDIENTS,
                confidence=0.95,
                parameters={"recipe": recipe_name},
                raw_query=text,
            )

        # 3. Planification de repas ("mets des pâtes carbonara ce soir", "prévois une pizza demain soir")
        set_meal_match = re.search(
            r"(?:mets|prévois|programme|planifie)\s+(.+?)\s+(ce\s+soir|ce\s+midi|demain(?:\s+soir|\s+midi)?|pour\s+demain|pour\s+ce\s+soir)$",
            cleaned,
            re.IGNORECASE,
        )
        if set_meal_match:
            meal = set_meal_match.group(1).strip()
            meal = re.sub(r"^(?:le|la|les|l'|du|de\s+la|des|un|une)\s+", "", meal).strip()
            time_expr = set_meal_match.group(2).lower()
            period = "demain" if "demain" in time_expr else ("midi" if "midi" in time_expr else "soir")
            return ParsedIntent(
                intent=IntentType.SET_MEAL_PLAN,
                confidence=0.95,
                parameters={"meal": meal, "period": period},
                raw_query=text,
            )

        # 4. Consultation repas ("qu'est-ce qu'on mange ce soir / midi / demain ?")
        if re.search(r"(?:qu[' ]?est[- ]ce\s+qu[' ]?on\s+mange|on\s+mange\s+quoi|menu\s+d[eu]|quel\s+est\s+le\s+repas)", cleaned):
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

        # 5. Marquage courses achetées ("j'ai acheté le café bio et le dentifrice")
        bought_match = re.search(
            r"^j[' ]?ai\s+achet[ée]\s+(?!pour\s+\d)(.+)$",
            cleaned,
            re.IGNORECASE,
        )
        if bought_match:
            items_str = bought_match.group(1).strip()
            items_str = re.sub(r"[?!.,;]+$", "", items_str).strip()
            return ParsedIntent(
                intent=IntentType.MARK_SHOPPING_BOUGHT,
                confidence=0.95,
                parameters={"items": items_str},
                raw_query=text,
            )

        # 6. Ajout article liste de courses ("ajoute du lait à la liste de courses", "mets du pain sur la liste")
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

        # 7. Consultation liste de courses ("donne-moi la liste de courses", "qu'est-ce qu'il y a sur la liste de courses")
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
