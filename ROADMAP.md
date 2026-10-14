# Roadmap Feature : Phase 6.6 - Stabilisation, Corrections de Bugs & Évolution Sport / Chat Vocal (`feat/bugfix-phase6-6`)

> **Règles d'or (AGENTS.md) :**
> - Chaque étape doit être validée **manuellement et explicitement par l'utilisateur** avant de passer à la suivante.
> - La suite de tests automatisés (`pytest`) doit être à **100% au vert** à chaque étape (TDD strict : Rouge ➔ Vert ➔ Refactor).
> - Zéro commit prématuré sans test ni validation préalable.
> - À la fin de la feature, un **test d'intégration End-to-End (E2E)** doit valider le flux complet de bout en bout.
> - Déploiement en production et validation utilisateur.

---

## Vue d'ensemble des Étapes

| Étape | Description | Statut | Validation Utilisateur | Tests Automatisés |
| :--- | :--- | :---: | :---: | :---: |
| **Étape 1** | **Correcteur Temporel Universel :** Résolution unifiée des expressions relatives (*« hier »*, *« demain »*, *« dernier »*, *« ces 3 derniers jours »*) sans collision ni dérive calendaire | 🟢 Terminé | Validé par l'utilisateur | ✅ 8/8 tests dédiés (427/427 total) au vert |
| **Étape 2** | **Détection Thématique Contextuelle par Mots-Clés :** Routage sémantique précis par domaine (Sport, Renfo, Second Cerveau/Notes, Courses, Métadiscussion) pour éliminer les faux positifs croisés | ⏳ À faire | En attente | ⏳ TDD à créer |
| **Étape 3** | **Éditeur Manuel Séances de Sport & Suppression (PWA) :** Modal d'édition des champs bruts (distance, durée, D+, RPE, météo, FC, notes, type) et bouton de suppression de séance avec confirmation pour assainir le carnet | 🟢 Terminé | Validé par l'utilisateur | ✅ 4/4 tests dédiés (455/455 total) au vert |
| **Étape 3.1** | **Import Séances par Capture d'Écran (Gemini Vision) & Toasts UI :** Alternative universelle et gratuite à l'API Strava (Strava, Decathlon Coach, Montre CW500 M) + Système universel de toasts flottants (fin des échecs muets) | 🟢 Terminé | Validé par l'utilisateur | ✅ 10/10 tests dédiés (465/465 total) au vert |
| **Étape 4** | **Pipeline Vocal PWA (Envoi Audio, Push-to-Talk & Wake-Word « Otis ») :** Diagnostic/fix de l'envoi de messages vocaux le matin + stabilisation tactile du bouton Push-to-Talk + tolérances phonétiques et réveil in-app sur « Otis » | ⏳ À faire | En attente | ⏳ TDD à créer |
| **Étape 5** | **Correction Sauvegarde & Débriefing des Séances (Screens 2 & Nouveaux) :** Résolution de l'erreur *« ❌ Échec »*, suppression des doublons et fusion réelle de doublon | 🟢 Terminé | Validé par l'utilisateur | ✅ 5/5 tests dédiés (439/439 total) au vert |
| **Étape 5.1** | **Persistance Débriefing Rétroactif, Préservation Sélective & FC :** Résolution de l'écrasement à 0/None, support complet FC (moy/max), persistance brute garantie et affichage Charge RPE & Météo | 🟢 Terminé | Validé par l'utilisateur | ✅ 7/7 tests dédiés (446/446 total) au vert |
| **Étape 6** | **Mémoire Conversationnelle Multi-Tours (Gestion d'État / Screens 3 & 4) :** Fin du mode stateless, buffer d'historique de 20 messages avec horodatages et bouton de nouveau fil | 🟢 Terminé | Validé par l'utilisateur | ✅ 7/7 tests dédiés (434/434 total) au vert |
| **Étape 6.1** | **File d'Attente Hors-Ligne & Synchronisation PWA (Offline Outbox) :** Sauvegarde locale immédiate si réseau coupé, indicateur d'attente et envoi automatique dès reconnexion | ⏳ À faire | En attente | ⏳ TDD à créer |
| **Étape 6.2** | **Gestion Audio Focus & Ducking Casque (Running Mode) :** Atténuation du volume casque (musique/podcast) uniquement si Otis parle ou si l'utilisateur lui parle, et non en continu dès l'ouverture de l'application | ⏳ À faire | En attente | ⏳ Tests UI / Audio à créer |
| **Étape 7** | **Test d'Intégration End-to-End (E2E) & Recette Finale :** Validation complète du cycle stabilisé, non-régression, déploiement prod et recette utilisateur | ⏳ À faire | En attente | ⏳ TDD à créer |

---

## Détail des Étapes

### 🟢 Étape 1 : Correcteur Temporel Universel
* **Contexte & Problème résolu :**
  - Des requêtes contenant des termes temporels relatifs (*« hier »*, *« avant-hier »*, *« demain »*, *« après-demain »*, *« dimanche dernier »*, *« ces 3 derniers jours »*) subissaient des collisions ou n'étaient pas captées correctement.
* **Objectifs réalisés :**
  1. Centralisation dans `app/core/date_resolver.py` avec `TemporalRangeType` et `resolve_temporal_range` :
     - Résolution de fenêtres de jours (*« ces 3 derniers jours »* ➔ liste exacte des dates et bornes).
     - Résolution des semaines (*« cette semaine »*, *« la semaine dernière »*, *« la semaine prochaine »*).
  2. Support complet des expressions relatives passées et futures dans `resolve_date_expression` :
     - *« avant-hier »*, *« hier »*, *« après-demain »*, *« demain »*.
     - Jours relatifs avec *« dernier / dernière »* (*« dimanche dernier »*, *« lundi dernier »* résolu dans le passé de 1 à 7 jours).
  3. Distinction étanche entre période calendaire et décompte d'échanges conversationnels (*« ces 3 derniers échanges »* ne produit aucune date calendaire parasite).
  4. Intégration dans `IntentParser` : support complet des consultations de séances passées/futures (*« c'est quoi ma séance d'avant-hier ? »*).
* **Critères d'acceptation :**
  - 8/8 tests unitaires TDD validés dans `tests/test_universal_date_resolver.py`.
  - Non-régression totale : 427/427 tests passés au vert.

---

### ⏳ Étape 2 : Détection Thématique Contextuelle par Mots-Clés
* **Contexte & Problème (Screen 4) :**
  - En disant *« Ok prends note de ces 3 derniers échanges. Il faut corriger »*, l'assistant a compris à tort qu'il devait mettre à jour 3 séances de sport avec un RPE à 3/10 !
* **Objectifs à réaliser :**
  1. Renforcer le filtrage par mots-clés thématiques dominants :
     - Sport/Running : `couru`, `footing`, `fractionné`, `km`, `allure`, `séance de course`, etc.
     - Renforcement : `renfo`, `gainage`, `pompes`, `muscu`, `étirements`, `tibial`, etc.
     - Second Cerveau / Notes : `prends note`, `note que`, `rappelle-moi de`, `à noter`, `note de bug`, `idée`.
     - Métadiscussion : `ces derniers échanges`, `ce qu'on vient de dire`, `la conversation`.
  2. Priorisation stricte : une intention explicite de prise de note (*« prends note de... »*) ne doit **JAMAIS** déclencher une mutation sportive (CRUD sport).
* **Critères d'acceptation :**
  - 100% de tests unitaires sur les phrases pièges et phrases mixtes.

---

### 🟢 Étape 3 : Éditeur Manuel Complet des Séances de Sport & Suppression (PWA)
* **Contexte & Règle d'or de conception (Validation Alexis) :**
  - Si l'analyse vocale échoue ou si une séance a besoin d'ajustements fins, l'utilisateur doit pouvoir modifier les données brutes de la séance sans risquer d'altérer la logique métier.
  - **Distinction stricte Champs Bruts vs Champs Calculés :**
    - **Champs bruts modifiables (updatables) :**
      * `distance_km`, `duree_secondes` (minutes et secondes), `denivele_d_plus`.
      * `ressenti_rpe` (1 à 10), `meteo_note` (1 à 10).
      * `type_seance` (`EF`, `Fractionné`, `Sortie Longue`, `Renforcement`, `Course`, `Vitesse`, `Tempo`, `Récup`).
      * `programme`, `remarques`, `notes`, `fc_moyenne`, `fc_max`, `statut`.
    - **Champs calculés protégés (NON updatables manuellement car dérivés automatiquement) :**
      * `allure_moyenne` (dérivée de duree / distance).
      * `vitesse_moyenne` (dérivée de distance / duree).
      * `charge_rpe` (dérivée de RPE * (duree_secondes / 60)).
      * `km_effort` (dérivé de distance + D+ / 100).
      * Synthèses hebdomadaires et mensuelles (recalculées de façon déterministe par le moteur).
* **Réalisations :**
  1. **Endpoints API Backend (`routers/sport.py`, `sqlite/sport_connector.py`) :**
     - Endpoint `DELETE /api/v1/sport/session/{id}` avec suppression en base SQLite et recalcul automatique de la synthèse hebdomadaire rattachée.
     - Endpoint `PATCH /api/v1/sport/session/id/{id}` avec filtrage strict des `None` (non-écrasement sélectif), exclusion des champs calculés forcés et recalcul immédiat des indicateurs dérivés.
     - Champ `id` exposé dans le contrat Pydantic `SportSession`.
  2. **Interface PWA (`sport_view.js`, `index.html`, `api.js`) :**
     - Boutons d'action « ✏️ Modifier » et « 🗑️ Supprimer » sur chaque carte d'accordéon de l'historique et sur la carte du jour.
     - Confirmation explicite avant suppression pour éviter toute perte accidentelle.
     - Formulaire modal d'édition `#modal-edit-sport-session` ergonomique restreint aux champs bruts éligibles (distance, durée minutes/secondes, D+, RPE, météo, FC, remarques).
     - Actualisation réactive instantanée des vues et compteurs sans rechargement de page.
* **Critères d'acceptation validés :**
  - 4/4 tests TDD dédiés au vert dans `tests/test_sport_manual_editor_and_deletion.py`.
  - Non-régression totale : **455/455 tests passés à 100% au vert**.
  - Validé manuellement et testé avec succès par Alexis.

---

### 🟢 Étape 3.1 : Import Universel par Capture d'Écran (Gemini Vision) & Observabilité UI (Toasts)
* **Contexte & Décision d'Architecture :**
  1. **Abandon de l'API Strava Payante :** Strava ayant rendu payant l'accès développeur à son API (réservé aux abonnements Summit payants), Alexis et l'assistant ont validé une alternative **100% gratuite, universelle et sans friction** : l'ingestion multimodale par capture d'écran via **Gemini Vision**.
  2. **Support des 3 formats réels fournis par Alexis :**
     - **Format 1 (Strava) :** Distance, durée, allure au km, D+, date relative (*« Aujourd'hui à... »* / *« Il y a 2 jours »*).
     - **Format 2 (Decathlon Coach / Kiprun) :** Distance, durée (`31'23"`), D+, allure (`06'07"/km`), horodatage (`12/10/2026 - 12:55`).
     - **Format 3 (Decathlon Connect / Montre CW500 M) :** Distance, durée (`0:33:07`), FC moyenne (`163 bpm`), allure, cadence (`170`), date (`08 oct. 2026`).
  3. **Fin des échecs muets :** Remplacement de tous les `alert()` bloquants et des boutons rouges anonymes par un système universel de notifications flottantes (toasts) avec cause exacte renvoyée par le serveur.
* **Réalisations :**
  1. **Backend & IA Multimodale (`SportVisionService`, `sport.py`, `models.py`) :**
     - Schéma Pydantic strict `SportScreenshotAnalysisResult` (validation typée des durées en secondes, distances, allures, FC moy/max, dénivelé).
     - Service multimodal `SportVisionService` exploitant Gemini 2.5 Flash / Flash-Lite avec prompt calibré pour extraire instantanément les métriques clés de toute capture de course.
     - Endpoint `POST /api/v1/sport/import-screenshot` avec déduplication intelligente : met à jour la séance prévue existante en conservant son programme technique, ou crée une nouvelle séance au statut `Réalisé`.
     - Recalcul déterministe immédiat des indicateurs dérivés et des synthèses hebdomadaires.
  2. **Système Universel de Toasts & Observabilité UI (`toast.js`, `style.css`) :**
     - Module universel `showToast`, `showToastSuccess`, `showToastError`, `showToastWarning`, `showToastInfo` avec animations fluides et fermeture automatique.
     - Remplacement complet des `alert()` et des échecs muets dans les cartes de sport.
  3. **Expérience Utilisateur Mobile & Desktop (`sport_view.js`, `chat_view.js`, `index.html`) :**
     - Bouton **« 📸 Importer capture »** dans l'en-tête de l'onglet Running & Coach (avec input file acceptant galeries mobiles ou appareils photos natifs).
     - Support universel du collage direct (**Ctrl+V**) d'une capture d'écran sur l'onglet Sport ou dans le Chat.
     - Bouton photo direct dans la barre de message d'Otis : l'import dans le chat déclenche la réponse vocale immédiate du coach.
* **Critères d'acceptation validés :**
  - 10/10 tests TDD dédiés au vert dans `tests/test_sport_screenshot_vision_import.py` (couvrant les formats Strava, Decathlon Coach, montre CW500 M, dates avec heures, formats ISO, slash, tirets et abréviations de mois).
  - Non-régression totale : 465/465 tests passés à 100% au vert.
  - Validé avec succès par Alexis sur des captures réelles (Strava et Decathlon Coach) avec correction automatique de date et débrief vocal.

---

### ⏳ Étape 4 : Pipeline Vocal PWA (Envoi Audio, Bouton Push-to-Talk & Wake-Word « Otis »)
* **Contexte & Problèmes (Screen 1 & Retour Utilisateur) :**
  - Les messages vocaux ne partent pas certains matins.
  - Le bouton flottant Push-to-Talk se décale au toucher ou au scroll sur smartphone.
  - La reconnaissance continue du mot-clé de réveil in-app (*« Otis »*) ne se déclenche jamais sur mobile.
* **Objectifs à réaliser :**
  1. **Envoi Audio & Permissions :** Auditer le flux d'enregistrement et d'envoi audio dans `app/static/js/app.js` (MediaRecorder, gestion des permissions micro, formats MIME Safari/Chrome/Android, timeout réseau).
  2. **Stabilité Tactile & CSS du Bouton :** Fixer la position du bouton Push-to-Talk en CSS (`position: fixed`, désactivation du scroll rebond élastique sur le conteneur du bouton, gestion propre de `touch-action: none`).
  3. **Fiabilisation & Calibrage du Wake-Word In-App (« Otis ») :**
     - Module de calibrage in-app multi-situations (échantillonnage guidé de 5 à 10 prononciations dans des contextes réels : voix au calme, essoufflé en courant, voix rapide, voix forte).
     - Apprentissage automatique des retranscriptions du micro pour alimenter un dictionnaire local d'alias personnalisés propre à l'utilisateur.
     - Tolérances phonétiques françaises par défaut (*« autiste »*, *« notice »*, *« au tisse »*, *« hotis »*, *« dis otis »*).
     - Rendre le redémarrage de `SpeechRecognition` résilient (reconnexion automatique après silence ou mise en arrière-plan sans planter).
     - Témoin visuel clair (icône micro pulsante) confirmant l'écoute active du wake-word.
* **Critères d'acceptation :**
  - Bouton stable et immobile au toucher sur smartphone.
  - Envoi des blobs audio fluide sans échec silencieux.
  - Module de calibrage guidé disponible dans l'onglet réglages/profil.
  - Déclenchement fluide du réveil in-app, y compris avec une voix essoufflée en courant.

---

### ✅ Étape 5 : Correction Sauvegarde & Débriefing des Séances (Screens 2 & Nouveaux)
* **Contexte & Problèmes résolus :**
  1. **Échec de sauvegarde manuelle (Screen 2) :** L'endpoint `PATCH /api/v1/sport/session/{target_date}` appelait `update_session(..., update_data=payload)` qui levait un `TypeError: unexpected keyword argument 'update_data'` sur `SqlSportConnector`, causant une erreur 500 et le bouton rouge *« ❌ Échec. Réessayer »*.
  2. **Création d'un doublon lors d'un débriefing consécutif :** L'ordre « durée avant distance » (*« j'ai mis 45min et 30 sec pour faire 7km sur cette séance »*) et l'anaphore n'étaient pas reconnus, provoquant un log en doublon (*EF 7 km* à côté de la *Sortie Longue 7.5 km*).
  3. **Hallucination passive sur rétroaction corrective :** L'injonction *« tu as créé une séance plutôt que modifier la séance qui était prévue »* tombait en `unknown` sans mutation réelle en base.
* **Réalisations :**
  1. **Harmonisation et robustesse de l'API de debrief (`sport_connector.py`, `routers/sport.py`, `api.js`, `sport_view.js`) :**
     - `SqlSportConnector.update_session` accepte désormais indifféremment `updates` et `update_data` en keyword arguments.
     - Gestion d'erreur explicite avec status 400/404 contextualisés, messages d'erreur détaillés extraits côté PWA et logs complets.
  2. **Résolution anaphorique et protection anti-doublon (`intent_parser.py`, `sport_handler.py`, `sport_connector.py`) :**
     - Détection dans `IntentParser` des tournures durée-avant-distance (*« j'ai mis X min [et Y sec] pour faire Z km (sur cette séance) »*) et extraction précise des secondes.
     - Prise en compte de `contextual_session` et `last_sport_date` pour cibler la séance active sans créer de doublon.
     - Préservation du type de séance d'origine (ex: Sortie Longue) lors d'un débriefing rapide.
  3. **Action corrective réelle et fusion de doublon (`models.py`, `sport_handler.py`, `nlu_service.py`) :**
     - Nouvelle intention `FIX_SPORT_DUPLICATE` (`fix_sport_duplicate`) intégrée dans le parser local et le prompt NLU Gemini.
     - Action concrète en base SQLite : fusion des métriques (distance, durée, notes, RPE) sur la séance prévue/principale, suppression du doublon parasite via `delete_session` et recalcul de la synthèse hebdomadaire avec confirmation vocale explicite d'Otis.
* **Critères d'acceptation validés :**
  - 5/5 tests TDD dédiés au vert dans `tests/test_sport_debrief_and_duplicate_handling.py`.
  - Suite de régression globale à 100% au vert (**439/439 tests passés**).

---

### ✅ Étape 5.1 : Persistance Débriefing Rétroactif, Préservation Sélective & FC (Screens Débriefing)
* **Contexte & Problèmes résolus :**
  1. **Confusion entre consultation et réécriture rétroactive :**
     - Alexis disait : *« Finalement sur ma dernière séance de sport j'ai couru 5km avec un rpe a 4 et en 45min 30 »*.
     - Le système déclenchait une simple lecture passive (`GET_SPORT_SESSION`) de 7 km au lieu de mettre à jour la séance en base.
  2. **Incomplétude des champs bruts et écrasement partiel à 0/None :**
     - Lorsqu'Alexis précisait un champ ultérieur (*« ma fréquence max sur cette séance était a 156 et moyenne a 171 »*), le backend écrasait les métriques précédentes (`distance_km`, `duree_secondes`, `ressenti_rpe`) avec `None`, remettant la carte à zéro.
     - Les fréquences cardiaques (`fc_moyenne`, `fc_max`) n'étaient pas reconnues dans l'intention ni persistées en base.
  3. **Manque de visibilité de la Charge RPE et de la Météo dans l'UI :**
     - Les cartes de séances n'affichaient ni la Charge RPE calculée ni la note météo.
* **Réalisations :**
  1. **Routage intelligent des révisions d'ouverture & de la FC (`intent_parser.py`, `nlu_service.py`) :**
     - Détection des tournures de rectification combinées à une action de course pour cibler la dernière séance (`target_date="last"`).
     - Détection et extraction complète des fréquences cardiaques (`fc_max`, `fc_moyenne` et formats libres en bpm).
  2. **Débriefing des séances planifiées & transition de statut (`sport_handler.py`, `sport_connector.py`, `database.py`) :**
     - Résolution intelligente de « dernière séance » : recherche jusqu'à la date du jour (`max_date=date.today()`) incluant les séances au statut `Prévu` non encore débriefées.
     - Transition automatique : dès qu'une séance planifiée (`Prévu`) reçoit des métriques réelles d'effort (durée, distance, RPE, météo, FC), son statut bascule immédiatement à **`Réalisé`**, et sa charge RPE ainsi que sa vitesse/allure sont calculées.
  3. **Préservation sélective absolue & non-écrasement (`sport_connector.py`, `sport_handler.py`) :**
     - Filtrage strict des valeurs `None` dans `update_session` pour ne modifier QUE les champs explicitement spécifiés.
     - Prise en charge et persistance complète de `fc_moyenne` et `fc_max` dans SQLite.
     - Confirmation vocale détaillée d'Otis citant explicitement les métriques modifiées (distance, durée, RPE, météo, FC max, FC moyenne).
  4. **Affichage enrichi de la Charge RPE et de la Météo dans la PWA (`sport_view.js`) :**
     - Intégration de badges visibles dès l'en-tête de la séance (*« 🔥 RPE {charge} »*, *« ☀️ {meteo}/10 »*).
     - Boîtes dédiées dans la grille de métriques de la carte pour la Charge RPE et la Météo avec icônes dynamiques.
* **Critères d'acceptation validés :**
  - 8/8 tests TDD dédiés au vert dans `tests/test_sport_retroactive_debrief_and_persistence.py` et `tests/test_sport_selective_update_and_heart_rate.py`.
  - Non-régression totale : **451/451 tests au vert**.

---

### ✅ Étape 6 : Mémoire Conversationnelle Multi-Tours (Gestion d'État / Screens 3 & 4)
* **Contexte & Problème résolu (Screens 3 & 4) :**
  - Le chat était auparavant stateless avec désynchronisation des sessions entre texte et vocal (*« C'est l'application » ➔ « Tu parles de quelle application ? »*).
* **Réalisations :**
  1. **SessionManager résilient (`app/core/session_manager.py`) :**
     - Fenêtre glissante intelligente portée à **20 messages** (10 allers-retours complets Alexis + Otis).
     - **Horodatage contextuel précis** de chaque tour dans le prompt Gemini (`[À l'instant]`, `[Il y a 12 min]`, `[Il y a 2h]`) permettant à l'IA d'avoir une perception temporelle exacte.
     - TTL étendu à **24 heures** (session continue sur la journée sans coupure intempestive).
     - Restauration automatique depuis SQLite (`conversation_logs`) en cas de redémarrage serveur ou recyclage de worker.
  2. **Identité de session unifiée PWA, Persistance Visuelle & Contrôle utilisateur (`config.js`, `api.js`, `chat_view.js`, `index.html`) :**
     - Transmission systématique du `session_id` partagé dans `postInteract` (texte) ET `postInteractAudio` (vocal).
     - **Persistance locale du fil de discussion (20 messages) :** Sauvegarde automatique dans `localStorage` (`pah_chat_ui_history`) à chaque message émis ou reçu. Les allers-retours d'onglets (Chat ➔ Séance ➔ Chat) et les rechargements de page préservent désormais 100% du fil de discussion.
     - **Synchronisation & Restauration Serveur :** Endpoints dédiés `GET /api/v1/session/history` et `POST /api/v1/session/reset`. Si le cache local est vierge, réhydratation automatique depuis `SessionManager`.
     - **Bouton & Chip « ✨ Nouveau fil » :** Accessible d'un clic dans le header et au-dessus des messages pour repartir d'une page blanche à la demande d'Alexis (purge `localStorage` et reset serveur).
     - **Actualisation réactive des vues métier :** Événement custom `sport-data-updated` émis lors d'une modification par le chat pour rafraîchir instantanément la vue sport sans rechargement manuel.
  3. **Résolution des anaphores & prise de note contextuelle (`intent_parser.py`, `nlu_service.py`, `sport_handler.py`) :**
     - Prompt Gemini enrichi pour poursuivre naturellement le fil après une question d'Otis (*« C'est l'application »*).
     - Détection et capture de notes multi-tours (*« Prends note de ces 3 derniers échanges. Il faut corriger »*) synthétisant les échanges récents dans `second_brain_notes` (`bug_report` ou `dev_idea`).
     - Résolution de séances sportives contextuelles sans date explicite (*« Il fallait en modifier le rpe a 3 »*).
* **Critères d'acceptation validés :**
  - 8/8 tests dédiés passés à 100% au vert dans `tests/test_conversation_session_memory.py`.
  - Suite globale à 100% au vert (**450/450 tests**).

---

### ⏳ Étape 6.1 : File d'Attente Hors-Ligne & Synchronisation PWA (Offline Outbox)
* **Contexte & Problème :**
  - Si la connexion est coupée (perte 4G/5G, tunnel coupé ou redémarrage du serveur), l'envoi échoue et le message saisi ou dicté est perdu avec une simple erreur *« Impossible de joindre le serveur »*.
* **Objectifs à réaliser :**
  1. **File d'attente locale (Offline Outbox) :** Sauvegarde immédiate des messages échoués dans `localStorage` (`pah_offline_queue`) avec leur horodatage et leur `session_id`.
  2. **Feedback visuel dans le chat :** Affichage immédiat du message dans le flux avec un indicateur discret ⏳ *« En attente de réseau »* et bouton *« Réessayer »*.
  3. **Synchronisation automatique & manuelle :**
     - Détection du retour réseau (`window.addEventListener('online')` ou polling léger).
     - Dépilage séquentiel dans l'ordre chronologique sur la même session active.
     - Option de déclenchement manuel au clic.
* **Critères d'acceptation :**
  - Zéro perte de message en cas de coupure réseau ou serveur indisponible.
  - Envoi fluide dès reconnexion et réception de la réponse d'Otis.

---

### ⏳ Étape 6.2 : Gestion Audio Focus & Ducking Casque (Running Mode)
* **Contexte & Problème constaté en course à pied :**
  - À l'ouverture de l'application pendant une sortie running, le son du casque (musique, podcast) baisse automatiquement de manière continue (*audio ducking permanent*).
  - L'écoute du micro ou le contexte audio Web / SpeechRecognition force le système hôte (iOS/Android) en mode communication continue.
* **Comportement attendu :**
  - Le volume du casque ne doit baisser (**ducking**) **uniquement** si Otis est en train de parler (synthèse vocale TTS en cours de lecture) ou si l'utilisateur est en train de lui parler (Push-to-Talk actif).
  - Dès la fin de l'interaction (TTS terminé ou relâchement du Push-to-Talk), libérer le flux audio pour que la musique/le podcast reprenne son volume nominal à 100%.
* **Objectifs à réaliser :**
  1. Gestion dynamique du contexte audio (`AudioContext` / MediaStreams / SpeechRecognition) : n'activer l'écoute et la capture que sur appui Push-to-Talk ou détection de parole, et libérer les tracks micro au repos.
  2. Gestion des attributs AudioSession / Ducking pour ne pas monopoliser le canal audio du smartphone en continu en arrière-plan.
* **Critères d'acceptation :**
  - La musique/le podcast continue à son volume normal lorsque la PWA est simplement ouverte à l'écran.
  - Le son est atténué uniquement pendant que l'utilisateur parle ou qu'Otis répond, puis revient instantanément à la normale.

---

### ⏳ Étape 7 : Test d'Intégration End-to-End (E2E) & Recette Finale
* **Objectifs à réaliser :**
  1. Test E2E couvrant les scénarios critiques corrigés.
  2. Validation de la suite complète à 100% au vert.
  3. Déploiement en production et validation avec l'utilisateur sur mobile.
