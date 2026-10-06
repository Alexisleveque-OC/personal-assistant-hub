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
| **Étape 2** | Connecteur Backend `SportConnector` (lecture séance, calculs Km-Effort, synthèse hebdo & alerte +10%) | 🟢 Terminé | Validé par l'utilisateur | ✅ 11/11 tests dédiés (231/231 total) au vert |
| **Étape 3** | Intentions NLU Gemini Flash & réponses vocales Otis complices (Structured Outputs) | 🟢 Terminé | Validé par l'utilisateur | ✅ 8/8 tests dédiés (239/239 total) au vert |
| **Étape 4** | Intégration `/api/v1/interact`, passerelle de synchronisation, colonnes BPM & import réel des 9 GPX | 🟢 Terminé | Validé par l'utilisateur | ✅ 6/6 tests dédiés (37/37 sport, 245+ total) au vert |
| **Étape 5** | Renforcement Musculaire (Renfo/PPG) & Réajustement vocal a posteriori (RPE / Douleur Périostite) | ⚪ À faire | En attente | Tests unitaires & NLU (TDD strict) |
| **Étape 6** | Cerveau LLM Otis : Analyse fine d'historique & Planification hebdomadaire proactive (gestion périostite) | ⚪ À faire | En attente | Tests LLM structured outputs & TDD |
| **Étape 7** | Interface Graphique PWA Running (Dashboard, jauges charge, ajout rapide course/renfo) | ⚪ À faire | En attente | Tests de routes PWA & UI |
| **Étape 8** | Test d'intégration End-to-End (E2E) complet & Validation smartphone en conditions réelles | ⚪ À faire | En attente | Test E2E complet (100% au vert) |

---

## Détail des Étapes

### 🟢 Étape 1 : Modélisation Pydantic du Sheet Sport, Configuration & Validation de Schéma
* **Objectifs :**
  1. Configuration `spreadsheet_sport_id` et modèles Pydantic (`SportSession`, `SportWeeklySummary`).
  2. Formule standard du Km-Effort : $\text{Km-Effort} = \text{Distance} + \frac{D^+}{100}$.
  3. Validateur de schéma `SportSchemaValidator` (tolérance aux dérives).
* **Statut :** Validé et commité (`de03944`).

---

### 🟢 Étape 2 : Connecteur Backend `SportConnector` (TDD Strict)
* **Objectifs :**
  1. Implémentation du connecteur `SportConnector` (`get_session`, `log_session`, `plan_session`, `get_weekly_summary`).
  2. Respect de la règle des +10% max et gestion de cache RAM.
* **Statut :** Validé et commité (`f8bf73e`).

---

### 🟢 Étape 3 : Intentions NLU Gemini Flash & Cerveau Otis
* **Objectifs :**
  1. Définition des intentions `GET_SPORT_SESSION`, `LOG_SPORT_SESSION`, `GET_SPORT_WEEKLY_SUMMARY`, `PLAN_SPORT_SESSION`.
  2. Prompt persona Otis le scribe complice et protecteur contre les blessures.
* **Statut :** Validé et commité (`241ffd7`).

---

### 🟢 Étape 4 : Intégration `/api/v1/interact`, Passerelle de Synchro, Cardio BPM & Import Réel
* **Objectifs :**
  1. Brancher les intentions sportives dans `/api/v1/interact` (avec support de la semaine courante et des semaines passées).
  2. Endpoints d'ingestion et de webhook Strava (`/api/v1/sport/sync-activity`).
  3. Colonnes BPM (`FC Moy (bpm)`, `FC Max (bpm)`) intégrées dans le Google Sheet.
  4. Importation des 9 vraies séances réelles d'Alexis depuis ses fichiers GPX avec mise à jour automatique de la synthèse hebdomadaire sur 4 semaines (S37 à S40).
* **Statut :** Validé et commité (`a03d275`).

---

### ⚪ Étape 5 : Renforcement Musculaire & Réajustement Vocal a posteriori (RPE / Périostite)
* **Objectifs :**
  1. Support du type de séance `Renforcement` (`Renfo`) : pas de distance kilométrique forcée, mais comptabilisation de la durée et de la Charge RPE ($\text{Durée} \times \text{RPE}$) dans le cumul hebdomadaire.
  2. Méthode métier `update_session(target_date, ...)` dans `SportConnector` permettant de modifier le RPE, le ressenti ou d'ajouter une note de douleur sur une séance passée.
  3. Intention vocale `UPDATE_SPORT_SESSION` :
     - *« Otis, modifie le ressenti de ma course de dimanche à 9 sur 10 à cause de ma périostite »*
     - *« Otis, ajoute une note sur ma course de dimanche : douleur au tibia à J+2 »*
* **Critères de succès :** Tests unitaires validant la modification a posteriori et la mise à jour immédiate du Google Sheet et de la charge RPE.

---

### ⚪ Étape 6 : Cerveau LLM Otis : Analyse fine d'historique & Planification Hebdomadaire Proactive
* **Objectifs :**
  1. Connecter le LLM Gemini à l'historique complet des 4 dernières semaines et au contexte physiologique d'Alexis (antécédent de périostite, besoin de décharge post-compétition).
  2. Nouvelle intention `PLAN_WEEKLY_TRAINING` (*« Otis, prévois-moi ma semaine d'entraînement »*, *« Que me conseilles-tu cette semaine ? »*).
  3. Génération d'un plan hebdomadaire équilibré et personnalisé :
     - Alternance intelligente course / renforcement musculaire ciblé.
     - Prise en compte de la périostite : conseils de terrains souples/herbe, étirements, limitation des chocs.
     - Gestion des semaines de décharge (Deload post-course) sans brider le plafond des semaines futures.
* **Critères de succès :** Tests de génération de plans pertinents et cohérents avec la physiologie d'Alexis.

---

### ⚪ Étape 7 : Interface Graphique PWA Running
* **Objectifs :**
  1. Vue dédiée Running dans la PWA (`app/static/index.html`) avec design moderne et soigné.
  2. Tableau de bord hebdomadaire (Km-Effort, Allure moy, Charge RPE, Alerte Sécurité, Plafond conseillé).
  3. Historique interactif des séances (Course et Renfo).
  4. Formulaire d'ajout rapide (Course ou Renforcement) en complément de la voix.
  5. Affichage du conseil de la semaine d'Otis.
* **Critères de succès :** Interface fluide, responsive et agréable sur smartphone.

---

### ⚪ Étape 8 : Test d'Intégration End-to-End (E2E) & Validation Finale
* **Objectifs :**
  1. Écrire le test d'intégration complet `tests/test_e2e_sport_running.py` couvrant l'ensemble du cycle de vie (consultation $\rightarrow$ log course $\rightarrow$ log renfo $\rightarrow$ modification de douleur a posteriori $\rightarrow$ planification par le LLM).
  2. 100% de la suite de tests au vert (zéro régression).
  3. Validation manuelle en conditions réelles par Alexis sur son smartphone et son Google Sheet.
* **Critères de succès :** Validation totale et feu vert d'Alexis pour le merge sur `develop`.
