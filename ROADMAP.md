# Roadmap Feature : Audio Focus Casque, Pipeline Vocal & Stabilisation Avancée (`feat/audio-focus-and-voice-pipeline`)

> **Règles d'or (AGENTS.md) :**
> - Chaque étape doit être validée **manuellement et explicitement par l'utilisateur** avant de passer à la suivante.
> - La suite de tests automatisés (`pytest`) doit être à **100% au vert** à chaque étape (TDD strict : Rouge ➔ Vert ➔ Refactor).
> - Zéro commit prématuré sans test ni validation préalable.
> - À la fin de la feature, un **test d'intégration End-to-End (E2E)** valide le flux complet.
> - Déploiement en production et validation utilisateur.

---

## Vue d'ensemble des Étapes

| Étape | Description | Statut | Validation Utilisateur | Tests Automatisés |
| :--- | :--- | :---: | :---: | :---: |
| **Étape 1** | **Gestion Audio Focus & Ducking Casque (Running Mode) :** Atténuation du volume casque (musique/podcast) uniquement si Otis parle ou si l'utilisateur lui parle, et non en continu dès l'ouverture de l'application | ✅ Fait | Validé par Alexis | ✅ 100% vert (469 tests) |
| **Étape 2** | **Pipeline Vocal PWA (Envoi Audio, Push-to-Talk & Wake-Word « Otis ») :** Diagnostic/fix de l'envoi de messages vocaux le matin + stabilisation tactile du bouton Push-to-Talk + calibrage in-app du mot-clé de réveil « Otis » | ✅ Fait | Validé par Alexis | ✅ 100% vert (478 tests) |
| **Étape 3** | **Détection Thématique Contextuelle par Mots-Clés :** Routage sémantique précis par domaine (Sport, Renfo, Second Cerveau/Notes, Courses, Métadiscussion) pour éliminer les faux positifs croisés | ✅ Fait | Validé par Alexis | ✅ 100% vert (493 tests) |
| **Étape 4** | **File d'Attente Hors-Ligne & Synchronisation PWA (Offline Outbox) :** Sauvegarde locale immédiate si réseau coupé en forêt, indicateur d'attente et envoi automatique dès reconnexion | ✅ Fait | Validé par Alexis | ✅ 100% vert (507 tests) |
| **Étape 5** | **Test d'Intégration End-to-End (E2E) & Recette Finale :** Validation complète du cycle stabilisé, non-régression, déploiement prod et recette utilisateur | 🟡 En cours | En cours | ⏳ TDD en cours |

---

## Détail des Étapes

### ⏳ Étape 1 : Gestion Audio Focus & Ducking Casque (Running Mode)
* **Contexte & Problème soulevé par Alexis :**
  - Lors d'une course, ouvrir l'application baissait automatiquement et en continu le son du casque (musique / podcasts).
  - Le son ne doit être atténué (*ducking*) **QUE** si Otis prend la parole ou pendant que l'utilisateur lui dicte un message vocal.
* **Objectifs à réaliser :**
  1. **Gestion fine des flux audio du navigateur :**
     - Libérer immédiatement l'AudioContext / flux micro tant qu'aucune interaction n'est active.
     - Ne pas réserver le canal microphone de façon permanente en arrière-plan sans réveil.
  2. **Ducking Dynamique (Atténuation / Restauration) :**
     - Câbler l'Audio Focus sur les événements précis du cycle vocal :
       * Début TTS (`speechSynthesis.speak` / lecture audio) ➔ Déclenchement de l'atténuation.
       * Fin TTS (`onend` / arrêt du son) ➔ Restauration immédiate du volume nominal.
       * Appui Push-to-Talk / début enregistrement ➔ Atténuation du son pour capturer la voix clairement.
       * Relâchement / envoi ➔ Restauration du volume dès la fin de prise de parole.
  3. **Mode Écoute Wake-Word Non-Intrusif :**
     - S'assurer que la détection du wake-word (« Otis ») utilise un flux audio basse priorité (sans forcer le mode communication téléphone complet qui étouffe le son multimédia du smartphone).
