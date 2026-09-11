"""Moteur d'analyse et de classification d'intentions en langage naturel."""
import re
from typing import Optional
from app.core.models import IntentType, ParsedIntent


class IntentParser:
    """Analyseur d'intentions.
    
    Combine des règles heuristiques locales déterministes (ultra-rapides et sans coût)
    avec possibilité de délégation à un LLM pour les cas ambigus.
    """

    def parse(self, text: str, context: Optional[dict] = None) -> ParsedIntent:
        cleaned = text.strip().lower()

        # 0.0 Politesse et small-talk ("merci", "ok merci", "bonjour", "au revoir", "super", "parfait", "d'accord")
        if re.search(
            r"^(?:(?:ok|d[' ]accord|super|parfait|bien|top|merci)\s+)*(?:merci(?:\s+beaucoup|\s+bien)?|bonjour|salut|coucou|bonsoir|au\s+revoir|bonne\s+(?:journ[ée]e|soir[ée]e)|[àa]\s+bient[ôo]t|[àa]\s+plus(?:\s+tard)?|bye|de\s+rien|je\s+vous\s+en\s+prie|ça\s+marche|nickel|impeccable|d[' ]accord|parfait|super|top|ok)\s*[!.]*$",
            cleaned,
            re.IGNORECASE,
        ):
            category = "thanks" if "merci" in cleaned else (
                "greeting" if any(w in cleaned for w in ["bonjour", "salut", "coucou", "bonsoir"]) else (
                    "farewell" if any(w in cleaned for w in ["au revoir", "bonne journée", "bonne soirée", "a bientot", "à bientôt", "bye"]) else "ack"
                )
            )
            return ParsedIntent(
                intent=IntentType.SMALL_TALK,
                confidence=0.95,
                parameters={"type": category},
                raw_query=text,
            )

        # 0.1 Nettoyage de la liste de courses ("vide la liste de courses", "nettoie la liste")
        if re.search(r"(?:vide|nettoie|supprime|efface)\s+(?:la\s+)?liste\s+(?:de\s+|des\s+)?courses?", cleaned):
            return ParsedIntent(
                intent=IntentType.CLEAR_SHOPPING_LIST,
                confidence=0.95,
                parameters={},
                raw_query=text,
            )

        # 0.2 Nettoyage des préfixes conversationnels / modaux pour les commandes
        # Ex: "tu peux tout rajouter...", "est-ce que tu peux...", "ok tu peux..."
        command_cleaned = cleaned
        command_cleaned = re.sub(
            r"^(?:(?:ok|d[' ]accord|bon|dis|dis[- ]moi|s[' ]?il\s+te\s+pla[îi]t|s[' ]?il\s+vous\s+pla[îi]t|stp|svp)\s*[,!.]?\s*)+",
            "",
            command_cleaned,
            flags=re.IGNORECASE,
        ).strip()
        command_cleaned = re.sub(
            r"^(?:(?:est[- ]ce\s+que\s+)?(?:tu\s+peux|tu\s+pourrais|peux[- ]tu|pourrais[- ]tu|vous\s+pouvez|pouvez[- ]vous|on\s+peut)|merci\s+de|veuillez)\s+(?:de\s+|d[' ])?",
            "",
            command_cleaned,
            flags=re.IGNORECASE,
        ).strip()

        # 0.bis Anaphore contextuelle : "ajoute ces ingrédients", "rajoute tout", "tu peux tout rajouter a la liste d'ingrédients"
        anaphora_match = re.search(
            r"^(?:tout\s+(?:ajoute[sz]?|ajoutez|ajouter|rajoute[sz]?|rajoutez|rajouter|mets?|mettez|mettre)|(?:ajoute[sz]?|ajoutez|ajouter|rajoute[sz]?|rajoutez|rajouter|mets?|mettez|mettre)(?:\s+tous)?(?:\s+tout(?:\s+ça)?|\s+tous\s+ces\s+ingr[ée]dients|\s+ces\s+ingr[ée]dients|-les(?:\s+tous)?|\s+les\s+tous|\s+les(?=\s+(?:[àa]|sur|dans|sauf|sans)\b|$)|(?:\s+(?:tous\s+)?les\s+ingr[ée]dients(?=\s+(?:[àa]|sur|dans|sauf|sans)\b|$))|\s+cette\s+recette))\s*(?:(?:[àa]|sur|dans)\s+(?:la\s+)?liste(?:\s+(?:de\s+|des\s+|d[' ])?(?:courses?|ingr[ée]dients?))?)?(.*)$",
            command_cleaned,
            re.IGNORECASE,
        )
        if anaphora_match:
            rest = anaphora_match.group(1).strip()
            rest = re.sub(r"[?!.,;]+$", "", rest).strip()
            rest = re.sub(r"\s*(?:s[' ]?il\s+te\s+pla[îi]t|s[' ]?il\s+vous\s+pla[îi]t|stp|svp)$", "", rest, flags=re.IGNORECASE).strip()
            exclude_val = None
            if " sauf " in rest:
                _, exclude_val = rest.split(" sauf ", 1)
            elif rest.startswith("sauf "):
                exclude_val = rest[5:].strip()
            elif " sans " in rest:
                _, exclude_val = rest.split(" sans ", 1)
            elif rest.startswith("sans "):
                exclude_val = rest[5:].strip()

            if exclude_val:
                exclude_val = re.sub(r"\s+(?:[àa]|sur|dans)\s+(?:la\s+)?liste\s+(?:de\s+|des\s+|d[' ])?(?:courses?|ingr[ée]dients?).*$", "", exclude_val, flags=re.IGNORECASE).strip()
                exclude_val = re.sub(r"^(?:le|la|les|l'|du|de\s+la|des|un|une|d')\s+", "", exclude_val.strip(), flags=re.IGNORECASE).strip()

            last_recipe = (context or {}).get("last_recipe")
            if last_recipe:
                params = {"recipe": last_recipe}
                if exclude_val:
                    params["exclude"] = exclude_val
                return ParsedIntent(
                    intent=IntentType.ADD_RECIPE_INGREDIENTS,
                    confidence=0.95,
                    parameters=params,
                    raw_query=text,
                )
            else:
                params = {"error": "no_context_recipe"}
                if exclude_val:
                    params["exclude"] = exclude_val
                return ParsedIntent(
                    intent=IntentType.ADD_RECIPE_INGREDIENTS,
                    confidence=0.90,
                    parameters=params,
                    raw_query=text,
                )

        # 1. Ajout d'ingrédients d'une recette ("ajoute les ingrédients du risotto", "ajoute les ingrédients pour faire du boeuf aux poivrons...")
        recipe_ing_add_match = re.search(
            r"^(?:ajoute|mets|rajoute)\s+(?:tous\s+)?les\s+ingr[ée]dients\s+(?:pour\s+(?:faire|pr[ée]parer|cuisiner)?\s*)?(?:d[eu]|de\s+la|de\s+l[' ]|des|d[' ]|le|la|les|l[' ]|un[e]?\s+)?\s*(.+)",
            cleaned,
            re.IGNORECASE,
        )
        if recipe_ing_add_match:
            rest = recipe_ing_add_match.group(1).strip()
            rest = re.sub(r"[?!.,;]+$", "", rest).strip()
            exclude_val = None
            if " sauf " in rest:
                rest, exclude_val = rest.split(" sauf ", 1)
            elif " sans " in rest:
                rest, exclude_val = rest.split(" sans ", 1)

            # Nettoyer "à la liste de courses" (avec tolérance sur accent et singulier)
            rest = re.sub(r"\s+(?:[àa]|sur|dans)\s+(?:la\s+)?liste\s+(?:de\s+|des\s+)?courses?.*$", "", rest, flags=re.IGNORECASE).strip()
            rest = re.sub(r"^(?:le|la|les|l'|du|de\s+la|des|un|une|d')\s+", "", rest).strip()

            params = {"recipe": rest}
            if exclude_val:
                exclude_val = re.sub(r"\s+(?:[àa]|sur|dans)\s+(?:la\s+)?liste\s+(?:de\s+|des\s+)?courses?.*$", "", exclude_val, flags=re.IGNORECASE).strip()
                exclude_val = re.sub(r"^(?:le|la|les|l'|du|de\s+la|des|un|une|d')\s+", "", exclude_val.strip()).strip()
                params["exclude"] = exclude_val

            return ParsedIntent(
                intent=IntentType.ADD_RECIPE_INGREDIENTS,
                confidence=0.95,
                parameters=params,
                raw_query=text,
            )

        # 2. Consultation de recette ou d'ingrédients ("quels sont les ingrédients pour...", "qu'est-ce qu'il faut pour faire...", "donnes-moi la recette du préfou")
        recipe_direct_match = None
        recipe_ing_match = None
        if not re.search(r"^(?:ajoute|mets|rajoute)\b", cleaned):
            recipe_direct_match = re.search(
                r"(?:(?:donne[sz]?(?:-moi|\s+moi)?|quelle\s+est|c[' ]est\s+quoi)\s+(?:la\s+)?recette\s+(?:d[eu]|de\s+la|de\s+l[' ]|des|d[' ])|recette\s+(?:d[eu]|de\s+la|de\s+l[' ]|des|d[' ]))\s*(.+)",
                cleaned,
                re.IGNORECASE,
            )
            recipe_ing_match = re.search(
                r"(?:ingr[ée]dients\s+(?:pour|d[eu]|de\s+la|de\s+l[' ]|des|d[' ])|"
                r"(?:qu[' ]?est[- ]ce\s+qu[' ]?il\s+faut|il\s+(?:me\s+)?faut\s+quoi|(?:j[' ]?ai\s+)?besoin\s+de\s+quoi)\s+pour\s+(?:faire|pr[ée]parer|cuisiner)?\s*(?:d[eu]|de\s+la|de\s+l[' ]|des|un[e]?|le|la|les|l[' ]|d[' ])?)\s*(.+)",
                cleaned,
                re.IGNORECASE,
            )

        matched_recipe_raw = None
        if recipe_direct_match:
            matched_recipe_raw = recipe_direct_match.group(1).strip()
        elif recipe_ing_match:
            matched_recipe_raw = recipe_ing_match.group(1).strip()

        if matched_recipe_raw:
            recipe_name = re.sub(r"[?!.,;]+$", "", matched_recipe_raw).strip()
            recipe_name = re.sub(r"^(?:le|la|les|l'|du|de\s+la|des|un|une|d')\s+", "", recipe_name).strip()
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

        # 6. Ajout article liste de courses ("ajoute du lait à la liste de courses", "ajoute chocolat a la liste de course", "ajoute chocolat")
        add_shopping_match = re.search(
            r"^(?:ajoute|mets|rajoute)\s+(.+?)\s+(?:[àa]|sur|dans)\s+(?:la\s+)?liste\s+(?:de\s+|des\s+)?courses?.*$",
            cleaned,
            re.IGNORECASE,
        )
        short_add_match = None
        if not add_shopping_match:
            # Format court : "ajoute chocolat", "rajoute des oeufs"
            short_add_match = re.search(
                r"^(?:ajoute|rajoute)\s+(?!les\s+ingr[ée]dients)(.+)$",
                cleaned,
                re.IGNORECASE,
            )

        target_match = add_shopping_match or short_add_match
        if target_match:
            item = target_match.group(1).strip()
            item = re.sub(r"[?!.,;]+$", "", item).strip()
            item = re.sub(r"^(?:du|de\s+la|des|le|la|les|l'|un|une|d')\s+", "", item, flags=re.IGNORECASE).strip()
            if item and item.lower() not in ["tout", "tous", "rien", "ça", "ceci", "cela", "les"]:
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
