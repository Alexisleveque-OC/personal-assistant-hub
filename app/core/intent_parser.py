"""Moteur d'analyse et de classification d'intentions en langage naturel."""
import re
from typing import Optional
from app.core.models import IntentType, ParsedIntent
from app.core.date_resolver import resolve_date_expression


def _normalize_rayon(raw: str) -> str:
    """Normalise le nom du rayon en insensibilité à la casse, singulier/pluriel et synonymes."""
    r = raw.strip().strip("'\"").strip()
    r_lower = r.lower()

    mapping = {
        "fruit": "Fruits",
        "fruits": "Fruits",
        "legume": "Légumes",
        "legumes": "Légumes",
        "légume": "Légumes",
        "légumes": "Légumes",
        "viande": "Viande",
        "viandes": "Viande",
        "boucherie": "Viande",
        "charcuterie": "Charcuterie",
        "charcuteries": "Charcuterie",
        "dessert": "Dessert",
        "desserts": "Dessert",
        "fromage": "Fromage/Beurre/Creme",
        "fromages": "Fromage/Beurre/Creme",
        "beurre": "Fromage/Beurre/Creme",
        "creme": "Fromage/Beurre/Creme",
        "crème": "Fromage/Beurre/Creme",
        "fromage/beurre/creme": "Fromage/Beurre/Creme",
        "apero": "Apéro",
        "apéro": "Apéro",
        "oeuf": "Oeufs/farine/lait",
        "oeufs": "Oeufs/farine/lait",
        "œufs": "Oeufs/farine/lait",
        "farine": "Oeufs/farine/lait",
        "lait": "Oeufs/farine/lait",
        "petit dej": "Petit dej + bio",
        "petit dejeuner": "Petit dej + bio",
        "petit déjeuner": "Petit dej + bio",
        "bio": "Petit dej + bio",
        "produit du monde": "Produit du monde",
        "produits du monde": "Produit du monde",
        "monde": "Produit du monde",
        "epicerie": "Épicerie",
        "épicerie": "Épicerie",
        "boisson": "Boisson",
        "boissons": "Boisson",
        "hygiene": "Hygiène",
        "hygiène": "Hygiène",
        "pq": "PQ + entretien",
        "entretien": "PQ + entretien",
        "pq + entretien": "PQ + entretien",
        "surgele": "Surgelé",
        "surgelé": "Surgelé",
        "surgeles": "Surgelé",
        "surgelés": "Surgelé",
        "plat prepare": "Plat préparé",
        "plat préparé": "Plat préparé",
        "plats prepares": "Plat préparé",
        "plats préparés": "Plat préparé",
    }
    for key, mapped in mapping.items():
        if r_lower == key or r_lower == f"{key}s":
            return mapped
    return r.capitalize()