* **Critères d'acceptation :**
  - Ouvrir l'application ou naviguer dans les onglets ne coupe ni ne baisse la musique du casque.
  - La musique s'atténue de façon transparente quand Otis parle ou pendant la dictée, puis revient instantanément à 100% dès la fin.

---

### ✅ Étape 2 : Pipeline Vocal PWA (Envoi Audio, Bouton Push-to-Talk & Wake-Word « Otis »)
* **Contexte & Problèmes soulevés :**
  - Les messages vocaux ne partent pas certains matins.
  - Le bouton flottant Push-to-Talk se décale au toucher ou au scroll sur smartphone.
  - La reconnaissance continue in-app du mot-clé « Otis » ne se déclenche jamais sur mobile.
* **Objectifs à réaliser :**
  1. **Envoi Audio & Permissions :** Auditer le flux d'enregistrement et d'envoi audio dans `app/static/js/app.js` (MediaRecorder, gestion des formats audio Safari/Android, gestion robuste des timeouts).
  2. **Stabilité Tactile & CSS du Bouton :** Fixer la position du bouton Push-to-Talk en CSS (`position: fixed`, désactivation du scroll élastique sous le bouton, gestion propre de `touch-action: none`).
  3. **Fiabilisation & Calibrage du Wake-Word In-App (« Otis ») :**
     - Module de calibrage in-app multi-situations (échantillonnage guidé de prononciations réelles : voix au calme, essoufflé en courant, voix forte).
     - Tolérances phonétiques françaises par défaut (*« autiste »*, *« notice »*, *« au tisse »*, *« hotis »*, *« dis otis »*).
     - Rendre le redémarrage de `SpeechRecognition` résilient (reconnexion automatique après silence ou mise en arrière-plan).
     - Témoin visuel clair (icône micro pulsante) confirmant l'écoute active du wake-word.
* **Critères d'acceptation :**
  - Bouton stable et immobile au toucher sur smartphone.
  - Envoi des messages audio fluide sans échec silencieux.
  - Module de calibrage guidé disponible dans l'interface.
  - Déclenchement fluide du réveil in-app, y compris avec une voix essoufflée en courant.

---

### ✅ Étape 3 : Détection Thématique Contextuelle par Mots-Clés
* **Contexte & Problème résolu :**
  - En disant *« Ok prends note de ces 3 derniers échanges. Il faut corriger »*, l'assistant comprenait à tort qu'il devait mettre à jour 3 séances de sport avec un RPE à 3/10 !
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

### ⏳ Étape 4 : File d'Attente Hors-Ligne & Synchronisation PWA (Offline Outbox)
* **Contexte & Problème :**
  - En plein footing en forêt ou en zone blanche, la perte de 4G provoque un échec réseau si on tente de logger une séance ou d'enregistrer une note.
* **Objectifs à réaliser :**
  1. File d'attente locale (IndexedDB / LocalStorage) pour stocker les requêtes en attente.
  2. Témoin visuel d'attente discret dans la PWA (*« ⏳ En attente de connexion »*).
  3. Envoi et synchronisation automatique dès le retour du réseau (événement `online`).
* **Critères d'acceptation :**
  - Aucune perte de données en cas de coupure réseau.
  - Notification toast de confirmation dès la reconnexion réussie.

---

### ⏳ Étape 5 : Test d'Intégration End-to-End (E2E) & Recette Finale
* **Objectifs à réaliser :**
  1. Écriture d'un test d'intégration E2E complet simulant le cycle de vie utilisateur :
     - Import d'une séance (capture ou vocal) ➔ Recalcul ➔ Débriefing oral ➔ Prise de note sans collision.
  2. Validation de l'absence de régression sur l'ensemble des 465+ tests.
  3. Déploiement en production et validation par Alexis.
