# Roadmap Feature : Phase 6 - Moteur Vocal Haute-Fidélité, Mémoire Long-terme & Second Cerveau (`feat/voice-memory-second-brain`)

> **Règles d'or (AGENTS.md) :**
> - Chaque étape doit être validée **manuellement et explicitement par l'utilisateur** avant de passer à la suivante.
> - La suite de tests automatisés (`pytest`) doit être à **100% au vert** à chaque étape (TDD strict : Rouge ➔ Vert ➔ Refactor).
> - Zéro commit prématuré sans test ni validation préalable.
> - À la fin de la feature, un **test d'intégration End-to-End (E2E)** doit valider le flux complet de bout en bout.

---

## Vue d'ensemble des Étapes

| Étape | Description | Statut | Validation Utilisateur | Tests Automatisés |
| :--- | :--- | :---: | :---: | :---: |
| **Étape 1** | **Socle SQLite & Journal Conversationnel :** Base `hub_data.db` (WAL mode), traçabilité des échanges (`conversation_logs`) et endpoints d'audit | 🟢 Terminé | Prêt pour recette utilisateur | ✅ 7/7 tests dédiés (359/359 total) au vert |
| **Étape 2** | **Second Cerveau Compartimenté :** Segmentation automatique LLM en 5 catégories (`dev_idea`, `bug_report`, `thought`, `preference`, `task`), service et endpoints | ⚪ À faire | En attente | Tests unitaires (TDD strict) |
| **Étape 3** | **Auto-Apprentissage Vocal (`TEACH_ASSISTANT`) :** Extraction de règle par Gemini, table `user_learnings`, rétro-correction et injection dynamique dans le prompt | ⚪ À faire | En attente | Tests unitaires (TDD strict) |
| **Étape 4** | **Commande d'Annulation (« Undo ») :** Intention `undo_last_action` et annulation contextuelle (repas, courses, sport, notes) | ⚪ À faire | En attente | Tests unitaires (TDD strict) |
| **Étape 5** | **Pipeline STT & Audio Direct Backend :** Endpoint audio direct (`/api/v1/interact/audio`) avec transcription multimodale Gemini & normalisation phonétique | ⚪ À faire | En attente | Tests unitaires (TDD strict) |
| **Étape 6** | **Ergonomie Vocale PWA :** VAD anti-coupure avec délai de silence configurable (1.5s - 2.5s), mode Push-to-Talk, Wake Word in-app (« Otis ») | ⚪ À faire | En attente | Tests manuels & PWA |
| **Étape 7** | **Interface PWA - Vues Second Cerveau & Audit :** Consultation et filtres pills (🛠️ À dev, 🐛 Bugs, etc.), vue Journal des échanges avec feedback | ⚪ À faire | En attente | Tests visuels & ergonomie |
| **Étape 8** | **Test d'Intégration End-to-End (E2E) & Recette Finale :** Validation du cycle complet (journal, apprentissage vocal in-context, notes, annulation) | ⚪ À faire | En attente | Suite complète (100% au vert) |

---

## Détail des Étapes

### 🟢 Étape 1 : Socle de Persistance SQLite & Journal Conversationnel (`conversation_logs`)
* **Objectifs réalisés :**
  1. **Base SQLite unifiée locale (`hub_data.db`) :**
     - Initialisation automatique avec mode WAL (`PRAGMA journal_mode=WAL;`), clés étrangères actives (`PRAGMA foreign_keys=ON;`) et timeout à 5000ms.
     - Tables créées : `conversation_logs`, `conversation_feedbacks`, `user_learnings`, `second_brain_notes`.
  2. **Traçabilité systématique des interactions :**
     - Enregistrement systématique dans `conversation_logs` de chaque requête arrivant sur `/api/v1/interact` : session, prompt brut, intention détectée, paramètres, réponse générée, statut succès, latence en millisecondes (`latency_ms`), modèle LLM résolu, trace d'erreur.
     - L'identifiant généré `log_id` est retourné dans le payload `data` de `InteractionResponse` pour faciliter le feedback côté client.
  3. **Endpoints de consultation & audit :**
     - `GET /api/v1/system/conversation-logs` avec pagination (`limit`, `offset`) et filtres (`session_id`, `success`).
     - `GET /api/v1/system/conversation-logs/{log_id}` retournant le détail d'un échange et ses feedbacks.
     - `POST /api/v1/system/conversation-logs/{log_id}/feedback` pour enregistrer un retour utilisateur (positif, négatif, correction).
  4. **TDD strict :** 7/7 tests unitaires et d'intégration validés dans `tests/test_database_and_audit_logs.py`.
  5. **Zéro régression :** 359 tests du projet à 100% au vert.
* **Statut :** 🟢 Terminé, prêt pour recette utilisateur.


---

