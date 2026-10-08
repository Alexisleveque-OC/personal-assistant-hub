# Roadmap Feature : Phase 6.5 - Migration Sport vers SQLite & Résolution Temporelle (`feat/sport-sqlite-migration`)

> **Règles d'or (AGENTS.md) :**
> - Chaque étape doit être validée **manuellement et explicitement par l'utilisateur** avant de passer à la suivante.
> - La suite de tests automatisés (`pytest`) doit être à **100% au vert** à chaque étape (TDD strict : Rouge ➔ Vert ➔ Refactor).
> - Zéro commit prématuré sans test ni validation préalable.
> - À la fin de la feature, un **test d'intégration End-to-End (E2E)** doit valider le flux complet de bout en bout.

---

## Vue d'ensemble des Étapes

| Étape | Description | Statut | Validation Utilisateur | Tests Automatisés |
| :--- | :--- | :---: | :---: | :---: |
| **Étape 1** | **Schéma Relationnel SQLite Sport :** Tables `sport_sessions` et `sport_weekly_summaries` dans `DatabaseManager` (`hub_data.db`), index, contraintes et méthodes CRUD | 🟢 Terminé | Validé par l'utilisateur | ✅ 4/4 tests dédiés (393/393 total) au vert |
| **Étape 2** | **Connecteur Backend `SqlSportConnector` :** Implémentation haute performance (< 1 ms), parité fonctionnelle complète avec `SportConnector` et calculs de charge en mémoire | 🟡 En cours | En attente de lancement | Phase Rouge TDD à initier |
| **Étape 3** | **Script de Migration & Outils d'Export/Backup :** Aspiration complète du Google Sheet actif vers SQLite et utilitaire d'export/backup de secours (CSV / JSON) | ⚪ Prévu | - | Tests de migration & export |
| **Étape 4** | **Résolution Sémantique Temporelle (« Ma dernière séance ») :** Interrogation dynamique en base SQLite pour « ma dernière séance », « mon dernier footing », « mon dernier renfo » | ⚪ Prévu | - | Tests NLU & Handler |
| **Étape 5** | **Ergonomie Vocale & Dates Naturelles :** Suppression du « Pour aujourd'hui... » hardcodé, dates orales naturelles (« du 7 octobre »), tolérance infinitif et lexique (« renfort ») | ⚪ Prévu | - | Tests réponses vocales & NLU |
| **Étape 6** | **Bascule Globale vers `SqlSportConnector` :** Injection du connecteur SQLite par défaut dans `dependencies.py`, routes REST et découplage total de Google Sheets | ⚪ Prévu | - | Tests API & régression globale |
| **Étape 7** | **Test d'Intégration End-to-End (E2E) & Recette Finale :** Validation complète du cycle (persistance locale, requêtes temporelles, oralisation naturelle, export de secours) | ⚪ Prévu | - | Test E2E Live & 100% vert |

---

## Détail des Étapes

### 🟢 Étape 1 : Schéma Relationnel SQLite & Persistance Sport (`sport_sessions`, `sport_weekly_summaries`)
* **Objectifs réalisés :**
  1. **Schéma de données étendu dans `DatabaseManager.init_db()` :**
     - Table `sport_sessions` créée avec colonnes typées, contraintes et index (`idx_sport_sessions_date`, `idx_sport_sessions_semaine`, `idx_sport_sessions_type`, `idx_sport_sessions_statut`).
     - Table `sport_weekly_summaries` créée avec contrainte d'unicité `UNIQUE(semaine, annee)` et index composé `idx_sport_summaries_semaine_annee`.
  2. **Méthodes CRUD et requêtage ajoutées dans `DatabaseManager` :**
     - Sessions : `add_sport_session`, `get_sport_session_by_id`, `get_sport_session_by_date`, `get_sport_sessions` (avec filtres de date, semaine, type, statut, pagination), `get_last_sport_session`, `update_sport_session`, `delete_sport_session`.
     - Synthèses : `upsert_sport_weekly_summary` (avec `ON CONFLICT DO UPDATE`), `get_sport_weekly_summary`, `get_all_sport_weekly_summaries`, `delete_sport_weekly_summary`.
  3. **TDD strict :** 4/4 tests unitaires validés dans `tests/test_database_sport.py`.
  4. **Zéro régression :** 393/393 tests au vert sur l'ensemble du projet.
* **Statut :** 🟢 Terminé, prêt pour validation utilisateur.

---

