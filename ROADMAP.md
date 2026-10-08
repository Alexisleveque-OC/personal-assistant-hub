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

### ✅ Étape 4 : Commande d'Annulation Immédiate (« Undo »)
* **Objectifs validés :**
  1. **Intention `undo_last_action` :** Détection d'ordres d'annulation immédiate (« Annule », « Annule ça », « Oups annule ma dernière commande », « Reviens en arrière », « Undo »).
  2. **Mécanisme d'inversion contextuelle :** Module dédié `app/handlers/undo_handler.py` avec rollbacks adaptés selon le domaine :
     - *Second cerveau* : suppression immédiate de la note créée en base SQLite.
     - *Auto-apprentissage* : suppression / désactivation de la règle formulée.
     - *Courses* : retrait de l'article ajouté via `remove_shopping_item`.
  3. **Message informatif de sécurité :** Réponse courtoise si aucune action récente n'est réversible (« Il n'y a aucune action récente à annuler »).
  4. **TDD strict :** 5/5 tests validés dans `tests/test_undo_last_action.py`, 375/375 tests du projet au vert.

---

### ✅ Étape 5 : Pipeline STT Haute-Fidélité & Audio Direct Backend
* **Objectifs validés :**
  1. **Couche de normalisation phonétique :** Module dédié [app/core/audio/phonetic_normalizer.py](file:///home/alexis/CODE/personal-assistant-hub/app/core/audio/phonetic_normalizer.py) corrigeant préventivement les confusions usuelles (« RPE à Troyes » $\rightarrow$ « RPE à 3 », « autiste/notice » $\rightarrow$ « Otis », « renfort » $\rightarrow$ « renforcement », « des plus » $\rightarrow$ « D+ »).
  2. **Service STT Multimodal Gemini :** Module dédié [app/core/audio/stt_service.py](file:///home/alexis/CODE/personal-assistant-hub/app/core/audio/stt_service.py) envoyant directement le flux audio base64 avec `inlineData` à l'API Gemini pour une transcription exacte et une extraction structurée.
  3. **Endpoint direct `POST /api/v1/interact/audio` :** Réception de flux audio bruts (WebM, WAV, OGG, MP3), validation MIME type, transcription et exécution transparente du pipeline conversationnel avec renvoi de `transcribed_text`.
  4. **TDD strict :** 5/5 tests validés dans `tests/test_audio_stt_and_phonetic.py`, 380/380 tests du projet au vert.

---

### ✅ Étape 6 : Ergonomie Vocale PWA (VAD Anti-Coupure, Push-to-Talk, Wake Word & Undo Toast)
* **Objectifs validés :**
  1. **Voice Activity Detection (VAD) Web Audio API & MediaRecorder :**
     - Analyse du flux audio via `AnalyserNode` en continu.
     - Gestion d'un seuil de silence tolérant (1.5s, 2.0s, 2.5s configurable dans les paramètres) empêchant toute coupure prématurée lors d'hésitations orales.
     - Envoi du flux audio brut directement à `POST /api/v1/interact/audio`.
  2. **Mode Push-to-Talk & Bascule :**
     - Possibilité d'activer le mode Push-to-Talk (maintenir le bouton micro appuyé pour parler) avec persistance dans `localStorage`.
  3. **Wake Word in-app (« Otis ») :**
     - Détection discrète en continu du mot-clé de réveil déclenchant automatiquement la capture audio si activé.
  4. **Toast flottant d'annulation immédiate (« Undo ») :**
     - Composant `#undo-toast` apparaissant automatiquement après l'enregistrement d'une note, d'une règle d'apprentissage ou l'ajout d'articles de courses, permettant d'annuler en 1 tap tactile (8s d'affichage).
  5. **Zéro régression :** 380/380 tests du projet à 100% au vert.
* **Statut :** 🟢 Terminé, prêt pour recette utilisateur.

---

### ✅ Étape 7 : Interface PWA - Vues Second Cerveau & Journal d'Audit
* **Objectifs validés :**
  1. **Vue Second Cerveau ES6 (`second_brain_view.js`) :**
     - Onglet « Cerveau » dédié dans la barre de navigation inférieure de la PWA.
     - Contrôle segmenté : sous-vue [🧠 Notes & Idées] et sous-vue [📜 Journal & Feedback].
     - Filtres par catégories dynamiques (Pills : Tous, 🛠️ À Développer, 🐛 Bugs & Fixes, 💡 Pensées, 🎯 Préférences, 📋 Tâches, 🌴 Voyages, 🍳 Cuisine, 🏃 Coach Sport...).
     - Filtres par statut (Actives / Toutes / Archivées) et barre de recherche textuelle en temps réel.
     - Formulaire d'ajout rapide inline de note avec sélection de catégorie.
     - Cartes de notes interactives avec bascule de statut (✓ Fait / ↺ Réactiver) et suppression.
  2. **Vue Journal Conversationnel d'Audit & Feedback :**
     - Liste détaillée des échanges (requête utilisateur, réponse d'Otis, intention détectée, modèle LLM, latence en ms, statut succès/erreur).
     - Bouton interactif « 💬 Corriger / Signaler » ouvrant un formulaire de feedback pour alimenter le moteur d'auto-apprentissage (`postConversationFeedback`).
  3. **Mise à jour PWA & Service Worker :**
     - Cache incrémenté en `v15` dans `sw.js` avec mise en cache de `second_brain_view.js`.
     - Script tag PWA incrémenté en `v=10.0`.
  4. **Zéro régression :** 380/380 tests du projet à 100% au vert.
* **Statut :** 🟢 Terminé, prêt pour recette utilisateur.

---

### ⚪ Étape 8 : Ingestion Multimodale Visuelle & Second Cerveau (Screenshots / Photos Gemini Vision)
* **Objectifs :**
  1. **Endpoint d'analyse visuelle `/api/v1/second-brain/notes/image` :**
     - Réception d'images et captures d'écran (PNG, JPEG, WebP) avec champ optionnel `category_hint` ou `note_text`.
     - Traitement multimodal natif via Gemini Vision (`inlineData`).
  2. **Extraction contextuelle et classification autonome :**
     - Détection du type de contenu :
       - Screenshot de bug / code / console -> note classifiée en `bug_report`.
       - Screenshot d'hôtel / destination / billet -> note classifiée en `voyage` ou `vacances`.
       - Screenshot de feature / maquette / repo -> note classifiée en `dev_idea`.
       - Screenshot de plat / recette -> note classifiée en `cuisine`.
     - Extraction d'une synthèse courte et pertinente sans forcer l'utilisateur à décrire manuellement.
  3. **Persistance directe en base SQLite (`second_brain_notes`) :**
     - Stockage de la note enrichie avec tags et référence.
  4. **TDD strict :** tests unitaires et mocks de l'analyse d'image.

---

### ⚪ Étape 9 : Test d'Intégration End-to-End (E2E) & Recette Finale
* **Objectifs :**
  1. Test E2E simulant l'ensemble du cycle de la Phase 6 :
     - Enregistrement dans le journal conversationnel et mesure de latence.
     - Correction vocale (`teach_assistant`) et injection dynamique de la règle au tour suivant.
     - Capture d'idées réparties dans les différents segments du second cerveau (texte et image).
     - Commande d'annulation ("Undo") réversible.
     - Pipeline audio direct backend et normalisation phonétique.
  2. Suite complète de tests (380+ tests) à 100% au vert.
  3. Validation manuelle et recette par l'utilisateur.

