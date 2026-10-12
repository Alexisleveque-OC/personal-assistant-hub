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
| **Étape 3** | **Éditeur Manuel Complet des Séances de Sport (PWA) :** Modal d'édition manuelle de chaque champ (distance, durée, D+, RPE, notes, remarques, type) pour modifier ses séances en toute autonomie | ⏳ À faire | En attente | ⏳ TDD à créer |
| **Étape 4** | **Pipeline Vocal PWA (Envoi Audio, Push-to-Talk & Wake-Word « Otis ») :** Diagnostic/fix de l'envoi de messages vocaux le matin + stabilisation tactile du bouton Push-to-Talk + tolérances phonétiques et réveil in-app sur « Otis » | ⏳ À faire | En attente | ⏳ TDD à créer |
| **Étape 5** | **Correction Sauvegarde & Débriefing des Séances (Screens 2 & Nouveaux) :** Résolution de l'erreur *« ❌ Échec. Réessayer »*, suppression des créations de doublons lors d'un debrief (*« sur cette séance »*), et correction automatique sur plainte utilisateur | ⏳ À faire | En attente | ⏳ TDD à créer |
| **Étape 6** | **Mémoire Conversationnelle Multi-Tours (Gestion d'État / Screens 3 & 4) :** Fin du mode stateless, buffer d'historique de 20 messages avec horodatages et bouton de nouveau fil | 🟢 Terminé | Validé par l'utilisateur | ✅ 7/7 tests dédiés (434/434 total) au vert |
| **Étape 6.1** | **File d'Attente Hors-Ligne & Synchronisation PWA (Offline Outbox) :** Sauvegarde locale immédiate si réseau coupé, indicateur d'attente et envoi automatique dès reconnexion | ⏳ À faire | En attente | ⏳ TDD à créer |
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

### ⏳ Étape 3 : Éditeur Manuel Complet des Séances de Sport (PWA)
* **Contexte & Problème :**
  - Si l'analyse vocale échoue ou si une séance a besoin d'ajustements fins, l'utilisateur ne peut pas modifier chaque champ individuellement à la main dans l'interface PWA.
* **Objectifs à réaliser :**
  1. Ajouter un bouton « Modifier » / icône crayon sur la carte de séance de la PWA.
  2. Ouvrir un formulaire modal d'édition complet permettant de modifier manuellement :
     - Type de séance (`EF`, `Fractionné`, `Sortie Longue`, `Renforcement`).
     - Distance ($km$), Allure / Durée (minutes/secondes), Dénivelé ($D+$).
     - Ressenti RPE ($1$ à $10$), Notes & Remarques.
  3. Endpoint backend `PATCH /api/v1/sport/sessions/{id}` avec validation Pydantic granulaire et recalcul automatique de la synthèse hebdomadaire.
* **Critères d'acceptation :**
  - Modification manuelle fonctionnelle au clic sur mobile et desktop, avec persistance SQLite immédiate.

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

### ⏳ Étape 5 : Correction Sauvegarde & Débriefing des Séances (Screens 2 & Nouveaux)
* **Contexte & Problèmes constatés :**
  1. **Échec de sauvegarde manuelle (Screen 2) :** Erreur *« ❌ Échec. Réessayer »* sur le bouton rouge lors de la saisie du debrief d'une séance dans l'UI.
  2. **Création d'un doublon au lieu de modifier la séance existante (Nouveaux Screens) :**
     - Après avoir consulté sa dernière séance (*Sortie Longue de 7.5 km du 10 oct.*) et modifié son RPE, Alexis enchaîne : *« super, j'ai mis 45min et 30 sec pour faire 7km sur cette séance »*.
     - Le système a interprété cela comme `LOG_SPORT_SESSION` au lieu de `UPDATE_SPORT_SESSION` ou validation de la séance existante, créant une deuxième séance distincte le même jour (*EF 7 km* en doublon de *Sortie Longue 7.5 km*).
  3. **Hallucination passive sur rétroaction corrective :**
     - Alexis signale : *« tu as créé une séance plutôt que modifier la séance qui était prévue »*.
     - Otis formule une promesse polie (*« Toutes mes excuses, Alexis. Je rectifie le tir et fusionne cela sur la bonne séance. »*) mais n'effectue AUCUNE action réelle dans la base de données (intention `unknown` sans mutation concrète).
* **Objectifs à réaliser :**
  1. **Débriefing contextuel d'une séance existante :**
     - Identifier les formulations de debriefing de séance en cours (*« sur cette séance »*, *« pour cette course »*, *« j'ai mis X min pour faire Y km »*) et les router vers la mise à jour / validation de la séance ciblée (`session_ctx["last_sport_date"]`) au lieu d'en insérer une nouvelle.
  2. **Gestion des doublons et intentions de fusion/correction :**
     - Reconnaître les plaintes de doublon ou de mauvaise création (*« tu as créé une séance plutôt que modifier... »*, *« fusionne avec la séance prévue »*, *« supprime le doublon »*) et exécuter la correction en base (fusion des données sur la séance prévue et suppression du doublon créé par erreur).
  3. **Robustesse de l'endpoint de debrief de la carte PWA :**
     - Sécuriser l'endpoint `PATCH /api/v1/sport/session/{dateStr}`, gérer les retours à la ligne, types numériques et fournir des messages d'erreur contextualisés.
* **Critères d'acceptation :**
  - Pas de création de doublon lorsqu'un debriefing oral fait référence à une séance existante ou prévue.
  - La remarque corrective d'Alexis fusionne et nettoie immédiatement le doublon en base sans promesse vide.
  - Sauvegarde de la carte de debriefing fluide sans bouton rouge d'erreur.

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
  2. **Identité de session unifiée PWA & Contrôle utilisateur (`config.js`, `api.js`, `chat_view.js`, `index.html`) :**
     - Transmission systématique du `session_id` partagé dans `postInteract` (texte) ET `postInteractAudio` (vocal).
     - **Bouton & Chip « ✨ Nouveau fil » :** Accessible d'un clic dans le header et au-dessus des messages pour repartir d'une page blanche à la demande d'Alexis (`resetActiveSessionId()`).
  3. **Résolution des anaphores & prise de note contextuelle (`intent_parser.py`, `nlu_service.py`, `sport_handler.py`) :**
     - Prompt Gemini enrichi pour poursuivre naturellement le fil après une question d'Otis (*« C'est l'application »*).
     - Détection et capture de notes multi-tours (*« Prends note de ces 3 derniers échanges. Il faut corriger »*) synthétisant les échanges récents dans `second_brain_notes` (`bug_report` ou `dev_idea`).
     - Résolution de séances sportives contextuelles sans date explicite (*« Il fallait en modifier le rpe a 3 »*).
* **Critères d'acceptation validés :**
  - 7/7 tests dédiés passés à 100% au vert dans `tests/test_conversation_session_memory.py`.
  - Suite globale à 100% au vert (434/434 tests).

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

### ⏳ Étape 7 : Test d'Intégration End-to-End (E2E) & Recette Finale
* **Objectifs à réaliser :**
  1. Test E2E couvrant les scénarios critiques corrigés.
  2. Validation de la suite complète à 100% au vert.
  3. Déploiement en production et validation avec l'utilisateur sur mobile.