class IntentParser:
    """Analyseur d'intentions.
    
    Combine des règles heuristiques locales déterministes (ultra-rapides et sans coût)
    avec possibilité de délégation à un LLM pour les cas ambigus.
    """

    def parse(self, text: str, context: Optional[dict] = None) -> ParsedIntent:
        cleaned = text.strip().lower()

        # 0.00 Confirmation ou annulation interactive d'une action en attente
        if context and context.get("pending_action"):
            if re.search(r"^(?:oui|ouais|vas[- ]y|confirme|c[' ]est\s+bon|exactement|tout\s+[àa]\s+fait|absolument|ok|d[' ]accord)\b", cleaned):
                return ParsedIntent(
                    intent=IntentType.CONFIRM,
                    confidence=0.95,
                    parameters={"action": context["pending_action"]},
                    raw_query=text,
                )
            if re.search(r"^(?:non|nan|annule|laisse\s+tomber|pas\s+la\s+peine|non\s+merci)\b", cleaned):
                return ParsedIntent(
                    intent=IntentType.CANCEL,
                    confidence=0.95,
                    parameters={"action": context["pending_action"]},
                    raw_query=text,
                )

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

        # 2. Consultation de recette ou d'ingrédients ("quels sont les ingrédients pour...", "qu'est-ce qu'il faut pour faire...", "donnes-moi la recette du préfou", "quel est la recette pour le chilli sin carne")
        recipe_direct_match = None
        recipe_ing_match = None
        if not re.search(r"^(?:ajoute|mets|rajoute)\b", command_cleaned):
            recipe_direct_match = re.search(
                r"(?:(?:(?:(?:me|nous)\s+)?(?:donne[sz]?|donner)(?:-moi|\s+moi)?|quel(?:le)?[sz]?\s+est|c[' ]est\s+quoi)\s+(?:la\s+)?recette|(?:la\s+)?recette)\s+(?:pour\s+(?:faire|pr[ée]parer|cuisiner)?\s*|d[eu]|de\s+la|de\s+l[' ]|des|d[' ])\s*(.+)",
                command_cleaned,
                re.IGNORECASE,
            )
            recipe_ing_match = re.search(
                r"(?:ingr[ée]dients\s+(?:pour|d[eu]|de\s+la|de\s+l[' ]|des|d[' ])|"
                r"(?:qu[' ]?est[- ]ce\s+qu[' ]?il\s+faut|il\s+(?:me\s+)?faut\s+quoi|(?:j[' ]?ai\s+)?besoin\s+de\s+quoi)\s+pour\s+(?:faire|pr[ée]parer|cuisiner)?\s*(?:d[eu]|de\s+la|de\s+l[' ]|des|un[e]?|le|la|les|l[' ]|d[' ])?)\s*(.+)",
                command_cleaned,
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

        # 2.bis Anaphore d'ingrédients : "quel ingredients faut-il ?", "il faut quoi ?"
        recipe_anaphora_match = re.search(
            r"^(?:(?:quel(?:le)?[sz]?\s+ingr[ée]dients?\s+faut[- ]il|il\s+faut\s+quoi(?:\s+comme\s+ingr[ée]dients?)?|quel(?:le)?[sz]?\s+sont\s+les\s+ingr[ée]dients?|qu[' ]?est[- ]ce\s+qu[' ]?il\s+faut))\s*[?!.]*$",
            command_cleaned,
            re.IGNORECASE,
        )
        if recipe_anaphora_match:
            last_recipe = (context or {}).get("last_recipe")
            if last_recipe:
                return ParsedIntent(
                    intent=IntentType.GET_RECIPE_INGREDIENTS,
                    confidence=0.95,
                    parameters={"recipe": last_recipe},
                    raw_query=text,
                )
            else:
                return ParsedIntent(
                    intent=IntentType.UNKNOWN,
                    confidence=0.2,
                    parameters={},
                    raw_query=text,
                )

        # 3. Planification de repas ("mets des pâtes carbonara ce soir", "prévois du poulet pour jeudi", "j'aimerai mangé du risotto jeudi prochain")
        set_meal_match = re.search(
            r"(?:(?:j[' ]?aimerai[sz]?|je\s+voudrai[sz]?|on\s+(?:pourrait|va))\s+(?:manger|mang[ée]|cuisiner|faire)|(?:mets|prévois|programme|planifie))\s+(.+)$",
            command_cleaned,
            re.IGNORECASE,
        )
        if set_meal_match and not re.search(r"\b(?:ingr[ée]dient|liste\s+(?:de\s+|des\s+)?courses?)\b", command_cleaned):
            raw_payload = set_meal_match.group(1).strip()
            resolved = resolve_date_expression(raw_payload)
            meal_candidate = resolved.cleaned_query if resolved.cleaned_query else raw_payload
            meal_candidate = re.sub(r"\b(?:pour|ce\s+soir|ce\s+midi|demain)\b.*$", "", meal_candidate, flags=re.IGNORECASE).strip()
            meal_candidate = re.sub(r"^(?:du|de\s+la|des|de\s+l[' ]|d[' ]|le|la|les|l[' ]|un[e]?)\s+", "", meal_candidate, flags=re.IGNORECASE).strip()
            meal_candidate = re.sub(r"[?!.,;]+$", "", meal_candidate).strip()
            if meal_candidate:
                params = {"meal": meal_candidate}
                if resolved.period:
                    params["period"] = resolved.period
                if resolved.target_date:
                    params["target_date"] = resolved.date_str
                if resolved.day_name:
                    params["day_name"] = resolved.day_name
                return ParsedIntent(
                    intent=IntentType.SET_MEAL_PLAN,
                    confidence=0.95,
                    parameters=params,
                    raw_query=text,
                )

        # 4. Consultation repas ("qu'est-ce qu'on mange ce soir / midi / demain ?", "on mange quoi ?", "que mange t-on...")
        if re.search(r"(?:qu[' ]?est[- ]ce\s+qu[' ]?on\s+mange|on\s+mange\s+quoi|que\s+mange[- ]t[- ]on|menu\s+d[eu]|quel\s+est\s+le\s+repas)", cleaned):
            resolved = resolve_date_expression(cleaned)
            params = {}
            if resolved.period:
                params["period"] = resolved.period
            if resolved.target_date:
                params["target_date"] = resolved.date_str
            if resolved.day_name:
                params["day_name"] = resolved.day_name
            return ParsedIntent(
                intent=IntentType.GET_MEAL_PLAN,
                confidence=0.95,
                parameters=params,
                raw_query=text,
            )

        # 5. Marquage courses achetées ("j'ai acheté le café bio et le dentifrice", "j'ai tout acheté", "j'ai acheté tout les produit de la listes d'attente")
        if re.search(
            r"^(?:j[' ]?ai\s+tout\s+(?:achet[ée]|pris)|(?:j[' ]?ai\s+(?:achet[ée]|pris)\s+)?(?:tout(?:es?|s)?|tous?)(?:\s+(?:les?|la))?(?:\s+(?:articles?|produits?))?(?:\s+(?:de|sur)\s+(?:la\s+)?listes?(?:\s+d[' ]attente|\s+de\s+courses?)?)?|tout\s+est\s+(?:achet[ée]|pris))\s*[?!.]*$",
            cleaned,
            re.IGNORECASE,
        ) and not re.search(r"^j[' ]?ai\s+achet[ée]\s+(?!pour\s+\d)(?:du|des|le|la|les|un|une)\s+[a-z0-9]+(?:\s+(?:et|avec)\s+|$)", cleaned, re.IGNORECASE):
            return ParsedIntent(
                intent=IntentType.MARK_SHOPPING_BOUGHT,
                confidence=0.95,
                parameters={"all": True},
                raw_query=text,
            )

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

        # 7. Consultation liste de courses (spécifique rayon, reste à acheter dans Cette semaine, ou globale)
        # 7.1 Requête sur un rayon spécifique ("j'ai quoi a acheter au rayon Fruits", "au rayon Charcuterie", "il me reste quoi a acheter au rayon Légumes", "qu'est-ce qui est déjà coché au rayon Fruits ?")
        rayon_match = re.search(
            r"(?:(?:au|dans\s+le)\s+rayon|rayon)\s+['\"]?([a-zA-ZÀ-ÿ0-9 /+-]+?)['\"]?(?:\s+(?:s[' ]il\s+te\s+pla[îi]t|svp|stp))?\s*[?.,!;:]*$",
            cleaned,
            re.IGNORECASE,
        )
        if rayon_match and not re.search(r"^(?:ajoute|mets|rajoute)\b", cleaned):
            is_chk_query = bool(re.search(r"(?:d[ée]j[àa]\s+(?:coch[ée]|pris|achet[ée])|qui\s+est\s+coch[ée])", cleaned, re.IGNORECASE))
            status = "checked" if is_chk_query else "remaining"
            rayon_name = _normalize_rayon(rayon_match.group(1))
            return ParsedIntent(
                intent=IntentType.GET_SHOPPING_LIST,
                confidence=0.95,
                parameters={
                    "filter": "current_week",
                    "rayon": rayon_name,
                    "status": status,
                },
                raw_query=text,
            )

        # 7.2 Articles déjà cochés (général) ("qu'est-ce qui est déjà coché ?", "qu'est ce que j'ai déjà coché")
        if re.search(
            r"^(?:qu[' ]?est[- ]ce\s+(?:qui\s+est|que\s+j[' ]?ai)\s+d[ée]j[àa]\s+(?:coch[ée]|pris|achet[ée])|articles?\s+d[ée]j[àa]\s+coch[ée]s?)\s*[?!.]*$",
            cleaned,
            re.IGNORECASE,
        ):
            return ParsedIntent(
                intent=IntentType.GET_SHOPPING_LIST,
                confidence=0.95,
                parameters={"filter": "current_week", "status": "checked"},
                raw_query=text,
            )

        # 7.3 Reste à acheter dans 'Cette semaine' ("Il me reste quoi a acheté", "il me reste quoi à acheter", "qu'est ce qu'il me reste a acheter ?")
        if "budget" not in cleaned and re.search(
            r"(?:(?:qu[' ]?est[- ]ce\s+(?:qu[' ]?il|qui)\s+(?:me\s+)?reste|(?:il\s+(?:me\s+)?reste\s+quoi)|qu[' ]?est[- ]ce\s+que\s+je\s+dois\s+encore\s+acheter)\s*(?:[àa]\s+achet[ée]r?|dans\s+(?:les\s+courses|le\s+caddie)|sur\s+la\s+liste(?:\s+de\s+la\s+semaine)?)?|il\s+(?:me\s+)?reste\s+quoi\s+[àa]\s+achet[ée]r?)",
            cleaned,
            re.IGNORECASE,
        ):
            return ParsedIntent(
                intent=IntentType.GET_SHOPPING_LIST,
                confidence=0.95,
                parameters={"filter": "current_week", "status": "remaining"},
                raw_query=text,
            )

        # 7.4 Consultation globale ou liste d'attente ("donne-moi la liste de courses", "donne moi la liste d'attente", "qu'est ce que je doit acheter ?")
        if re.search(
            r"(?:liste\s+(?:de\s+|des\s+)?courses?|liste\s+d[' ]attente|qu[' ]?est[- ]ce\s+qu[' ]?il\s+faut\s+acheter|qu[' ]?est[- ]ce\s+(?:que\s+)?(?:je|on)\s+doi[ts]\s+acheter|qu[' ]?est[- ]ce\s+qu[' ]?il\s+y\s+a\s+[àa]\s+acheter|quoi\s+acheter)",
            cleaned,
            re.IGNORECASE,
        ):
            params = {}
            if "attente" in cleaned:
                params["filter"] = "waiting_list"
            return ParsedIntent(
                intent=IntentType.GET_SHOPPING_LIST,
                confidence=0.95,
                parameters=params,
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
