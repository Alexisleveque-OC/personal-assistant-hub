# Roadmap Feature : Connecteur Repas & Courses (`feat/meals-shopping-connector`)

> **Règle d'or (AGENTS.md) :**
> - Chaque étape doit être validée **manuellement et explicitement par l'utilisateur** avant de passer à la suivante.
> - La suite de tests automatisés (`pytest`) doit être à **100% au vert** à chaque étape.
> - À la fin de la feature, un **test d'intégration End-to-End (E2E)** doit valider le flux complet de bout en bout.

---

## Vue d'ensemble des Étapes

| Étape | Description | Statut | Validation Utilisateur | Tests Automatisés |
| :--- | :--- | :---: | :---: | :---: |
| **Étape 1** | Analyse approfondie du script existant (`meal-planner`) et compréhension de l'architecture | 🟢 Réalisé | ⏳ En attente | N/A (Analyse) |
| **Étape 2** | Mise en place de l'authentification et connexion au Google Sheet (Lecture seule d'abord) | ⚪ À faire | ⚪ À faire | ⚪ Mocks + Test connexion |
| **Étape 3** | Inspection et cartographie automatique de la structure réelle du Google Sheet | ⚪ À faire | ⚪ À faire | ⚪ Snapshot du schéma |
| **Étape 4** | Conception des tests de non-régression de structure du Sheet (Drift detection) | ⚪ À faire | ⚪ À faire | ⚪ Tests de contrat / schéma |
| **Étape 5** | Évolution du Google Sheet / Apps Script pour accueillir les appels de l'API (si requis) | ⚪ À faire | ⚪ À faire | ⚪ Tests fonctionnels |
| **Étape 6** | Implémentation du connecteur `SheetsConnector` et liaison avec le NLU (`intent_parser`) | ⚪ À faire | ⚪ À faire | ⚪ Tests unitaires connecteur |
| **Étape 7** | Tests d'intégration End-to-End (E2E) complets & validation finale de la feature | ⚪ À faire | ⚪ À faire | ⚪ 100% vert (Unitaires + E2E) |

---

## Détail des Étapes

### 🟢 Étape 1 : Analyse du script existant (`meal-planner`)
* **Objectif :** Décortiquer `Code.js` de l'Apps Script local pour comprendre les onglets, la gestion des menus, des recettes et de la liste de courses.
* **Livrable :** Synthèse d'architecture documentée (onglets mensuels, onglet `Cette semaine`, `Recettes`, `Rayons`, `Hors_Repas`).
* **Critère de passage :** Validation de la compréhension par l'utilisateur.

### ⚪ Étape 2 : Connexion sécurisée au Google Sheet
* **Objectif :** Mettre en place les credentials Google (Compte de service ou OAuth) via variables d'environnement (`.env`) sans jamais les exposer dans Git.
* **Livrable :** Client Python (`gspread` ou `google-api-python-client`) capable de ping le Sheet cible.
* **Critère de passage :** Connexion réussie et validée par l'utilisateur.

### ⚪ Étape 3 : Cartographie de la structure réelle du Sheet
* **Objectif :** L'agent inspecte directement les onglets, colonnes et types de données réels du Sheet.
* **Livrable :** Modèle Pydantic ou rapport de structure documentant l'état exact du document.
* **Critère de passage :** Confirmation par l'utilisateur que la cartographie correspond bien à son usage.

### ⚪ Étape 4 : Tests de structure du Sheet (Détection de dérive / Drift)
* **Objectif :** Créer des tests automatisés qui s'assurent que si une colonne ou un onglet du Sheet change de place, une alerte claire soit remontée.
* **Livrable :** Fichier `tests/test_sheet_schema.py`.
* **Critère de passage :** `pytest` vert sur les tests de schéma.

### ⚪ Étape 5 : Préparation du Sheet / Apps Script pour l'API
* **Objectif :** Si nécessaire, adapter le format d'écriture des données ou ajouter un point d'entrée pour que l'API puisse ajouter un article ou lire le repas du jour de façon optimale.
* **Livrable :** Modifications validées sur le Sheet / Apps Script.
* **Critère de passage :** Validation manuelle des modifications.

### ⚪ Étape 6 : Implémentation du `SheetsConnector` & Intentions NLU
* **Objectif :** Développer `app/connectors/sheets/meal_connector.py` et enrichir `intent_parser.py` :
  * 🍽️ **Consultation de repas (Fonction unifiée avec résolution de date) :**
    * `get_meal_plan(target_date: str | date)` :
      * *Relatif / jour de la semaine :* « Qu'est-ce qu'on mange ce soir ? », « On mange quoi demain ? », « Qu'est-ce qu'on mange jeudi prochain ? » (jour variable).
      * *Date absolue :* « Qu'est-ce qu'on mange le 24 septembre ? » (résolution automatique du jour dans le planning mensuel ou hebdomadaire).
  * ✏️ **Planification / Suggestion de repas *(À discuter et confirmer avant dev)* :**
    * `set_meal_plan(meal: str, target_date: str | date, meal_type: str = "soir")` :
      * « J'aimerais manger des lasagnes jeudi prochain » ou « Prévois une pizza la semaine prochaine ».
      * *Points à arbitrer ensemble :* Vérification si la recette existe dans l'onglet `Recettes`, choix du créneau (Midi vs Soir).
  * 🛒 **Gestion de la liste de courses :**
    * `add_shopping_item(item: str, rayon: Optional[str] = None)` -> « Ajoute du café bio à ma liste de courses ».
    * `get_shopping_list()` -> « Donne-moi la liste de courses ».
* **Livrable :** Code du connecteur + parseur NLU mis à jour + tests unitaires exhaustifs avec mocks étanches.
* **Critère de passage :** Validation explicite des cas d'usage par l'utilisateur et suite `pytest` à 100% au vert.

### ⚪ Étape 7 : Test d'intégration End-to-End (E2E) & Clôture
* **Objectif :** Valider le scénario complet : Phrase utilisateur -> Parser NLU -> Déclenchement du connecteur -> Résultat Sheet vérifié.
* **Livrable :** Test d'intégration E2E + documentation dans `walkthrough.md`.
* **Critère de passage :** Validation finale par l'utilisateur avant création de la Pull Request vers `develop`.
