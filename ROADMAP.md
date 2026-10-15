# Roadmap - Gestion des Séances Sport & Résolution Date Import Screenshot

Cette roadmap détaille les étapes d'implémentation pour répondre aux besoins remontés dans les notes de production :
- **Note #3** : Résolution de la date sur l'import de screener Decathlon (importé à la date du jour au lieu de la bonne date).
- **Note #4** : Création manuelle de séances et modification de la date d'une séance existante.
- **Log #31** : Correction du bug vocal de logging de séance sans distance (ex: Fractionné qualifié à tort en renforcement musculaire).

---

## Étapes d'Implémentation

### [x] État Initial & Diagnostic
- [x] Rapatriement de la base de production (`hub_data.db`) via `pull_prod_db.py`.
- [x] Analyse des tables `second_brain_notes`, `sport_sessions` et `conversation_logs`.
- [x] Identification des causes racines (résolution temporelle des captures, prompts Gemini Vision, fallback sans distance en renfo, absence de champ date dans la modale d'édition et absence de bouton de création manuelle).
- [x] Baseline de tests validée : 508 tests passés à 100% au vert.
- [x] Création de la branche dédiée `feat/sport-session-management-and-screenshot-fix`.

---

### [x] Étape 1 : Résolution Temporelle Robuste des Captures d'Écran (Decathlon Coach & Connect)
*Objectif : Garantir que toute capture sportive (Decathlon Coach, CW500 M, Strava) extrait la date exacte et résout correctement les dates relatives passées.*
- [x] **Phase Rouge (TDD)** : Tests unitaires dans `tests/test_date_resolver.py` et `tests/test_sport_screenshot_vision_import.py` :
  - Résolution des noms de jours sans qualificatif ("mercredi", "mardi 13", "mercredi 14") vers le **passé** (les séances enregistrées sont par définition passées ou du jour, jamais futures).
  - Support des formats jour/mois sans année (`14/10`, `14/10/26`, `14 oct.`, `14 octobre à 18h`).
  - Tolérance aux variations Decathlon Coach (titre, date sous le tracé GPS, heure relative).
  - Guidage strict du prompt Gemini Vision (`SportVisionService`) pour interdire le repli aveugle sur la date du jour et cibler précisément l'en-tête Decathlon.
- [x] **Phase Verte** : Implémentation dans `app/core/date_resolver.py` (`parse_screenshot_date`), `app/core/vision/sport_vision_service.py` et `app/routers/sport.py`.
- [x] **Phase Refactor** : Nettoyage et typage strict.
- [x] **Validation Pas-à-Pas** : Exécution de `pytest tests/test_date_resolver.py tests/test_sport_screenshot_vision_import.py` (100% vert - 23 tests).

---

### [x] Étape 2 : Correction du Bug Vocal de Logging Sans Distance
*Objectif : Lorsqu'Alexis dit "J'ai fait une séance de fractionné", l'assistant doit enregistrer et annoncer une séance de Fractionné, pas de renforcement musculaire.*
- [x] **Phase Rouge (TDD)** : Tests dans `tests/test_sport_intent.py` vérifiant :
  - "J'ai fait une séance de fractionné" -> Enregistrement de type `FRACTIONNE` et formulation vocale "Votre séance de Fractionné de 30 minutes a bien été ajoutée au carnet."
  - Ne pas écraser la distance d'une séance existante si `distance_km` est `None`.
- [x] **Phase Verte** : Correction de la condition dans `app/handlers/sport_handler.py` (`elif type_seance == SportSessionType.RENFORCEMENT or dist is None:` -> distinguer strictement le type de séance).
- [x] **Phase Refactor** : Typage et robustesse.
- [x] **Validation Pas-à-Pas** : Exécution de `pytest tests/test_sport_intent.py` (100% vert - 18 tests).

---

### [x] Étape 3 : Backend - Modification de Date & Création Manuelle de Séance
*Objectif : Permettre la mise à jour de la date d'une séance (avec recalcul de semaine et actualisation des synthèses) et la création manuelle directe d'une séance.*
- [x] **Phase Rouge (TDD)** : Tests dans `tests/test_sport_api_and_strava.py` :
  - `patch_sport_session_by_id` avec modification de date : recalcul de `semaine` et mise à jour des synthèses hebdomadaires de l'ancienne et de la nouvelle semaine.
  - Endpoint `POST /api/v1/sport/session` pour créer manuellement une séance (type, date, statut, distance, durée, RPE, etc.).
- [x] **Phase Verte** : Implémentation dans `app/connectors/sqlite/sport_connector.py` et `app/routers/sport.py`.
- [x] **Phase Refactor** : Validation Pydantic stricte via `SportSessionCreate` (champs `statut` et `duree_secondes` optionnelle).
- [x] **Validation Pas-à-Pas** : Exécution de la suite de tests sport (100% vert - 15 tests).

---

### [x] Étape 4 : Frontend PWA - Sélecteur de Date dans la Modale & Bouton "+ Nouvelle séance"
*Objectif : Interface utilisateur intuitive permettant de corriger la date d'une séance et d'en créer une nouvelle directement depuis la vue Sport.*
- [x] Ajout d'un `<input type="date">` éditable dans `#modal-edit-sport-session` (remplaçant le badge figé).
- [x] Ajout du bouton d'action `+ Nouvelle séance` dans l'en-tête de la vue Sport (`app/static/index.html`).
- [x] Ajout du modal de création `#modal-create-sport-session` avec sélecteur de date, type, statut, distance, durée, RPE, programme.
- [x] Câblage JavaScript dans `app/static/js/views/sport_view.js` et `app/static/js/api.js`.
- [x] Validation manuelle et incrémentation de cache d'assets (`v=14.0`).

---

### [x] Étape 5 : Test d'Intégration Global (E2E) & Validation Finale
*Objectif : Valider le flux de bout en bout.*
- [x] Test d'intégration de bout en bout (`tests/test_e2e_sport_session_management.py`).
- [x] Exécution complète de `pytest` (521 tests au vert).

