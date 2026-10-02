# Roadmap Feature : Cerveau Conversationnel LLM Gemini & Performance (`feat/gemini-llm-brain`)

> **Règles d'or (AGENTS.md) :**
> - Chaque étape doit être validée **manuellement et explicitement par l'utilisateur** avant de passer à la suivante.
> - La suite de tests automatisés (`pytest`) doit être à **100% au vert** à chaque étape (TDD strict).
> - À la fin de la feature, un **test d'intégration End-to-End (E2E)** doit valider le flux complet de bout en bout.

---

## Vue d'ensemble des Étapes

| Étape | Description | Statut | Validation Utilisateur | Tests Automatisés |
| :--- | :--- | :---: | :---: | :---: |
| **Étape 1** | Configuration Pydantic & Client Gemini avec auto-découverte du dernier modèle Flash | 🟢 Terminé | En attente de validation | ✅ 7/7 tests unitaires + live au vert |
| **Étape 2** | Extraction d'intentions LLM avec Structured Outputs (Pydantic) & Chaîne de repli | 🟢 Terminé | Validé par l'utilisateur | ✅ 6 tests NLU + 185 tests au vert |
| **Étape 3** | Dialogue multi-tours & clarifications naturelles (ex: rayon inconnu) | 🟢 Terminé | Validé par l'utilisateur | ✅ 5 tests dédiés + 191 tests au vert |
| **Étape 4** | Optimisation de latence (< 1-2s) : Cache RAM au boot & Écritures asynchrones | 🟢 Terminé | Validé par l'utilisateur | ✅ 3 tests de latence + 194 tests au vert |
| **Étape 5** | Branchement dans `/api/v1/interact`, mémoire multi-tours & tolérance recettes | 🟢 Terminé | Validé par l'utilisateur | ✅ 205/205 tests au vert |
| **Étape 6** | Tests d'intégration End-to-End (E2E) complets & validation finale | 🟡 En cours de validation | En attente de validation utilisateur | ✅ 3/3 tests E2E (208/208 total) au vert |

---

## Détail des Étapes

### 🟢 Étape 1 : Configuration Pydantic & Client Gemini avec Auto-Découverte Dynamique
* **Objectifs :**
  1. Étendre `app/config.py` avec `gemini_api_key` et `gemini_model` (valeur par défaut `"auto"`).
  2. Créer `app/core/llm/gemini_client.py` :
     * Implémenter l'auto-découverte dynamique du dernier modèle `flash` stable via `client.models.list()`.
     * Filtrer pour exclure les modèles expérimentaux (`-preview`, `-experimental`, `-thinking`) et retenir la version stable la plus élevée (ex: `2.5` > `2.0` > `1.5`).
     * Mettre en cache le modèle sélectionné au démarrage pour éviter tout appel réseau inutile lors des requêtes vocales.
     * Fallback de secours résilient en cas d'absence de réseau au boot.
  3. Tests unitaires dédiés (mocks et cas limites) dans `tests/test_gemini_client.py`.
* **Résultat validé :** 7/7 tests au vert, modèle auto-découvert en live avec succès (`gemini-3.8-flash`).
* **Critères de succès :** Tests unitaires à 100% au vert, validation manuelle par l'utilisateur.

---

### 🟢 Étape 2 : Extraction d'Intentions LLM avec Structured Outputs (Pydantic) & Chaîne de Repli
* **Objectifs :**
  1. Modéliser le schéma de réponse structuré Pydantic (`LLMNLUResponse`) contenant l'intention (`IntentType`), les paramètres typés, le niveau de confiance et la réponse conversationnelle contextuelle.
  2. Fournir au modèle les définitions des intentions du Hub, les contraintes et le contexte conversationnel (anaphores multi-tours).
  3. Implémenter une chaîne de repli multi-modèles robuste (`get_candidate_models`) pour basculer automatiquement sur un modèle stable (ex: `gemini-3.6-flash`) si le premier candidat renvoie une erreur 503 ou 404.
  4. Bascule transparente sur le parseur local déterministe en cas de quota dépassé (garde-fou) ou indisponibilité réseau.
  5. Tests unitaires et d'intégration validant le parsing naturel, l'extraction de paramètres multiples et la conformité stricte Pydantic.
* **Résultat validé :** 6 tests unitaires LLM + 185/185 tests au vert dans toute la suite pytest.
* **Critères de succès :** 100% des intentions reconnues et validées par tests.

---

