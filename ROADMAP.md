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
| **Étape 2** | **Sport Backend :** Endpoints d'historique des séances et de synthèses de semaines (`/sessions` & `/summaries`) en TDD strict | 🟡 En cours | En attente | En cours de rédaction des tests |
| **Étape 3** | **Sport Frontend :** Vue chronologique des séances avec résumé concis et accordéon de détail complet (PWA) | ⚪ À faire | En attente | Tests d'affichage & composants |
| **Étape 4** | **Sport Frontend :** Vue historique et synthèse des semaines avec accordéon des séances composantes (PWA) | ⚪ À faire | En attente | Tests d'affichage & agrégations |
| **Étape 5** | **Test d'Intégration End-to-End (E2E) & Recette finale** | ⚪ À faire | En attente | Suite complète (100% au vert) |

---

## Détail des Étapes

### 🟢 Étape 1 : Courses : Synchronisation Directe Google Sheets sur "J'ai fini" & Réinitialisation
* **Objectifs réalisés :**
  1. **Source de Vérité Google Sheets (Adieu reset artificiel du lundi) :** Respect du cycle de courses d'Alexis (démarrant le samedi). Aucune purge arbitraire par semaine ISO. C'est l'état réel des cases du Google Sheet qui fait autorité.
  2. **Synchronisation en Lot (Batch) sur *"🏁 J'ai fini !"* :**
     - Durant les courses : les cases sont cochées tactilement et instantanément en mémoire/UI (0 requête API, 0 latence, quotas préservés).
     - Au clic sur *"🏁 J'ai fini !"* : un seul appel API groupé (`POST /api/v1/meals/shopping/complete`) transmet tous les articles cochés.
     - **`Cette semaine` :** les cases correspondantes passent à `TRUE` dans le Sheet via `batch_update`.
     - **`Liste_Attente` :** les articles achetés sont également passés à `TRUE` dans le Sheet (`mark_shopping_items_bought`).
     - Feedback visuel clair : badge vert *"✅ Synchronisé dans votre Google Sheet (Cette semaine & Liste d'attente)"*.
  3. **Bouton de Réinitialisation Explicite :** Bouton *"🔄 Réinitialiser"* sur l'onglet "Cette semaine" qui passe toutes les cases à `FALSE` dans le Google Sheet (`POST /api/v1/meals/shopping/reset`) et purge le cache pour démarrer une nouvelle semaine vierge.
  4. **Tests automatisés :** 4 tests unitaires dédiés dans `tests/test_shopping_week_reset.py`, 346/346 tests du projet au vert.
  5. **Mise à jour PWA :** Service Worker incrémenté en `v11`.
* **Statut :** 🟢 Validé techniquement, prêt pour confirmation utilisateur.

---

### ⚪ Étape 2 : Sport Backend : Endpoints d'Historique des Séances & des Semaines
* **Objectifs :**
  1. Endpoint `GET /api/v1/sport/sessions` : liste chronologique des séances (passées et prévues) avec tri antéchronologique par défaut (ou paramétrable), filtres optionnels par statut (`Réalisé`, `Prévu`, `Repos`), type de séance et plage de dates.
  2. Endpoint `GET /api/v1/sport/summaries` : liste de toutes les synthèses hebdomadaires (`SportWeeklySummary`) ordonnées par semaine (avec volume km, D+, allure moy, charge RPE cumulée, alerte sécurité).
  3. Association / imbrication optionnelle des séances de chaque semaine pour permettre un affichage fluide en accordéon.
  4. TDD strict avec mocks et validation de contrat Pydantic.
* **Statut :** En attente de l'Étape 1.

---

### ⚪ Étape 3 : Sport Frontend : Vue Chronologique des Séances avec Accordéon de Détail
* **Objectifs :**
  1. Nouveau sous-onglet ou section dédiée dans l'onglet Sport : "Historique des Séances".
  2. Cartes de séances élégantes avec statut, date, type (badge de couleur), distance/durée et allure ou programme.
  3. Dépliage au clic (accordéon CSS/JS fluide) affichant la vue détaillée complète : distance, durée, allure, dénivelé D+, Km-Effort, ressenti RPE, FC moyenne/max, météo, programme et remarques/périostite.
* **Statut :** En attente de l'Étape 2.

---

### ⚪ Étape 4 : Sport Frontend : Vue Historique & Synthèse des Semaines
* **Objectifs :**
  1. Vue sous-onglet ou section : "Historique des Semaines".
  2. Cartes synthétiques par semaine affichant les totaux clés (volume total, D+, allure moyenne, charge RPE cumulée, badge d'alerte sécurité).
  3. Accordéon interactif pour déplier la liste détaillée des séances ayant composé cette semaine.
* **Statut :** En attente de l'Étape 3.

---

### ⚪ Étape 5 : Test d'Intégration End-to-End (E2E) & Recette Finale
* **Objectifs :**
  1. Écriture d'un test d'intégration E2E automatisé validant le cycle complet : réinitialisation des courses d'une semaine sur l'autre, consultation de l'historique des séances passées/futures, consultation des synthèses hebdomadaires et dépliage des détails.
  2. Vérification de non-régression sur les 342+ tests existants (100% au vert).
  3. Invitation à la recette manuelle sur smartphone/PWA et validation finale par l'utilisateur.
* **Statut :** En attente.
