# Roadmap Feature : Module Sport Running & Mini-Coach Otis (`feat/sport-running-coach`)

> **Règles d'or (AGENTS.md) :**
> - Chaque étape doit être validée **manuellement et explicitement par l'utilisateur** avant de passer à la suivante.
> - La suite de tests automatisés (`pytest`) doit être à **100% au vert** à chaque étape (TDD strict).
> - À la fin de la feature, un **test d'intégration End-to-End (E2E)** doit valider le flux complet de bout en bout.

---

## Vue d'ensemble des Étapes

| Étape | Description | Statut | Validation Utilisateur | Tests Automatisés |
| :--- | :--- | :---: | :---: | :---: |
| **Étape 1** | Modélisation Pydantic du Sheet Sport, configuration & validation de schéma (Schema Drift) | 🟢 Terminé | Validé par l'utilisateur | ✅ 12/12 tests dédiés (220/220 total) au vert |
| **Étape 2** | Connecteur Backend `SportConnector` (lecture séance, calculs Km-Effort, synthèse hebdo & alerte +10%) | 🟢 Terminé | En attente de validation | ✅ 11/11 tests dédiés (231/231 total) au vert |
| **Étape 3** | Intentions NLU Gemini Flash & réponses vocales Otis complices (Structured Outputs) | ⚪ À faire | En attente | Tests unitaires NLU & parsing vocal |
| **Étape 4** | Intégration `/api/v1/interact`, cache RAM & passerelle de synchronisation automatique | ⚪ À faire | En attente | Tests API & BackgroundTasks |
| **Étape 5** | Test d'intégration End-to-End (E2E) complet & validation smartphone en conditions réelles | ⚪ À faire | En attente | Test E2E complet (100% au vert) |

---

## Détail des Étapes

### 🟡 Étape 1 : Modélisation Pydantic du Sheet Sport, Configuration & Validation de Schéma
* **Objectifs :**
  1. Ajouter `spreadsheet_sport_id: str = ""` dans `app/config.py` et `.env.example`.
  2. Créer `app/connectors/sheets/sport_models.py` :
     - Modèle de séance `SportSession` (date, semaine ISO, statut, type, distance, D+, durée, km_effort, vitesse_kmh, allure_minkm, ressenti_rpe, charge_rpe, notes, strava_id).
     - Modèle de synthèse hebdomadaire `SportWeeklySummary` (semaine, année, nb_seances, km_total, d_plus_total, km_effort_total, duree_totale, allure_moyenne, evolution_charge_pct, alerte_securite, plafond_max_s_plus_1).
  3. Formule standard du Km-Effort : $\text{Km-Effort} = \text{Distance} + \frac{D^+}{100}$.
  4. Créer le validateur de schéma `SportSchemaValidator` pour détecter tout dérive de colonnes ou d'onglets (`Seances`, `Synthese_Hebdo`).
  5. Tests unitaires dans `tests/test_sport_models.py` et `tests/test_sport_schema.py`.
* **Critères de succès :** 100% des tests de modèles et de schéma au vert, documentation prête pour le classeur Google Sheets d'Alexis.

---

### ⚪ Étape 2 : Connecteur Backend `SportConnector` (TDD Strict)
* **Objectifs :**
  1. Créer `app/connectors/sheets/sport_connector.py` dérivant de `BaseConnector`.
  2. Implémenter les méthodes métier :
     - `get_session(target_date)` : lecture de la séance planifiée ou réalisée du jour/date cible.
     - `log_session(session_data)` : écriture / mise à jour d'une séance réalisée avec calcul automatique des métriques.
     - `plan_session(plan_data)` : planification d'une séance future.
     - `get_weekly_summary(week_num, year)` : lecture / agrégation de la semaine et calcul des indicateurs de sécurité mini-coach.
  3. Gestion du respect strict de la règle des +10% max et détection des semaines de décharge (Deload).
* **Critères de succès :** Tests unitaires exhaustifs avec mocks et validation sans régression.

---

### ⚪ Étape 3 : Intentions NLU Gemini Flash & Cerveau Otis
* **Objectifs :**
  1. Définir les nouvelles intentions dans `app/core/models.py` :
     - `GET_SPORT_SESSION` (*« Qu'est-ce que j'ai comme séance aujourd'hui ? »*)
     - `LOG_SPORT_SESSION` (*« J'ai couru 8 km en 42 minutes avec 120m de dénivelé, ressenti 6 sur 10 »*)
     - `GET_SPORT_WEEKLY_SUMMARY` (*« J'en suis à combien de kilomètres cette semaine ? »*, *« Quel est mon bilan de course ? »*)
     - `PLAN_SPORT_SESSION` (*« Planifie-moi un fractionné jeudi »*)
  2. Enrichir le prompt système de Gemini Flash avec l'esprit d'**Otis le scribe** (bienveillant, complice, précis sur les calculs d'allure et protecteur contre les blessures).
  3. Extraction structurée Pydantic des entités (durée en secondes/minutes, distance en km, D+ en m, RPE 1-10).
* **Critères de succès :** Suite de tests NLU validant la reconnaissance naturelle sans ambiguïté.

---

### ⚪ Étape 4 : Intégration `/api/v1/interact`, Cache & Passerelle de Synchro
* **Objectifs :**
  1. Brancher les intentions sportives dans le routeur principal `/api/v1/interact` et mobile.
  2. Cache mémoire RAM pour les consultations instantanées (< 0.5s).
  3. Écritures Google Sheets en arrière-plan (`BackgroundTasks`) pour retour vocal immédiat.
  4. Mise en place de l'endpoint d'ingestion pour synchronisation (Webhook Strava ou passerelle d'activités).
* **Critères de succès :** Réponses vocales fluides et mise à jour transparente du Google Sheet.

---

### ⚪ Étape 5 : Test d'Intégration End-to-End (E2E) & Validation Finale
* **Objectifs :**
  1. Écrire le test d'intégration complet `tests/test_e2e_sport_running.py`.
  2. Valider l'ensemble du flux : consultation matinale $\rightarrow$ course $\rightarrow$ saisie vocale $\rightarrow$ mise à jour du bilan hebdo $\rightarrow$ recommandation de la prochaine séance par Otis.
  3. Validation manuelle en conditions réelles par l'utilisateur.
* **Critères de succès :** 100% de la suite de tests au vert (zéro régression) et validation manuelle d'Alexis.
