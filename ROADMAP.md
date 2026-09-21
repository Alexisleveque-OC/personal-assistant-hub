# Roadmap Feature : Connecteur Repas & Courses (`feat/meals-shopping-connector`)

> **Règle d'or (AGENTS.md) :**
> - Chaque étape doit être validée **manuellement et explicitement par l'utilisateur** avant de passer à la suivante.
> - La suite de tests automatisés (`pytest`) doit être à **100% au vert** à chaque étape.
> - À la fin de la feature, un **test d'intégration End-to-End (E2E)** doit valider le flux complet de bout en bout.

---

## Vue d'ensemble des Étapes

| Étape | Description | Statut | Validation Utilisateur | Tests Automatisés |
| :--- | :--- | :---: | :---: | :---: |
| **Étape 1** | Analyse approfondie du script existant (`meal-planner`) et compréhension de l'architecture | 🟢 Validé | ✅ Validé par l'utilisateur | N/A (Analyse) |
| **Étape 2** | Mise en place de l'authentification et connexion au Google Sheet (Lecture seule d'abord) | 🟢 Validé | ✅ Validé par l'utilisateur | ✅ 24/24 verts (Mock + Live) |
| **Étape 3** | Inspection et cartographie automatique de la structure réelle du Google Sheet | 🟢 Validé | ✅ Validé par l'utilisateur | ✅ 29/29 verts (Modèles Pydantic) |
| **Étape 4** | Tests de structure du Sheet (Détection de dérive / Schema Drift) | 🟢 Validé | ✅ Validé par l'utilisateur | ✅ 36/36 tests verts (Mock + Live) |
| **Étape 5** | Évolution du Google Sheet / Apps Script pour accueillir les appels de l'API (Liste_Attente) | 🟢 Validé | ✅ Validé par l'utilisateur | ✅ 37/37 tests verts (Mock + Live) |
| **Étape 6** | Implémentation du connecteur `MealsShoppingConnector` et liaison NLU | 🟢 Validé | ✅ Validé par l'utilisateur | ✅ 59/59 tests verts (Unitaires + Live) |
| **Étape 7** | Tests d'intégration End-to-End (E2E) complets & console de test interactive | 🟢 Validé | ⏳ En attente validation finale utilisateur | ✅ 113/113 tests verts (Unitaires + E2E Live) |

---

## Détail des Étapes

### 🟢 Étape 1 : Analyse du script existant (`meal-planner`) & Clarification du Sheet
* **Objectif :** Décortiquer `Code.js` de l'Apps Script local et valider l'organisation réelle du tableur.
* **Résultat validé avec l'utilisateur :**
  * 📅 **Planning annuel (`repas 2026`, `repas 2027`...) :**
    * Structure propre et chronologique sur toute l'année avec 5 colonnes : `Date` (format `JJ/MM/AAAA`), `Jour`, `Midi`, `Soir`, `Notes / Magasin`.
    * Les anciens onglets mensuels sont du legacy.
  * 📖 **Recettes :** Onglet `Recettes` actif (l'ancien onglet `Liste` n'existe plus).
  * 🛒 **Courses & Rayons :** Onglets `Cette semaine` (liste active), `Rayons` (ordre et couleurs) et `Hors_Repas`.
* **Statut :** ✅ Validé par l'utilisateur le 10/09/2026.

### 🟢 Étape 2 : Connexion sécurisée au Google Sheet (Lecture seule d'abord)
* **Objectif :** Mettre en place la passerelle d'authentification vers le Google Sheet cible en respectant les règles de sécurité (`.env`, `.gitignore`).
* **Livrables réalisés :**
  * Clé de compte de service isolée et sécurisée dans `credentials/service_account.json` (ignorée par Git).
  * Variables d'environnement configurées dans `.env`.
  * Dépendances `gspread` et `google-auth` installées dans `.venv`.
  * Résolution dynamique de l'année (`get_expected_meals_sheet_name`, `resolve_meals_worksheet_name`).
  * Gestion stricte et explicite des erreurs : `PlanningWorksheetNotFoundError` levée si une année future (ex: 2027) n'est pas encore créée dans le tableur.
  * Tests automatisés dans `tests/test_sheets_connection.py` (24/24 tests au vert).
* **Statut :** ✅ Validé par l'utilisateur le 10/09/2026.

