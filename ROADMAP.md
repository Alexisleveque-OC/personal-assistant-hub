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
| **Étape 2** | Extraction d'intentions LLM avec Structured Outputs (Pydantic) | ⚪ À venir | En attente | Tests de parsing naturel |
| **Étape 3** | Dialogue multi-tours & clarifications naturelles (ex: rayon inconnu) | ⚪ À venir | En attente | Tests conversationnels |
| **Étape 4** | Optimisation de latence (< 1-2s) : Cache RAM au boot & Écritures asynchrones | ⚪ À venir | En attente | Benchmarks & tests de cache |
| **Étape 5** | Branchement dans `/api/v1/interact` avec fallback de résilience local | ⚪ À venir | En attente | 170+ tests au vert |
| **Étape 6** | Tests d'intégration End-to-End (E2E) complets & validation sur PWA | ⚪ À venir | En attente | Tests E2E finaux |

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

### ⚪ Étape 2 : Extraction d'Intentions LLM avec Structured Outputs (Pydantic)
* **Objectifs :**
  1. Modéliser le schéma de réponse structuré Pydantic (`NLUResult`) contenant l'intention (`IntentType`), les paramètres typés et la réponse conversationnelle textuelle/orale.
  2. Fournir au modèle les définitions des intentions du Hub et le catalogue de référence.
  3. Remplacer les correspondances rigides de regex par une compréhension sémantique profonde et tolérante aux formulations orales variées.
  4. Tests unitaires comparatifs vérifiant la conformité des sorties par rapport aux contrats existants.
* **Critères de succès :** 100% des intentions reconnues et validées par tests.

---

### ⚪ Étape 3 : Dialogue Multi-Tours & Clarifications Naturelles
* **Objectifs :**
  1. Résoudre le problème du "papier cuisson classé automatiquement en Divers" :
     * Quand un article a un rayon inconnu ou ambigu, l'assistant pose une question de clarification naturelle (*"Je n'ai pas de rayon pour le papier cuisson. Veux-tu que je le range en Épicerie ou en Entretien ?"*).
  2. Mémorisation du contexte d'attente (`pending_clarification`) dans la session utilisateur.
  3. Au tour suivant, traitement de la réponse courte de l'utilisateur (*"En entretien"*), enregistrement de l'article avec son rayon et mise à jour du catalogue.
  4. Tests de dialogue à 2 tours.
* **Critères de succès :** Scénario multi-tours testé et validé.

---

### ⚪ Étape 4 : Optimisation de Latence (< 1 à 2 secondes)
* **Objectifs :**
  1. Éliminer le goulot d'étranglement des 8-9 secondes :
     * **Cache RAM persistant au démarrage** : chargement initial des catalogues de rayons et recettes en mémoire au boot de FastAPI. Plus aucun appel de lecture Google Sheets lors d'une commande vocale.
     * **Écritures asynchrones (`BackgroundTasks`)** : validation immédiate de l'intention et renvoi du message audio à la PWA en ~300 ms, écriture dans Google Sheets en tâche de fond.
  2. Invalidation chirurgicale du cache en cas de mutation.
  3. Tests automatisés vérifiant la rapidité d'exécution et l'intégrité des écritures.
* **Critères de succès :** Temps de réponse du endpoint mesuré à < 1-2s.

---

### ⚪ Étape 5 : Branchement dans `/api/v1/interact` & Mode Résilience Local
* **Objectifs :**
  1. Intégrer le moteur LLM dans le routeur principal de `/api/v1/interact`.
  2. Mise en place d'un fallback automatique : si la clé API Gemini n'est pas fournie ou en cas d'indisponibilité réseau, le hub bascule en toute transparence sur le parseur local déterministe (zéro régression, mode hors-ligne préservé).
  3. Garantir la compatibilité avec la PWA mobile et les raccourcis vocaux existants.
* **Critères de succès :** Suite complète des 170+ tests à 100% au vert.

---

### ⚪ Étape 6 : Tests d'Intégration End-to-End (E2E) & Validation PWA
* **Objectifs :**
  1. Écriture d'un test d'intégration complet E2E simulant un utilisateur réel sur la PWA.
  2. Validation manuelle sur smartphone en conditions réelles par l'utilisateur.
  3. Documentation finale et préparation de la MR vers `develop`.
* **Critères de succès :** Validation explicite par l'utilisateur sur son mobile.