### 🟢 Étape 3 : Dialogue Multi-Tours & Clarifications Naturelles
* **Objectifs :**
  1. Résoudre le problème du "papier cuisson classé automatiquement en Divers" :
     * Quand un article a un rayon inconnu ou ambigu, l'assistant pose une question de clarification naturelle (*"Je n'ai pas de rayon pour 'Papier cuisson'. Veux-tu que je le range en Entretien ou en Épicerie ?"*).
  2. Mémorisation du contexte d'attente (`pending_action` / `clarify_shopping_rayon`) dans la session utilisateur.
  3. Au tour suivant, traitement de la réponse courte de l'utilisateur (*"En entretien"* ou *"Laisse en divers"* ou *"Annule"*), enregistrement de l'article avec le rayon choisi et mise à jour du cache de rayons.
  4. Tests de dialogue à 2 tours (acceptation, choix alternatif, divers, annulation, article connu immédiat).
* **Résultat validé :** 5 tests de clarification dédiés + 191/191 tests au vert dans toute la suite pytest (zéro régression).
* **Critères de succès :** Scénario multi-tours testé et validé.

---

### 🟢 Étape 4 : Optimisation de Latence (< 1 à 2 secondes)
* **Objectifs :**
  1. Éliminer le goulot d'étranglement des 8-9 secondes :
     * **Cache RAM persistant au démarrage (`warmup_cache`)** : préchauffage via le cycle `lifespan` FastAPI au boot, chargeant en mémoire catalogues de rayons, recettes, ordre et listes.
     * **Mise à jour optimiste du cache** : les ajouts d'articles mettent immédiatement à jour `_shopping_cache` en mémoire pour des lectures subséquentes instantanées sans réinterrogation Google Sheets.
     * **Écritures asynchrones (`BackgroundTasks`)** : intégration dans `/api/v1/interact` et `/api/v1/mobile/interact` permettant d'envoyer la réponse audio instantanément.
     * **Endpoint dédié** : `/api/v1/cache/warmup` pour préchauffer ou rafraîchir le cache à la demande.
  2. Tests automatisés vérifiant la rapidité d'exécution (< 0.5s en mémoire) et l'intégrité du cache.
* **Résultat validé :** 3 tests de performance/latence + 194/194 tests au vert.
* **Critères de succès :** Temps de traitement mémoire < 0.5s et 100% des tests passés.

---

### 🟢 Étape 5 : Branchement dans `/api/v1/interact`, Mémoire Conversationnelle & Tolérance Recettes
* **Objectifs :**
  1. Intégrer le moteur LLM dans le routeur principal de `/api/v1/interact` avec réponses concises (1-2 phrases).
  2. Maintenir l'historique conversationnel multi-tours (`history`) dans la session pour préserver le fil du dialogue.
  3. Gestion robuste des dates relatives (`parse_target_date` pour `"today"`, `"tomorrow"`, `"ce soir"` sans erreur `ValueError`).
  4. Tolérance avancée aux recettes dans Google Sheets : normalisation des tirets, accents, ponctuations et pluriels dans la recherche (`"croque-monsieur"` $\leftrightarrow$ `"Croque monsieur"`).
  5. Mise en place d'un fallback automatique en cas de quota dépassé ou indisponibilité réseau.
* **Résultat validé :** 205/205 tests passés au vert, validé manuellement par l'utilisateur sur sa PWA.
* **Critères de succès :** Suite complète à 100% au vert et validation manuelle.

---

### 🟡 Étape 6 : Tests d'Intégration End-to-End (E2E) & Validation Finale
* **Objectifs :**
  1. Écriture d'un test d'intégration complet E2E simulant un utilisateur réel sur la PWA (`tests/test_e2e_gemini_llm_brain.py`).
  2. Validation de l'enchaînement complet :
     - Warmup & suivi des quotas LLM (`/api/v1/cache/warmup`, `/api/v1/llm/stats`).
     - Tour 1 : Réflexion & suggestion de repas conversationnelle.
     - Tour 2 : Choix dans le fil avec tolérance tiret/espace (`"croque-monsieur"` $\leftrightarrow$ `"Croque monsieur"`).
     - Tour 3 & 4 : Clarification de rayon ambigu et confirmation de rangement.
     - Tour 5 : Vérification de planning fluide et concis.
     - Tour 6 : Anaphore contextuelle d'ingrédients (*« ajoute ses ingrédients »*).
     - Résilience et bascule transparente si panne API Gemini.
  3. Validation manuelle sur smartphone en conditions réelles par l'utilisateur.
  4. Documentation finale et préparation de la fusion vers `develop`.
* **Résultat automatisé :** ✅ 3/3 tests E2E passés avec succès (208/208 tests au vert sur toute la suite).
* **Critères de succès :** Validation explicite par l'utilisateur sur son mobile.
