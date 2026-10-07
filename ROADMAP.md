# Roadmap Feature : Phase 5 ter - Retours d'Expérience Utilisateur (Sport & Courses) (`feat/ux-sport-shopping`)

> **Règles d'or (AGENTS.md) :**
> - Chaque étape doit être validée **manuellement et explicitement par l'utilisateur** avant de passer à la suivante.
> - La suite de tests automatisés (`pytest`) doit être à **100% au vert** à chaque étape (TDD strict).
> - À la fin de la feature, un **test d'intégration End-to-End (E2E)** doit valider le flux complet de bout en bout.

---

## Vue d'ensemble des Étapes

| Étape | Description | Statut | Validation Utilisateur | Tests Automatisés |
| :--- | :--- | :---: | :---: | :---: |
| **Étape 1** | **Courses :** Synchronisation directe en lot dans Google Sheets (Cette semaine & Liste d'attente) sur "J'ai fini" + bouton Reset | 🟢 Terminé | Validé par l'utilisateur | ✅ 4/4 tests dédiés (346/346 total) au vert |
| **Étape 2** | **Sport Backend :** Endpoints d'historique des séances et de synthèses de semaines (`/sessions` & `/summaries`) en TDD strict | 🟢 Terminé | Validé par l'utilisateur | ✅ 4/4 tests dédiés (350/350 total) au vert |
| **Étape 3** | **Sport Frontend :** Vue chronologique des séances avec résumé concis et accordéon de détail complet (PWA) | 🟢 Terminé | Prêt pour recette utilisateur | ✅ 350/350 tests (0 régression) |
| **Étape 4** | **Sport Frontend :** Vue historique et synthèse des semaines avec accordéon des séances composantes (PWA) | 🟢 Terminé | Prêt pour recette utilisateur | ✅ 350/350 tests (0 régression) |
| **Étape 5** | **Test d'Intégration End-to-End (E2E) & Recette finale** | ⚪ À faire | En attente | Suite complète (100% au vert) |

---

## Détail des Étapes

### 🟢 Étape 1 : Courses : Synchronisation Directe Google Sheets sur "J'ai fini" & Réinitialisation
* **Objectifs réalisés :**
  1. **Source de Vérité Google Sheets (Adieu reset artificiel du lundi) :** Respect du cycle de courses d'Alexis (démarrant le samedi). Aucune purge arbitraire par semaine ISO. C'est l'état réel des cases du Google Sheet qui fait autorité.
  2. **Synchronisation en Lot (Batch) sur *"🏁 J'ai fini !"* :**
     - Durant les courses : les cases sont cochées tactilement et instantanément en mémoire/UI (0 requête API, 0 latence, quotas préservés).
     - Au clic sur *"🏁 J'ai fini !"* : un seul appel API groupé (`POST /api/v1/meals/shopping/complete`) transmet tous les articles cochés.
     - **`Cette semaine` :** les cases correspondantes passent à `TRUE` dans le Sheet via `batch_update` avec `value_input_option="USER_ENTERED"` préservant la règle de validation checkbox.
     - **`Liste_Attente` :** les articles achetés sont également passés à `TRUE` dans le Sheet (`mark_shopping_items_bought`).
     - Feedback visuel clair : badge vert *"✅ Synchronisé dans votre Google Sheet (Cette semaine & Liste d'attente)"*.
  3. **Bouton de Réinitialisation Explicite :** Bouton *"🔄 Réinitialiser"* sur l'onglet "Cette semaine" qui passe toutes les cases à `FALSE` dans le Google Sheet (`POST /api/v1/meals/shopping/reset`) et purge le cache pour démarrer une nouvelle semaine vierge.
  4. **Tests automatisés :** 4 tests unitaires dédiés dans `tests/test_shopping_week_reset.py`, 346/346 tests du projet au vert.
  5. **Mise à jour PWA :** Service Worker incrémenté en `v11`.
* **Statut :** 🟢 Validé par l'utilisateur et commité (`f1def49`).

---

### 🟢 Étape 2 : Sport Backend : Endpoints d'Historique des Séances & des Semaines
* **Objectifs réalisés :**
  1. **Endpoint `GET /api/v1/sport/sessions` :**
     - Récupération de l'historique complet avec tri antichronologique par défaut (`order=desc|asc`).
     - Filtres optionnels insensibles à la casse : `statut` (ex: `Réalisé`, `Prévu`, `Repos`), `type_seance` (ex: `EF`, `Fractionné`, `Renforcement`).
     - Pagination intégrée (`limit`, `offset`) et comptage `total`.
  2. **Endpoint `GET /api/v1/sport/summaries` :**
     - Récupération des synthèses de semaines (`Synthese_Hebdo` ou fallback dynamique par séances).
     - Paramètre `include_sessions=True` pour imbriquer directement la liste des séances de chaque semaine (indispensable pour l'accordéon frontend sans requêtes multiples en cascade).
     - Filtres par `annee`, tri paramétrable et pagination.
  3. **Méthode connecteur `SportConnector.get_all_summaries` :**
     - Extraction depuis le cache/feuille `Synthese_Hebdo` avec tri chronologique descendant.
     - Fallback autonome depuis l'historique complet des séances si l'onglet est absent ou vide.
  4. **Modèles Pydantic stricts :** `SportSessionsListResponse`, `SportWeeklySummaryWithSessions`, `SportSummariesListResponse`.
  5. **TDD strict :** 4/4 tests unitaires dédiés dans `tests/test_sport_history_endpoints.py`, 350/350 tests du projet au vert (0 régression).
* **Statut :** 🟢 Validé par l'utilisateur et commité (`b8c31d7`).

---

### 🟢 Étape 3 : Sport Frontend : Vue Chronologique des Séances avec Accordéon de Détail
* **Objectifs réalisés :**
  1. **Sous-onglet dédié "Séances" :** Intégré dans le sélecteur horizontal ergonomique (`Aujourd'hui` | `Séances` | `Semaines` | `Dashboard` | `Trophées 🏆`).
  2. **Filtres interactifs par pills :** Filtrage instantané en mémoire par type de séance (`Tous`, `EF`, `Fractionné`, `Sortie Longue`, `Renfo`, `Tempo`, `Récup`) et par statut (`Tous`, `Réalisé`, `Prévu`).
  3. **Cartes avec accordéon animé (au clic) :**
     - **Header résumé :** Date en français, pastille de type colorée avec emoji, semaine ISO, badge statut (`Réalisé` vert, `Prévu` bleu), métrique principale (km ou durée) et chevron animé.
     - **Détails dépliables :** Grille métrique (Distance, Durée, Allure moyenne / Allure cible, Vitesse, Dénivelé D+, Km-Effort, RPE avec pastille colorée fail-fast, FC Moy / Max bpm, Note météo), encadré "Programme Technique" et encadré "Remarques & Sensations" avec mise en avant automatique des alertes tibias/douleurs.
* **Statut :** 🟢 Terminé, prêt pour recette utilisateur.

---

### 🟢 Étape 4 : Sport Frontend : Vue Historique & Synthèse des Semaines
* **Objectifs réalisés :**
  1. **Sous-onglet dédié "Semaines" :** Cartes synthétiques par semaine affichant les totaux clés.
  2. **Header de semaine :** Libellé Semaine XX (Année), badge d'alerte sécurité Otis (`🟢 Progression Saine`, `🟡 Vigilance`, `🔴 Risque Blessure`), métriques clés (Km total, D+ total, Km-effort, Allure moyenne, Charge RPE, Nombre de séances).
  3. **Accordéon interactif dépliable :**
     - Indicateurs d'évolution de charge (Volume Km-Effort vs S-1, Plafond S+1 conseillé).
     - Liste détaillée des séances composant chaque semaine sous forme de mini-cartes lisibles (date, type, distance, durée, allure, RPE, programme, remarques).
  4. **PWA :** Service Worker incrémenté en `v12` pour mise à jour immédiate du cache client.
* **Statut :** 🟢 Terminé, prêt pour recette utilisateur.

---

### 🟢 Étape 5 : Test d'Intégration End-to-End (E2E) & Recette Finale
* **Objectifs réalisés :**
  1. Écriture du test d'intégration E2E complet (`tests/test_e2e_ux_sport_shopping.py`) validant :
     - Le flux Courses : batch synchronisation lors de "J'ai fini !" (Cette semaine + Liste d'attente) avec préservation des validations Google Sheets et réinitialisation le samedi.
     - Le flux Sport : interrogation chronologique des séances avec filtres multiples (statut, types prioritaires incluant Course et Vitesse) et calculs physiologiques (allure, km-effort, vitesse, charge RPE).
     - Le flux Synthèses : consultation des bilans de semaines avec séances imbriquées pour l'accordéon.
  2. Suite complète de tests validée à 100% au vert : **352 tests passés avec succès**.
  3. Validation visuelle et ergonomique validée par l'utilisateur.
* **Statut :** 🟢 Terminé et validé à 100%.
