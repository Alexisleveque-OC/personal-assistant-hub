# Roadmap - « Annuler » sur les 3 dernières actions

Branche : `feat/undo-recent-actions` (depuis `develop`). La roadmap précédente (refonte UX/UI) est dans l'historique git de ce fichier (commit `e7df03d`).

## Décisions utilisateur (18/11)
- Conflit : on annule seulement si les données sont restées telles qu'Otis les a laissées ; sinon message explicite (même règle « tout ou rien » que l'annulation actuelle).
- Portée : seules les actions faites depuis ce téléphone (même `session_id`) sont annulables.
- Mécanisme : route directe, sans LLM (instantané, gratuit, déterministe).
- Action sans lot d'annulation (correction mémorisée, ancien flux de notes) : affichée sans bouton ; « annule ça » à la voix inchangé.
- Après annulation : la ligne reste, grisée, marquée « Annulée » à la place du bouton.

## Existant
- `GET /api/v1/home/recent-actions` : 3 dernières actions lues dans `conversation_logs` ; seule la plus récente de la session est `undoable` ; le bouton envoie « annule ça » à Otis.
- `UndoJournal` (table `agent_undo_batches`) : un lot d'annulation par tour de l'agent ; `UndoService.undo_last(session)` vérifie chaque cible puis restaure tout ou rien.
- Voie rapide (ajout simple aux courses, sans LLM) : annulation gardée en mémoire de session (`last_undoable_action`), pas de lot.

## Étapes
1. **Lien action ↔ lot** : l'identifiant du lot d'annulation est écrit dans les paramètres du journal (`data["undo_batch_id"]`) pour les tours de l'agent et les réponses aux questions de rayon. Pas de changement de schéma.
2. **Voie rapide** : un ajout simple aux courses enregistre aussi un lot (`ShoppingAddedUndo`), en plus de la mémoire de session (« annule ça » à la voix inchangé).
3. **Service** : `UndoService.undo_batch(session_id, batch_id)` — refus explicite si le lot est d'une autre session, déjà annulé, ou si les données ont changé depuis ; `undo_last` réutilise le même cœur.
4. **API** : `POST /api/v1/home/recent-actions/{log_id}/undo` (clé API, `session_id`) → message d'Otis ; l'annulation est tracée dans le journal des conversations ; `recent-actions` renvoie `undoable` (session + lot non annulé) et `undone`.
5. **PWA** : bouton « Annuler » sur chaque action annulable, toast du résultat, liste et feuille concernée rafraîchies ; bump du SW.
6. **E2E** : ajout puis annulation d'une action plus ancienne de bout en bout ; README.
