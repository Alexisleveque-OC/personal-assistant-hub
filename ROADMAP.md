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
| **Étape 1** | **Correcteur Temporel Universel :** Résolution unifiée des expressions relatives (*« hier »*, *« demain »*, *« dernier »*, *« ces 3 derniers jours »*) sans collision ni dérive calendaire | ⏳ À faire | En attente | ⏳ TDD à créer |
| **Étape 2** | **Détection Thématique Contextuelle par Mots-Clés :** Routage sémantique précis par domaine (Sport, Renfo, Second Cerveau/Notes, Courses, Métadiscussion) pour éliminer les faux positifs croisés | ⏳ À faire | En attente | ⏳ TDD à créer |
| **Étape 3** | **Éditeur Manuel Complet des Séances de Sport (PWA) :** Modal d'édition manuelle de chaque champ (distance, durée, D+, RPE, notes, remarques, type) pour modifier ses séances en toute autonomie | ⏳ À faire | En attente | ⏳ TDD à créer |
| **Étape 4** | **Pipeline Vocal PWA (Envoi Audio, Push-to-Talk & Wake-Word « Otis ») :** Diagnostic/fix de l'envoi de messages vocaux le matin + stabilisation tactile du bouton Push-to-Talk + tolérances phonétiques et réveil in-app sur « Otis » | ⏳ À faire | En attente | ⏳ TDD à créer |
| **Étape 5** | **Correction Sauvegarde des Séances (Screen 2) :** Résolution de l'erreur *« ❌ Échec. Réessayer »* lors de la validation du ressenti RPE et des notes de course dans l'interface PWA Sport | ⏳ À faire | En attente | ⏳ TDD à créer |
| **Étape 6** | **Mémoire Conversationnelle Multi-Tours (Gestion d'État / Screens 3 & 4) :** Fin du mode 100% "stateless", buffer d'historique des derniers échanges pour conserver le contexte du dialogue | ⏳ À faire | En attente | ⏳ TDD à créer |
| **Étape 7** | **Test d'Intégration End-to-End (E2E) & Recette Finale :** Validation complète du cycle stabilisé, non-régression (419+ tests), déploiement prod et recette utilisateur | ⏳ À faire | En attente | ⏳ TDD à créer |

---

## Détail des Étapes

### ⏳ Étape 1 : Correcteur Temporel Universel
* **Contexte & Problème :**
  - Des requêtes contenant des termes temporels relatifs (*« hier »*, *« demain »*, *« dernier »*, *« ces 3 derniers jours »*) subissent parfois des décalages calendaires ou sont captées par le mauvais handler.
* **Objectifs à réaliser :**
  1. Centraliser et unifier la logique de résolution temporelle dans un service/helper réutilisable (`UniversalDateResolver`).
  2. Gérer explicitement les expressions pluriel/période : *« ces 3 derniers jours »*, *« les 3 derniers échanges »*, *« cette semaine »*, *« la semaine dernière »*.
  3. Empêcher toute dérive de date lors du changement de semaine calendaire ou de fin de mois.
* **Critères d'acceptation :**
  - Tests unitaires TDD couvrant tous les cas temporels passés, relatifs et multiples.

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

### ⏳ Étape 5 : Correction Sauvegarde des Séances (Screen 2)
* **Contexte & Problème (Screen 2) :**
  - Erreur *« ❌ Échec. Réessayer »* affichée sur le bouton rouge lors de la saisie du debrief d'une séance de sport.
* **Objectifs à réaliser :**
  1. Inspecter la route appelée par le bouton (payload JSON, gestion des types, gestion du RPE, texte avec retours à la ligne ou caractères spéciaux).
  2. Améliorer la robustesse de l'endpoint et afficher un message d'erreur précis au lieu d'un échec opaque.
  3. Gérer le retry automatique et la mise à jour optimiste de l'UI.
* **Critères d'acceptation :**
  - Validation et enregistrement du debrief sans erreur, passage de la carte à l'état sauvegardé.

---

### ⏳ Étape 6 : Mémoire Conversationnelle Multi-Tours (Gestion d'État / Screens 3 & 4)
* **Contexte & Problème (Screens 3 & 4) :**
  - Le chat est actuellement 100% stateless : chaque message est traité isolément sans mémoire du message précédent (*« C'est l'application » ➔ « Tu parles de quelle application ? »*).
* **Objectifs à réaliser :**
  1. Intégrer un buffer d'historique de conversation (les $N$ derniers messages de la session active) transmis au NLU / Gemini.
  2. Permettre la résolution contextuelle des anaphores (*« l'application »*, *« celle-ci »*, *« la deuxième »*, *« corrige ça »*).
  3. Définir une politique de TTL / expiration de session propre pour ne pas mélanger des discussions distantes de plusieurs heures.
* **Critères d'acceptation :**
  - Tests unitaires et E2E validant la continuité d'un dialogue multi-tours.

---

### ⏳ Étape 7 : Test d'Intégration End-to-End (E2E) & Recette Finale
* **Objectifs à réaliser :**
  1. Test E2E couvrant les scénarios critiques corrigés.
  2. Validation de la suite complète à 100% au vert.
  3. Déploiement en production et validation avec l'utilisateur sur mobile.
