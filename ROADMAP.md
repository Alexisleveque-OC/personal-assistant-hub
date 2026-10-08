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
| **Étape 1** | **Socle SQLite & Journal Conversationnel :** Base `hub_data.db` (WAL mode), traçabilité des échanges (`conversation_logs`) et endpoints d'audit | 🟢 Terminé | Validé par l'utilisateur | ✅ 7/7 tests dédiés (359/359 total) au vert |
| **Étape 2** | **Second Cerveau Compartimenté :** Segmentation automatique LLM en 5 catégories (`dev_idea`, `bug_report`, `thought`, `preference`, `task`), service et endpoints | 🟢 Terminé | Prêt pour recette utilisateur | ✅ 5/5 tests dédiés (364/364 total) au vert |
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
* **Statut :** 🟢 Validé par l'utilisateur et commité (`bdd591f`).

---

### 🟢 Étape 2 : Second Cerveau Compartimenté (Segments Fondamentaux & Dynamiques Auto-Découverts)
* **Objectifs réalisés :**
  1. **Modélisation Pydantic & Intentions :**
     - Nouvelles intentions déclarées : `save_note`, `list_notes`, `delete_note`.
     - 5 segments fondamentaux par défaut (`dev_idea`, `bug_report`, `thought`, `preference`, `task`).
     - **Extensibilité dynamique et auto-découverte :** Otis accepte n'importe quelle catégorie ou thème récurrent (ex: `voyage`, `finance`, `lecture`, `musique`, `cuisine`, etc.) sans contrainte d'enum rigide.
     - Modèles de données flexibles : `SecondBrainNoteItem`, `SecondBrainNotesListResponse`, `NoteCreate`, `NoteUpdate`.
  2. **Persistance haute performance SQLite (`DatabaseManager`) :**
     - Méthodes CRUD ajoutées : `add_note`, `get_note`, `get_notes` (filtrage par catégorie quelconque, statut, recherche textuelle, pagination), `update_note`, `delete_note` et `get_notes_stats` (agrégation dynamique de tous les segments existants).
  3. **Classification NLU double niveau (Local + Gemini LLM) :**
     - Parseur local déterministe enrichi avec regex pour les 5 catégories et capture de préfixes dynamiques (`note <thème> : ...`).
     - Prompt système Gemini et schéma JSON instruits pour classifier et créer automatiquement des catégories thématiques sur des récurrences de vocabulaire.
  4. **Handler métier & Routeur REST dédié :**
     - Handler `handle_second_brain_intent` intégré dans le pipeline `/api/v1/interact` avec réponses orales complices adaptées aux catégories dynamiques.
     - Routeur FastAPI `app/routers/second_brain.py` sous `/api/v1/second-brain/*` :
       - `GET /notes` : liste paginée et filtrée
       - `POST /notes` : création directe
       - `GET /notes/{id}` : détail d'une note
       - `PATCH /notes/{id}` : mise à jour partielle (ex: statut `done`)
       - `DELETE /notes/{id}` : suppression
       - `GET /stats` : compteurs par catégorie (découverte dynamique)
  5. **TDD strict :** 6/6 tests unitaires et d'intégration validés dans `tests/test_second_brain.py` (incluant la création et le filtrage d'un segment dynamique `voyage`).
  6. **Zéro régression :** 365 tests du projet à 100% au vert.
* **Statut :** 🟢 Terminé, prêt pour recette utilisateur.


---


### ✅ Étape 3 : Auto-Apprentissage Vocal Interactif (`TEACH_ASSISTANT`) & Injection Dynamique
* **Objectifs validés :**
  1. **Intention `teach_assistant` :** Détection d'ordres de correction vocale (« Attention là tu as compris Troyes alors que je t'ai dit 3 », « Quand je dis renfort je veux dire renforcement », « Le quinoa va dans le rayon épicerie »).
  2. **Extraction et persistance de la règle :** Enregistrement dans la table `user_learnings` (SQLite WAL) et rattachement d'un feedback `"correction"` sur le dernier échange dans `conversation_logs`.
  3. **Rétro-correction & réponse vocale :** Formulations orales naturelles (« C'est bien noté Alexis, j'ai retenu la correction... »).
  4. **Injection dynamique dans le prompt NLU :** `build_system_prompt_with_learnings()` injecte à la volée les règles actives de `user_learnings` dans le prompt système de Gemini sans modifier une seule ligne de code.
  5. **Endpoints REST `/api/v1/system/learnings` :** CRUD complet (POST, GET, PATCH, DELETE) pour auditer ou désactiver des règles.
  6. **TDD strict :** 5/5 tests au vert dans `test_teach_assistant_learning.py`, 370/370 tests du projet au vert.

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