### 🟢 Étape 3 : Cartographie de la structure réelle du Sheet
* **Objectif :** L'agent inspecte directement les onglets, colonnes et types de données réels du Sheet.
* **Résultats de l'inspection en direct :**
  * 📅 **`repas 2026` (366 lignes) :**
    * Colonnes : `Date` (JJ/MM/AAAA), `Jour`, `Midi`, `Soir`, `Notes / Magasin`.
  * 📖 **`Recettes` (1006 lignes) :**
    * Base de données de plus de 1000 recettes !
    * Colonnes : `Plat`, `Catégorie`, `Catégorie 2`, `Complet` (TRUE/FALSE), puis colonnes E+ pour la liste des ingrédients.
  * 🛒 **`Cette semaine` (32 lignes) :**
    * Lignes 1 à 8 : Tableau du planning de la semaine (Midi col C, Soir col E).
    * Ligne 9 : Séparateur.
    * Lignes 10 à 32 : Grille de courses organisée en 4 colonnes de rayons avec cases à cocher `FALSE`/`TRUE` et noms d'ingrédients.
  * 🏷️ **`Rayons` (17 lignes) :**
    * Liste ordonnancée des rayons : Fruits (1), Légumes (2), Plat préparé (3), Viande (4), etc.
  * 📦 **`Hors_Repas` (64 lignes) :**
    * Produits récurrents : `Nom`, `pré-cocher?` (FALSE/TRUE), `rayon` (Hygiène, Entretien...).
  * 🍹 **`Recette festive` (25 lignes) :**
    * Recettes dédiées Apéro / Gâteaux (ex: `guacamole`, `Chocolat mascarpone`, `Sauce St moret`, `Préfou`...) avec ingrédients.
  * 🥂 **`Courses festives` (11 lignes) :**
    * Grille de courses dédiée pour l'apéro et réceptions, organisée par rayons avec cases à cocher `FALSE`/`TRUE`.
* **Livrables réalisés :**
  * Modèles Pydantic stricts dans `app/connectors/sheets/models.py` (`DayMealPlan`, `Recipe` avec tags festifs, `ShoppingItem`, `RayonSetting`, `SheetSchemaSnapshot`).
  * Tests unitaires des modèles dans `tests/test_sheets_models.py` (29/29 tests au vert).
* **Statut :** ✅ Validé par l'utilisateur le 10/09/2026.

