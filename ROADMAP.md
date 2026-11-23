# Roadmap - Phase 6.10 : cerveau en cascade (Gemini → Claude)

Branche : `feat/llm-cascade` (depuis `develop`). La roadmap précédente (« Annuler » sur les 3 dernières actions) est dans l'historique git de ce fichier (commit `7d84763`).

## Objectif
Garder la rapidité actuelle sur les demandes simples tout en sachant répondre à une question complexe (ex. « je dois changer la porte de mon frigo »). Chaque demande va automatiquement au niveau le moins coûteux capable de la traiter :
- **Niveau 0 — PWA / sans LLM** (existant) : voie rapide des courses, réponse directe après une modification simple.
- **Niveau 1 — Gemini** (gratuit) : l'agent actuel et ses outils.
- **Niveau 2 — Claude Sonnet 5.5** (API payante) : l'« expert ».

## Décisions utilisateur (23/11)
- Expert : **Claude Sonnet 5.5**. Crédit prépayé de 5 $ et limite de dépense réglés sur la console Anthropic (compte perso).
- Passage à l'expert : quand la demande sort de ce que l'agent Gemini connaît (ses outils / le contexte de la PWA) ou qu'il n'arrive pas à la traiter d'un coup. Si l'expert ne sait pas non plus, il demande à l'utilisateur de clarifier.
- Réponses de l'expert **courtes** (adaptées à l'oral) + **bouton pause** pour couper la lecture vocale.
- Filet manuel « creuse ça » (réponse plus détaillée) : **discret**.
- Conversation continue (micro rouvert sans mot de réveil) : reportée.

## Choix techniques (agent, à signaler en fin d'étape)
- SDK officiel `anthropic` (version épinglée) ; clé `ANTHROPIC_API_KEY` dans `.env` (local) et en secret GitHub → variable Cloud Run. Jamais dans le dépôt.
- Expert = boucle Claude séparée de la boucle Gemini (`app/core/expert/`), qui réutilise le même `ToolRegistry` (exécution et validation Pydantic identiques). Les déclarations d'outils sont converties au format Claude (`input_schema` JSON Schema).
- Escalade : outil `demander_expert` exposé à Gemini + escalade automatique quand Gemini échoue (réponse vide, réponse mal formée, limite de boucle, Gemini indisponible) **seulement si rien n'a été modifié** pendant le tour ; sinon, message d'échec actuel (mutations signalées).
- Si l'expert termine par une question, la réponse de l'utilisateur lui revient directement (sans repasser par Gemini).
- Coût : table SQLite `llm_usage` (date, modèle, tokens entrée/sortie/cache, coût en $) ; garde-fou mensuel `CLAUDE_MONTHLY_BUDGET_USD` (5 par défaut) : au-delà, pas d'appel à l'expert et message explicite.
- Réponses courtes : consigne de l'expert (2 à 4 phrases, sans listes ni markdown à l'oral), `max_tokens` borné ; effort bas pour la latence.
- Hors périmètre (à rediscuter, coût) : recherche web de Claude.

## Étapes
- [ ] **Étape 1 — Connecteur Claude + boucle de l'expert** : `ClaudeExpertLLM` (SDK, erreurs explicites typées, mock hors ligne), conversion des outils au format Claude, `ExpertService` (boucle outils → réponse), consigne courte. Tests unitaires avec un faux client.
- [ ] **Étape 2 — Escalade depuis Gemini** : outil `demander_expert`, escalade automatique sur échec sans mutation, suite directe à l'expert quand il a posé une question, réponse et journal (`llm_calls` avec le niveau). Tests du handler.
- [ ] **Étape 3 — Coûts et garde-fou** : table `llm_usage`, calcul du coût par appel, total du mois, refus au-delà du budget ; coût visible dans le journal des conversations.
- [ ] **Étape 4 — PWA** : bouton pause pendant la lecture vocale (`cancelSpeaking`) ; lien discret « Approfondir » sous une réponse de l'expert (réponse détaillée affichée à l'écran). Tests Node + E2E Chromium.
- [ ] **Étape 5 — Déploiement et validation réelle** : secret `ANTHROPIC_API_KEY` dans la CD, questions types réelles (simples → niveau 0/1, complexes → expert), E2E de bout en bout, README, déploiement, test téléphone ; bilan de coût après quelques jours.
