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
| **Étape 2** | **Connecteur Backend `SqlSportConnector` :** Implémentation haute performance (< 1 ms), parité fonctionnelle complète avec `SportConnector` et calculs de charge en mémoire | 🟢 Terminé | Validé par l'utilisateur | ✅ 8/8 tests dédiés (401/401 total) au vert |
| **Étape 3** | **Script de Migration & Outils d'Export/Backup :** Aspiration complète du Google Sheet actif vers SQLite et utilitaire d'export/backup de secours (CSV / JSON) | 🟢 Terminé | Validé par l'utilisateur | ✅ 2/2 tests dédiés (403/403 total) au vert |
| **Étape 4** | **Résolution Sémantique Temporelle (« Ma dernière séance ») :** Interrogation dynamique en base SQLite pour « ma dernière séance », « mon dernier footing », « mon dernier renfo » | 🟢 Terminé | Validé par l'utilisateur | ✅ 4/4 tests dédiés (407/407 total) au vert |
| **Étape 5** | **Ergonomie Vocale & Dates Naturelles :** Suppression du « Pour aujourd'hui... » hardcodé, dates orales naturelles (« du 7 octobre »), tolérance infinitif et lexique (« renfort ») | 🟢 Terminé | Validé par l'utilisateur | ✅ 4/4 tests dédiés (411/411 total) au vert |
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
* **Statut :** 🟢 Validé par l'utilisateur et commité (`295a5b3`).

---

### 🟢 Étape 2 : Connecteur Backend `SqlSportConnector`
* **Objectifs réalisés :**
  1. **Implémentation de `SqlSportConnector` dans `app/connectors/sqlite/sport_connector.py` :**
     - Respect de l'interface `BaseConnector` avec propriété `name = "sqlite_sport"`, méthode `is_healthy()` et méthode générique `execute_action()`.
     - Parité fonctionnelle complète avec `SportConnector` : `get_session`, `get_all_sessions`, `get_week_sessions`, `log_session`, `plan_session`, `plan_weekly_sessions`, `update_session`, `get_weekly_summary`, `get_all_summaries`.
  2. **Performance & Temps Réel :**
     - Zéro latence réseau Google Sheets (< 1 ms d'exécution en SQLite WAL local).
     - Zéro quota API Google.
  3. **Synchronisation automatique des métriques physiologiques :**
     - Calcul automatique de la synthèse hebdomadaire et persistance dans `sport_weekly_summaries` à chaque enregistrement ou mise à jour de séance.
     - Gestion du `target_type` pour cibler une séance précise en cas de séances multiples à la même date (ex: Footing + Renforcement).
     - Gestion d'extension de remarques (`append_remarques`, `append_notes`).
  4. **TDD strict :** 8/8 tests unitaires validés dans `tests/test_sql_sport_connector.py`.
  5. **Zéro régression :** 401/401 tests au vert sur l'ensemble du projet.
* **Statut :** 🟢 Validé par l'utilisateur et commité (`cf48319`).

---

### 🟢 Étape 3 : Script d'Aspiration & Migration Google Sheets ➔ SQLite + Outil d'Export/Backup
* **Objectifs réalisés :**
  1. **Script de migration one-off (`scripts/migrate_sport_sheets_to_sqlite.py`) :**
     - Aspiration complète des séances et synthèses depuis le Google Sheet actif via `SportConnector`.
     - Insertion et mise à jour idempotente dans SQLite (zéro doublon en cas de réexécution).
     - Support CLI avec options `--db-path` et `--dry-run`.
  2. **Outil d'export/backup de secours (`scripts/export_sport_data.py`) :**
     - Export complet en JSON (`sport_backup_YYYYMMDD_HHMMSS.json`).
     - Export en CSV séparé (`sport_sessions_*.csv` et `sport_weekly_summaries_*.csv`).
     - Support CLI avec options `--output-dir`, `--format json|csv|all`, `--db-path`.
  3. **TDD strict :** 2/2 tests unitaires validés dans `tests/test_sport_migration_and_export.py`.
  4. **Zéro régression :** 403/403 tests au vert sur l'ensemble du projet.
* **Statut :** 🟢 Validé par l'utilisateur et commité (`ffe8712`).

---

### 🟢 Étape 4 : Résolution Sémantique Temporelle (« Ma dernière séance »)
* **Objectifs réalisés :**
  1. **Méthode `get_last_session` dans `SqlSportConnector` :**
     - Interrogation directe de SQLite (`get_last_sport_session`) filtrée par statut (`SportSessionStatus.REALISE` par défaut) et type de séance optionnel (`EF`, `Fractionné`, `Renforcement`, etc.).
  2. **Parsing sémantique dans `IntentParser` :**
     - Détection précise des requêtes temporelles : « ma dernière séance », « rappelle-moi mon dernier footing », « mon dernier renfo », « mon dernier renforcement ».
     - Extraction dynamique du type de séance cible (`session_type`).
     - Exclusion des consultations temporelles sportives de la création de tâches Google Tasks.
  3. **Résolution dynamique dans `sport_handler.py` :**
     - Traitement du cas `is_last` sans jamais présumer arbitrairement `date.today()`.
     - Formulation orale personnalisée : « Votre dernière séance était une séance de Fractionné de 10 km : 6x400m à 3'45/km. »
     - Réponse de repli claire si aucune séance passée n'existe en base.
  4. **TDD strict :** 4/4 tests unitaires validés dans `tests/test_sport_temporal_resolution.py`.
  5. **Zéro régression :** 407/407 tests au vert sur l'ensemble du projet.
* **Statut :** 🟢 Terminé, prêt pour validation utilisateur.

---

### 🟢 Étape 5 : Ergonomie Vocale, Formulations Naturelles & Tolérances Linguistiques
* **Objectifs :**
  1. Supprimer le texte hardcodé « Pour aujourd'hui... » de `sport_handler.py` lors de la consultation d'une séance à une autre date ou de la dernière séance.
  2. Implémenter un formateur oral de dates naturelles (`format_natural_spoken_date(target_date)`) :
     - Exemples : « d'aujourd'hui », « d'hier », « de demain », « du dimanche 4 octobre ».
  3. Améliorer la flexibilité grammaticale :
     - Support de l'infinitif dans les requêtes vocales (« modifier ma séance », « changer le rpe », « planifier un footing »).
     - Déclinaisons de vocabulaire : « renfort », « renfo », « muscu », « musculation », « PPG », « gainage » mappés automatiquement vers `SportSessionType.RENFORCEMENT`.
* **Critères d'acceptation :**
  - Réponses vocales chaleureuses, fluides et exemptes d'incohérences de date.
  - Tests unitaires validés à 100% dans `tests/test_sport_voice_natural_dates.py`.

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
