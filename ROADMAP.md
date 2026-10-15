# Roadmap - Résolution Date Capture Decathlon, Protection Écrasement & Échelle Météo

Cette roadmap détaille les étapes d'implémentation pour résoudre les anomalies remontées lors du dernier import :
1. **Extraction de date sur capture Decathlon Coach** : La date sous le titre (`12/10/2026 - 12:55`) n'a pas été extraite par Gemini Vision, conduisant à un fallback arbitraire sur la date du jour.
2. **Protection contre l'écrasement de données réelles** : Le système a écrasé la séance existante réalisée du 15/10 au lieu d'empêcher la perte de données.
3. **Alignement des logos météo** : La météo est une échelle de **difficulté météo** (1 = Idéale/Grand soleil ☀️ à 10 = Tempête/Déluge/Canicule ⛈️), alors que l'interface affichait l'inverse.
4. **Correction des données en base** : Création propre de la séance du 12/10/2026 et restauration de la séance du 15/10/2026.

---

## Étapes d'Implémentation

### [x] Étape 1 : Amélioration de l'Extraction de Date Gemini Vision (Decathlon Coach)
- [x] Écrire un test unitaire dans `tests/test_sport_screenshot_vision_import.py` vérifiant que l'en-tête Decathlon Coach `JJ/MM/AAAA - HH:MM` (ex: `12/10/2026 - 12:55`) extrait fidèlement la date `2026-10-12`.
- [x] Renforcer le prompt dans `SportVisionService` (`app/core/vision/sport_vision_service.py`) avec l'emplacement exact de la date sous `COURSE À PIED` et l'obligation stricte d'extraire la date calendaire.
- [x] Validation TDD pas-à-pas (100% vert).

---

### [x] Étape 2 : Garde-fou Anti-Écrasement lors de l'Import de Capture (`app/routers/sport.py`)
- [x] Écrire des tests dans `tests/test_sport_screenshot_vision_import.py` :
  - Si aucune date n'est détectée dans la capture et aucune date de référence n'est fournie, ne pas deviner silencieusement ni écraser : renvoyer une erreur explicite.
  - Si une séance existe déjà avec `statut == 'Réalisé'`, ne pas écraser silencieusement ses données existantes (distance, remarques). Mettre à jour uniquement les séances au statut `Prévu` (planifiées) ou créer une nouvelle entrée si plusieurs séances ont lieu le même jour.
- [x] Implémenter les garde-fous dans l'endpoint `POST /api/v1/sport/import-screenshot`.
- [x] Validation TDD pas-à-pas (100% vert).

---

### [x] Étape 3 : Correction de l'Échelle de Difficulté Météo & Icônes Frontend
- [x] Mettre à jour `getMeteoBadge(note)` dans `app/static/js/views/sport_view.js` :
  - 1-2 : ☀️ Idéale (Grand soleil, conditions parfaites)
  - 3-4 : 🌤️ Bonne (Légèrement voilé / petit vent)
  - 5-6 : 🌦️ Mitigée (Pluie fine / vent sensible)
  - 7-8 : 🌧️ Difficile (Pluie battante / froid vif / vent fort)
  - 9-10 : ⛈️ Extrême (Tempête / canicule / déluge)
- [x] Mettre à jour les labels des formulaires (modales d'édition et de création) dans `app/static/index.html` :
  - `Difficulté Météo (1=Idéale ☀️, 10=Tempête ⛈️)`
- [x] Ajouter le champ Météo dans `#modal-create-sport-session` et câblage dans `sport_view.js`.
- [x] Incrémentation du cache d'assets (`v=15.0`).

---

### [x] Étape 4 : Restauration et Régularisation des Données en Base
- [x] Créer la séance du **12/10/2026** issue du screenshot (5.12 km, 31 min 23 s, D+ 31m, allure 06:07, 9.79 km/h, Decathlon Coach).
- [x] Vérifier la séance du **15/10/2026** avec ses métriques et remarques intègres (6.01 km, 2132s, RPE 4, Météo 2).
- [x] Recalculer les synthèses hebdomadaires des semaines 41 et 42.

---

### [x] Étape 5 : Tests de Non-Régression & Validation E2E
- [x] Exécuter la suite de tests complète (`pytest -v`) : **524 tests passés à 100% au vert**.
- [x] Validation par l'utilisateur avant commits et déploiement.