### ⚪ Étape 2 : Second Cerveau Compartimenté (5 Segments SQLite + Classification LLM)
* **Objectifs :**
  1. **Modélisation Pydantic & Intentions :**
     - Nouvelles intentions : `save_note`, `list_notes`, `delete_note`.
     - 5 segments stricts :
       - 🛠️ `dev_idea` : Idées de développement (« À dev », « J'aimerais que ça fasse... »)
       - 🐛 `bug_report` : Corrections à apporter (« Bug », « Problème sur... »)
       - 💡 `thought` : Réflexions et pensées libres
       - 🎯 `preference` : Préférences et habitudes
       - 📋 `task` : Tâches à réaliser
  2. **Service métier `SecondBrainService` :**
     - Classification automatique intelligente par Gemini ou extraction déterministe locale.
     - Méthodes CRUD avec filtrage instantané par segment, recherche textuelle et statut (actif, archivé).
  3. **Handler & Endpoints API :**
     - Handler `second_brain_handler.py` intégré dans `/api/v1/interact`.
     - Endpoints REST : `/api/v1/second-brain/notes` (`GET`, `POST`, `DELETE`, `PATCH`).
  4. **TDD strict :** tests unitaires du parsing d'intention, de la classification et du service de notes.

---

### ⚪ Étape 3 : Auto-Apprentissage Vocal Interactif (`TEACH_ASSISTANT`) & Injection Dynamique
* **Objectifs :**
  1. **Intention `teach_assistant` :**
     - Détection des ordres de correction vocale (« Attention là tu as compris Troyes alors que je t'ai dit 3 », « Quand je dis renfort je veux dire renforcement », « Le quinoa va en épicerie »).
  2. **Extraction autonome de la règle :**
     - Analyse du dernier tour de parole issu de `conversation_logs` et formalisation par Gemini de la règle acquise (déclencheur, valeur corrigée, catégorie).
     - Persistance dans la table `user_learnings`.
  3. **Rétro-correction immédiate :**
     - Modification de la dernière action erronée (correction de la séance de sport, réassignation de rayon, etc.).
  4. **Injection dynamique sans modification de code :**
     - Le service NLU charge automatiquement les règles actives de `user_learnings` et les injecte dans le prompt système à chaque tour de parole.
  5. **TDD strict :** tests du flux de correction vocale, persistance de la règle et injection dans le prompt NLU.

---

### ⚪ Étape 4 : Commande d'Annulation Immédiate (« Undo »)
* **Objectifs :**
  1. **Intention `undo_last_action` :**
     - Détection vocale (« Annule », « Oups annule ma dernière commande », « Reviens en arrière »).
  2. **Mécanisme d'inversion contextuelle :**
     - Capacité à annuler la dernière action selon son domaine : suppression de la dernière note créée, suppression du dernier article de courses ajouté, ou annulation de la dernière séance de sport enregistrée.
  3. **TDD strict :** tests unitaires de l'annulation sur les différents domaines.

---

### ⚪ Étape 5 : Pipeline STT Haute-Fidélité & Audio Direct Backend
* **Objectifs :**
  1. **Endpoint audio direct `/api/v1/interact/audio` :**
     - Réception d'un flux audio WebM / WAV / OGG capté côté client.
     - Analyse multimodale native directe via Gemini (audio direct dans `generateContent`) ou transcription assistée avec lexique métier.
  2. **Couche de normalisation phonétique intelligente :**
     - Remplacement préventif et contextuel des confusions récurrentes (« Otis » vs « 10 » / « Autiste », « 3 » vs « Troyes », « renfort » vs « renforcement ») pour fiabiliser le flux Web Speech.
  3. **TDD strict :** tests du format audio, de l'endpoint et de la normalisation phonétique.

---

### ⚪ Étape 6 : Ergonomie Vocale PWA (VAD Anti-Coupure, Push-to-Talk, Wake Word)
* **Objectifs :**
  1. **Voice Activity Detection (VAD) tolérant :**
     - Reconnaissance vocale continue avec timer de silence configurable (1.5s à 2.5s réglable dans les paramètres) pour laisser le temps d'hésiter sans coupure intempestive.
  2. **Mode Push-to-Talk & Bascule :**
     - Bouton poussoir (maintenir pour parler) ou toggle pour choisir entre VAD automatique et Push-to-Talk.
  3. **Wake Word in-app (« Otis ») :**
     - Détection en écoute continue du mot-clé de réveil dans l'application ouverte.
  4. **Bouton tactile d'annulation (« Undo ») :**
     - Toast / bouton réactif immédiat après chaque action pour annuler en 1 clic.

---

### ⚪ Étape 7 : Interface PWA - Vues Second Cerveau & Journal d'Audit
* **Objectifs :**
  1. **Vue Second Cerveau ES6 :**
     - Onglet dédié ou sous-vue avec filtres pills (🛠️ À dev, 🐛 Bugs, 💡 Pensées, 🎯 Préférences, 📋 Tâches).
     - Saisie rapide au clavier ou dictée vocale, suppression et archivage.
  2. **Vue Journal & Feedback :**
     - Consultation des dernières interactions avec latence, modèle utilisé et bouton de signalement/correction.
  3. **Incrémentation Service Worker (v13).**

---

### ⚪ Étape 8 : Test d'Intégration End-to-End (E2E) & Recette Finale
* **Objectifs :**
  1. Test E2E simulant l'ensemble du cycle de la Phase 6 :
     - Enregistrement dans le journal conversationnel.
     - Correction vocale (`teach_assistant`) et vérification de la prise en compte de la règle au tour suivant.
     - Capture d'idées réparties dans les 5 segments du second cerveau.
     - Commande d'annulation ("Undo") réversible.
  2. Suite de 350+ tests à 100% au vert.
  3. Validation manuelle et recette par l'utilisateur.
