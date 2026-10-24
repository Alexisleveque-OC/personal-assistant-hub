# Roadmap - Fiabilisation de l'Import de Captures Sportives (Gemini Vision)

Cette roadmap corrige les imports de captures (Decathlon Coach, Strava, CW500 M) enregistrés à la mauvaise date ou en échec silencieux :
1. **Date inventée / date du jour par défaut** : le schéma Gemini force une date non-nullable alors que le prompt demande `null` si invisible, et la route retombe silencieusement sur `date.today()` quand aucune date n'est extraite.
2. **Échecs masqués** : si tous les modèles Gemini échouent (quota, 404, timeout) ou si la clé est absente, le service renvoie un faux rejet « image non sportive » au lieu d'une erreur technique explicite.
3. **Blocage du serveur** : appel HTTP synchrone (`httpx.Client`) dans une route async, jusqu'à 7 modèles × 25 s.
5. **FC à 0 → erreur 500** : FC absente renvoyée à `0` par Gemini, écrite en base puis rejetée à la relecture (`fc >= 30`).
4. **Doublons Decathlon Connect (CW500 M)** : distance/durée de la montre non fiables (ex: 4,9 km vs 5,12 km Coach) → l'écart > 0,2 km créait une seconde séance au lieu de compléter la FC.

---

## Étapes d'Implémentation

### [x] Étape 1 : Fiabilisation Backend (TDD)
- [x] Rendre `date`, `distance_km`, `duree_secondes` **nullables** dans `GEMINI_SPORT_VISION_SCHEMA` (toujours `required` : le modèle doit statuer, mais peut répondre `null` au lieu d'inventer).
- [x] Fail-fast : lever `VisionServiceUnavailableError` (clé absente ou tous les modèles en échec, avec la liste des modèles tentés et la dernière erreur) au lieu du faux rejet `_fallback_analysis`. La route répond **503** avec ce détail.
- [x] Ne plus jamais retomber sur la date du jour : sans date extraite ni `reference_date` explicite, la route répond **400** en demandant la date, sans rien enregistrer.
- [x] Passer l'appel Gemini en `httpx.AsyncClient` (`analyze_screenshot` async).
- [x] Decathlon Connect (CW500 M) : si une séance réalisée existe à la date, ne fusionner **que la FC** (moyenne/max) ; rejet explicite si aucune FC lisible. Séance seulement prévue → passage en Réalisé avec **durée + FC** (distance montre ignorée). Import complet uniquement si aucune séance n'existe ce jour-là.
- [x] FC absente renvoyée à `0` par Gemini : `fc_moyenne`/`fc_max` nullables dans le schéma et `0` traité comme « non mesurée » (évitait l'écrasement d'une FC existante et une erreur 500 à la relecture, validation Pydantic `>= 30`).
- [x] Couvrir les libellés Strava relatifs réels (« Aujourd'hui à 12:56 · La Rochelle », « Hier à 12:56 »).

### [x] Étape 2 : Frontend - Saisie de la Date Manquante
- [x] Code d'erreur stable `X-Error-Code: screenshot_date_missing` sur les refus pour date manquante (pas de détection par texte côté front).
- [x] Module `static/js/screenshot_import.js` partagé (Chat + vue Sport) : modale de choix de date (aujourd'hui par défaut, futur interdit) puis renvoi de la capture avec `reference_date`. Annulation explicite sans erreur.
- [x] Afficher explicitement la date retenue dans la confirmation d'import (ex: « Séance Strava du lundi 12 octobre importée ») sur les 3 chemins (import complet, FC CW500, séance prévue CW500).
- [x] Cache PWA `pah-pwa-cache-v21` + précache du nouveau module.
- Limite connue : le renvoi relance une analyse Gemini (cas rare, ~3 s et un appel de quota en plus).

### [x] Étape 3 : Validation Réelle & Test E2E
- [x] Validation sur captures réelles via Gemini Vision (Decathlon Coach, Strava, CW500 M, capture Strava recadrée sans date) - captures non commitées.
- [x] Test d'intégration E2E `tests/test_e2e_screenshot_import.py` (date manquante → saisie → Coach → CW500 → panne Gemini, sur une seule séance).
- [x] Suite complète `pytest -v` à 100 % verte (546 tests).
- [ ] Test manuel utilisateur en production (PWA mobile).

---

## Hors Périmètre (à traiter séparément)
- **Fuseau horaire serveur** : aucun `TZ` n'est configuré dans le conteneur (Cloud Run = UTC). Entre 00h et 02h (heure de Paris), `date.today()` renvoie la veille pour toute l'application (repas, sport, « Aujourd'hui » des captures).