### ⚪ Étape 2 : Connecteur Backend `SqlSportConnector`
* **Objectifs :**
  1. Créer `app/connectors/sqlite/sport_connector.py` implémentant l'interface métier attendue par l'application :
     - `get_session(target_date)`
     - `get_all_sessions()`
     - `get_week_sessions(week_num, year)`
     - `log_session(session_data)`
     - `plan_session(...)`
     - `plan_weekly_sessions(...)`
     - `update_session(...)`
     - `get_weekly_summary(week_num, year)`
     - `get_all_summaries(year)`
  2. Remplacer les lectures réseau Google Sheets par des requêtes SQLite locales exécutées en moins de 1 milliseconde.
  3. Mettre à jour automatiquement les synthèses hebdomadaires lors de chaque ajout ou modification de séance.
* **Critères d'acceptation :**
  - Parité fonctionnelle à 100% avec `SportConnector` (Google Sheets).
  - Tests unitaires complets sur base SQLite temporaire isolée.

---

### ⚪ Étape 3 : Script d'Aspiration & Migration Google Sheets ➔ SQLite + Outil d'Export/Backup
* **Objectifs :**
  1. Développer un script one-off `scripts/migrate_sport_sheets_to_sqlite.py` capable :
     - De lire l'intégralité de l'historique de l'onglet `Séances` et de la `Synthèse_Hebdo` depuis le Google Sheet actif via les identifiants existants.
     - De nettoyer, valider et insérer toutes les séances et synthèses dans la base SQLite unifiée locale (`hub_data.db`).
     - De gérer l'idempotence (éviter les doublons si le script est relancé).
  2. Fournir un outil d'export/backup de secours (`scripts/export_sport_data.py`) permettant d'exporter les données sportives en formats standards (JSON et CSV).
* **Critères d'acceptation :**
  - Script testable avec mock et vérification de la parfaite intégrité des données importées et exportées.

---

### ⚪ Étape 4 : Résolution Sémantique Temporelle (« Ma dernière séance »)
* **Objectifs :**
  1. Ajouter dans `SqlSportConnector` et `DatabaseManager` une méthode de recherche de la dernière séance :
     - `get_last_session(session_type: Optional[SportSessionType] = None, status: Optional[SportSessionStatus] = SportSessionStatus.REALISE)`
  2. Enrichir `IntentParser` (regex locales et prompt Gemini) pour détecter les formulations relatives :
     - « ma dernière séance », « ma dernière course », « mon dernier footing », « mon dernier renfo / renforcement ».
  3. Intégrer la résolution dynamique dans `app/handlers/sport_handler.py` pour récupérer la dernière entrée réelle en base au lieu de retomber sur la date d'aujourd'hui.
* **Critères d'acceptation :**
  - Tests NLU et tests de handler validant la bonne restitution de la dernière séance selon le contexte demandé.

---

### ⚪ Étape 5 : Ergonomie Vocale, Formulations Naturelles & Tolérances Linguistiques
* **Objectifs :**
  1. Supprimer le texte hardcodé « Pour aujourd'hui... » de `sport_handler.py` lors de la consultation d'une séance à une autre date ou de la dernière séance.
  2. Implémenter un formateur oral de dates naturelles (`format_natural_spoken_date(target_date)`) :
     - Exemples : « d'aujourd'hui », « d'hier », « de demain », « du mardi 6 octobre ».
  3. Améliorer la flexibilité grammaticale :
     - Support de l'infinitif dans les requêtes vocales (« modifier ma séance », « planifier mon footing »).
     - Déclinaisons de vocabulaire : « renfort », « renfo », « muscu », « PPG » mappés automatiquement vers `SportSessionType.RENFORCEMENT`.
* **Critères d'acceptation :**
  - Réponses vocales chaleureuses, fluides et exemptes d'incohérences de date. Tests unitaires dédiés.

---

### ⚪ Étape 6 : Bascule Globale vers `SqlSportConnector` & Nettoyage
* **Objectifs :**
  1. Mettre à jour `app/core/dependencies.py` pour instancier et injecter `SqlSportConnector` par défaut.
  2. Rendre la variable d'environnement `SPREADSHEET_SPORT_ID` optionnelle (suppression de l'erreur bloquante si absente).
  3. Mettre à jour `app/routers/sport.py` et le dashboard pour interagir avec le connecteur SQLite unifié.
* **Critères d'acceptation :**
  - 100% des tests de régression existants au vert sans dépendance externe à Google Sheets.

---

### ⚪ Étape 7 : Test d'Intégration End-to-End (E2E) & Recette Finale
* **Objectifs :**
  1. Écrire `tests/test_e2e_sport_sqlite_migration.py` validant l'ensemble du flux :
     - Initialisation base locale SQLite.
     - Enregistrement vocal d'une séance et consultation de « ma dernière séance ».
     - Modification orale avec formulations naturelles et infinitif.
     - Calculs physiologiques instantanés et export de secours.
  2. Effectuer la recette fonctionnelle complète.
* **Critères d'acceptation :**
  - Suite de tests 100% au vert.
  - Validation manuelle utilisateur.