### 🟢 Étape 4 : Tests de structure du Sheet (Détection de dérive / Schema Drift)
* **Objectif :** Créer un système de détection de dérive pour lever des alertes claires et immédiates si un onglet ou une colonne obligatoire est manquant, déplacé ou renommé.
* **Livrables réalisés :**
  * Module `app/connectors/sheets/schema_validator.py` :
    * Exceptions explicites et typées (`SheetSchemaWorksheetNotFoundError`, `SheetSchemaHeaderDriftError`, `SheetSchemaError`) respectant la **Règle 7 (Fail-Fast)**.
    * Modèle de rapport Pydantic `ValidationReport` avec liste d'erreurs et d'avertissements.
    * Classe `SheetSchemaValidator` avec normalisation robuste des chaînes (`normalize_header`) et validation modulaire.
  * Suite de tests complète dans `tests/test_sheet_schema.py` :
    * 6 tests unitaires isolés (mocks) couvrant tous les scénarios de dérive (onglet manquant, colonnes manquantes dans planning, recettes, hors-repas, mode non-strict d'agrégation).
    * 1 test d'intégration réel validant la conformité totale du Google Sheet en direct (`Semaine de repas 2025`).
* **Statut :** ✅ Validé par l'utilisateur le 10/09/2026.

### 🟢 Étape 5 : Préparation du Sheet & Intégration Apps Script (Liste_Attente)
* **Objectif :** Mettre en place l'onglet `Liste_Attente` dans le Google Sheet et adapter l'Apps Script existant (`meal-planner/Code.js`) pour intégrer les besoins au fil de l'eau sans écrasement involontaire.
* **Livrables réalisés :**
  * **Droits Éditeur :** Compte de service basculé en Éditeur par l'utilisateur.
  * **Nouvel onglet `Liste_Attente` créé et stylisé :**
    * Colonnes : `Acheté` (cases à cocher natives Google Sheets), `Article`, `Date d'ajout`.
    * En-tête figé (ligne 1) avec mise en page soignée.
  * **Modèles & Schéma :**
    * Modèle Pydantic `WaitingListItem` ajouté dans `app/connectors/sheets/models.py`.
    * Snapshot et validateur de schéma enrichis pour auditer automatiquement `Liste_Attente`.
  * **Adaptation de `meal-planner/Code.js` (Google Apps Script) :**
    * `getHorsRepasItems()` lit `Liste_Attente` et pré-coche automatiquement les articles en attente dans la barre latérale (qu'ils soient dans `Hors_Repas` ou ajoutés au vol sous leur rayon).
    * `generatePrintSheet()` effectue un nettoyage ciblé : seuls les articles de `Liste_Attente` effectivement cochés lors de la génération sont supprimés, les autres restent préservés.
  * **Tests automatisés :** 37/37 tests au vert (`pytest`), y compris validation de l'onglet `Liste_Attente` en direct sur le Google Sheet réel.
* **Statut :** ✅ Validé par l'utilisateur le 11/09/2026.

### 🟢 Étape 6 : Implémentation du `MealsShoppingConnector` & Intentions NLU
* **Objectif :** Développer `app/connectors/sheets/meals_connector.py` et enrichir `intent_parser.py` en suivant le cycle **TDD Strict (Règle 1)**.
* **Livrables réalisés :**
  * 🔴 **Phase Rouge (Tests d'abord) :**
    * Tests rédigés dans `tests/test_meals_connector.py` et `tests/test_intent_parser.py` et échec constaté lors de la collecte initiale.
  * 🟢 **Phase Verte (Implémentation minimale) :**
    * Énumérations `IntentType` enrichies dans `app/core/models.py`.
    * Règles NLU enrichies dans `app/core/intent_parser.py` avec nettoyage d'articles et gestion d'exclusions.
    * Implémentation complète de `MealsShoppingConnector` dans `app/connectors/sheets/meals_connector.py` :
      * 🍽️ `get_meal_plan` (résolution relative/absolue de date et onglet annuel).
      * 📖 `get_recipe_ingredients` (recherche insensible à la casse dans `Recettes` et `Recette festive`).
      * 🧺 `add_recipe_ingredients_to_shopping_list` (support des inclusions/exclusions et ajout à `Liste_Attente`).
      * ✏️ `set_meal_plan` (mise à jour directe de la cellule midi/soir dans le planning annuel).
      * 🛒 `add_shopping_item` (déduction de rayon dynamique via `Ingredients_Rayons` / `Hors_Repas` avec repli gracieux et warning sur `Divers`).
      * 📋 `get_shopping_list` (agrégation unifiée des articles non achetés de `Liste_Attente` et de `Cette semaine`).
      * ✅ `mark_shopping_items_bought` (coche comme acheté dans `Liste_Attente`).
      * 🧹 `clear_shopping_list` (suppression sécurisée de bas en haut des articles achetés).
  * 🔵 **Phase Refactor & Intégration :**
    * Câblage complet dans `app/main.py` sur l'endpoint `/api/v1/interact` avec support d'injection de mocks (`set_meals_connector`).
    * Tests fonctionnels d'interaction dans `tests/test_interact.py`.
    * Suite complète automatisée : **59/59 tests au vert** (`pytest`).
* **Statut :** ✅ Validé par l'utilisateur le 11/09/2026 (59/59 tests au vert).

### 🟢 Étape 7 : Test d'intégration End-to-End (E2E) & Console Interactive
* **Objectif :** Valider le cycle complet en conditions réelles (phrase utilisateur -> Parser NLU -> Déclencheur connecteur -> Google Sheet en direct) et fournir un moyen immédiat à l'utilisateur de tester son assistant.
* **Livrables réalisés :**
  * **Tests d'intégration E2E (`tests/test_e2e_meals_shopping.py`) :**
    * Test réel de recherche de recette standard (`Recettes`).
    * Test réel de recherche de recette apéro (`Recette festive`).
    * Test réel de lecture et parsing de la liste de courses (`Cette semaine` et `Liste_Attente`).
    * Test réel du cycle de vie complet d'un article dans `Liste_Attente` : ajout d'un article avec rayon automatique, vérification de sa présence, marquage comme acheté (`TRUE`), et nettoyage (`clear`).
  * **Robustification NLU & Connecteur (Suite aux tests réels utilisateur en TDD Strict) :**
    * Support des exclusions de recettes avec déterminants (`sauf le jambon`), au pluriel (`sauf ail et oignons`), et multi-exclusions (`sans le jambon et le fromage`).
    * Prise en charge des tournures composées d'ajout de recette : `ajoute les ingrédients pour faire du... / pour préparer...`.
    * Nettoyage automatique des articles partitifs (`du café` -> `Café`) pour résolution exacte du rayon (`Petit dej + bio`).
    * Reconnaissance des requêtes de recettes étendues (`donnes moi la recette de...`, `j'ai besoin de quoi pour préparer...`).
    * Prise en charge des ajouts d'articles au format court (`ajoute chocolat`).
    * Harmonisation de la synthèse vocale (`pour ce soir`, mention explicite des exclusions).
  * **Optimisation de performance & Quotas Sheets :**
    * Mise en cache mémoire O(1) des catalogues statiques (`Recettes`, `Recette festive`, `Rayons`, `Hors_Repas`) dans le connecteur afin d'éliminer le risque d'épuisement de quota API (429 Too Many Requests).
  * **Console de test interactive (`scripts/chat.py`) & Mémoire conversationnelle (Anaphores & Politesse) :**
    * Script interactif permettant à l'utilisateur de discuter directement avec son assistant en français dans son terminal (`.\.venv\Scripts\python scripts/chat.py`).
    * Gestion de la mémoire de session (`_SESSIONS` et `session_id`) : mémorisation automatique de la dernière recette consultée (`last_recipe`).
    * Résolution contextuelle des anaphores en TDD Strict : requêtes de suivi sans répéter le plat (*« Ajoutes ces ingrédients »*, *« Ajoute-les »*, *« rajoute tout »*, *« tu peux tout rajouter a la liste d'ingrédients »*) avec conservation des clauses d'exclusion (*« sauf ... »*, *« sans ... »*).
    * Gestion native de la politesse et du small-talk (*« ok merci »*, *« bonjour »*, *« parfait »*) avec préservation continue du contexte conversationnel.
    * Protection absolue contre l'ajout de pronoms (*« tout »*, *« rien »*, *« ça »*) comme articles isolés dans la liste de courses.
  * **Raffinement Conversationnel Avancé & Intendance Temporelle (TDD Strict) :**
    * **Résolveur de dates relatives (`app/core/date_resolver.py`) :** Prise en charge des jours de la semaine relatifs (*« que mange t-on jeudi prochain ? »*, *« prévois du poulet pour jeudi »*) et dates calendaires (*« le 24 septembre »*). Élimination totale du bug de repli arbitraire sur le soir même.
    * **Prochain repas réel (`get_next_meal_plan`) :** Pour *« On mange quoi ? »*, analyse de l'heure courante (< 14h vs $\ge$ 14h) et inspection du remplissage effectif du planning. Si le midi est vide, bascule automatique sur le dîner ; si le dîner est passé ou vide, bascule sur le lendemain.
    * **Restitution enrichie midi + soir :** Pour une journée complète (*« qu'est-ce qu'on mange jeudi prochain ? »*), formulation complète décrivant à la fois le déjeuner et le dîner s'ils sont prévus.
    * **Vérification de recette & Dialogue de confirmation (`CONFIRM` / `CANCEL`) :** Détection automatique des recettes non répertoriées dans le carnet (`Recettes` / `Recette festive`) lors d'une planification (*« prévois du poulet pour jeudi »*). L'assistant suspend l'action et demande confirmation à l'utilisateur (*« oui »* $\rightarrow$ insertion, *« non »* $\rightarrow$ abandon).
    * **Anaphore Repas $\rightarrow$ Ingrédients :** Enchaînement fluide après consultation de menu : demander *« On mange quoi ? »* puis *« quels ingrédients faut-il ? »* résout instantanément les ingrédients du plat sans avoir à répéter son nom.
    * **Consultation ciblée Liste d'Attente & Synonymes Courses :** Prise en charge des requêtes *« donne moi la liste d'attente »* pour n'afficher que les éléments ajoutés dynamiquement, et reconnaissance naturelle des questions de courses (*« Qu'est ce que je doit acheter ? »*, *« qu'est-ce qu'il faut acheter »*).
    * **Marquage groupé "Tout acheté" :** Prise en charge de *« J'ai acheté tout les produit de la listes d'attente »*, *« J'ai tout acheté »* avec détection du flag `all=True` et mise à jour collective de tous les articles en un seul appel sans injection de libellé parasite.
  * **Résultat de la suite de tests complète :** **113 tests au total (101 unitaires + 12 de structure et intégration) 100% au vert** en TDD Strict.
* **Statut :** ⏳ En attente de validation finale par l'utilisateur avant fusion / PR de la feature `feat/meals-shopping-connector`.

